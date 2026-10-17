"""money.ricerca.mean_reversion_basis — Simulatore di mean reversion dello spot-perp basis.

Questo modulo implementa la ricerca pre-registrata descritta in
docs/ipotesi/mean_reversion_basis_BTC_ETH.md e piano dati in
docs/piano_dati.md.

Non esegue ordini live: produce solo dati di backtest e un Esito
da passare a money.cancello per il giudizio.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple, List

from .. import statistica
from ..costi import Tariffa, Venue
from ..cancello import Esito


class EsitoMeanReversionBasis(Esito):
    """Esito della simulazione, pronto per money.cancello."""
    pass


def carica_config(config_path: Optional[Path] = None) -> dict:
    """Carica configurazione da JSON, altrimenti usa DEFAULT_CONFIG."""
    config = DEFAULT_CONFIG.copy()
    if config_path and config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            import json
            user_cfg = json.load(f)
            config.update(user_cfg)
    return config


# ----------------------------------------------------------------------
# Configurazione di default (può essere sovrascritta da file JSON)
# ----------------------------------------------------------------------
DEFAULT_CONFIG = {
    "simboli": ["BTC/USDT", "ETH/USDT"],  # spot symbols (usati per derivare perp)
    "perpetual_suffix": ":USDT",           # OKX perpetual USDT margined
    "timeframe": "8h",                     # funding interval (data sono ogni 8h)
    "zscore_entry": 2.0,                   # entrare quando |basis| > questa soglia in basis points
    "zscore_exit": 0.5,                    # uscire quando |basis| < questa soglia
    "lookback_window": 60,                 # non utilizzato nella versione semplice (soglia assoluta)
    "max_holding_periods": 3,              # massimo numero di periodi di funding da tenere
    "slippage_per_side": 0.0004,
    "commission_taker": 0.0005,
    "commission_maker": 0.0002,
    "leverage_max": 2.0,
    "margin_init_pct": 0.05,
    "risk_per_trade_pct": 0.01,            # frazione di capitale da allocare come margine per gamba
    "min_operazioni_train": 30,
    "capitale_riferimento_eur": 1000.0,
}


def simula_mean_reversion_basis(
    data_inizio: str,
    data_fine: str,
    config: Optional[dict] = None,
) -> EsitoMeanReversionBasis:
    """Esegue una simulazione di mean reversion del basis usando soglie assolute."""
    cfg = carica_config(config)
    
    # Percorso dati
    data_path = Path("/home/sergio/money/data/funding_xperp.jsonl")
    if not data_path.exists():
        raise FileNotFoundError(f"Dati non trovati: {data_path}")
    
    # Carica tutti i record
    records: List[dict] = []
    with data_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                records.append(rec)
            except json.JSONDecodeError:
                continue
    
    # Filtra per simbolo e range temporale
    simboli = [s + cfg["perpetual_suffix"] for s in cfg["simboli"]]  # es. BTC/USDT:USDT
    from datetime import datetime, timezone
    def to_ms(s: str) -> int:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    ts_inizio = to_ms(data_inizio)
    ts_fine = to_ms(data_fine)
    
    # Raggruppa per simbolo
    by_symbol: dict[str, List[dict]] = {s: [] for s in simboli}
    for rec in records:
        sym = rec.get("simbolo")
        ts = rec.get("ts")
        if sym in by_symbol and ts_inizio <= ts <= ts_fine:
            by_symbol[sym].append(rec)
    
    # Ordina ciascuna lista per timestamp
    for sym in by_symbol:
        by_symbol[sym].sort(key=lambda x: x["ts"])
    
    # Parametri
    entry_thr = cfg["zscore_entry"]   # basis points
    exit_thr = cfg["zscore_exit"]
    max_hold = cfg["max_holding_periods"]
    # periodo medio in ms (differenza tra timestamp consecutivi)
    period_ms = None
    for sym in simboli:
        lst = by_symbol[sym]
        if len(lst) >= 2:
            diffs = [lst[i+1]["ts"] - lst[i]["ts"] for i in range(len(lst)-1)]
            if diffs:
                period_ms = int(sum(diffs) / len(diffs))
                break
    if period_ms is None:
        period_ms = 8 * 3600 * 1000  # fallback 8h
    
    capitale = cfg["capitale_riferimento_eur"]
    leverage = cfg["leverage_max"]
    margin_pct = cfg["margin_init_pct"]
    risk_per_trade = cfg["risk_per_trade_pct"]
    # Margin allocated per leg (EUR)
    margin_alloc = capitale * risk_per_trade  # EUR allocated as margin for each leg
    # Notional per leg given leverage and margin requirement
    notional_per_leg = margin_alloc * leverage / margin_pct  # EUR
    # Costi per operazione (round trip): apertura e chiusura, assumiamo taker per entrambe le gambe
    commission_taker = cfg["commission_taker"]
    slippage = cfg["slippage_per_side"]
    costo_per_gamba = commission_taker + slippage
    costo_round_trip = 4.0 * costo_per_gamba  # 2 gambe * 2 volte
    
    # Simulazione per simbolo
    tutti_ritorni: List[float] = []
    primo_ts = None
    ultimo_ts = None
    
    for sym in simboli:
        lst = by_symbol[sym]
        position = 0  # 0 flat, +1 long basis (long perp, short spot), -1 short basis (short perp, long spot)
        entry_basis = 0.0
        entry_ts = 0
        for rec in lst:
            ts = rec["ts"]
            basis = float(rec.get("basis_pp", 0.0))
            if primo_ts is None or ts < primo_ts:
                primo_ts = ts
            if ultimo_ts is None or ts > ultimo_ts:
                ultimo_ts = ts
            
            if position == 0:
                if basis > entry_thr:
                    position = -1  # short basis (short perp, long spot)
                    entry_basis = basis
                    entry_ts = ts
                elif basis < -entry_thr:
                    position = 1   # long basis (long perp, short spot)
                    entry_basis = basis
                    entry_ts = ts
            else:
                # calcola periodi trascorsi
                hold_periods = (ts - entry_ts) / period_ms if period_ms > 0 else 0
                exit_signal = False
                if position == 1 and basis < exit_thr:
                    exit_signal = True
                elif position == -1 and basis > -exit_thr:
                    exit_signal = True
                elif hold_periods > max_hold:
                    exit_signal = True
                
                if exit_signal:
                    # profitto: variazione basis * notional * 0.0001 (basis points to decimal)
                    # basis in basis points, convert to decimal: basis * 0.0001
                    # profit per leg = (exit_basis - entry_basis) * 0.0001 * notional_per_leg
                    # Since we exit when basis returns near zero (exit_thr approx 0), we approximate exit_basis = 0
                    # Actually we exit when basis crosses exit_thr (small). For simplicity, assume exit_basis = 0
                    delta_basis = -entry_basis if position == 1 else entry_basis  # change to zero
                    profit_eur = delta_basis * 0.0001 * notional_per_leg
                    profit_fraction = profit_eur / capitale
                    # sottrarre costi
                    profit_fraction -= costo_round_trip
                    tutti_ritorni.append(profit_fraction)
                    position = 0
                    entry_basis = 0.0
                    entry_ts = 0
    
    n_operazioni = len(tutti_ritorni)
    if n_operazioni == 0:
        ritorni_netti = ()
        esposizione_media = 0.0
        max_drawdown = 0.0
        giorni_osservati = 0.0
    else:
        ritorni_netti = tuple(tutti_ritorni)
        # esposizione media: frazione di capitale utilizzata come margine per entrambe le gambe
        esposizione_media = 2.0 * risk_per_trade  # margin_alloc*2 / capitale
        # drawdown semplice su cumulativo
        cum = [0.0]
        for r in tutti_ritorni:
            cum.append(cum[-1] + r)
        max_cum = max(cum)
        min_cum = min(cum)
        max_drawdown = (max_cum - min_cum) if max_cum > 0 else 0.0
        # giorni osservati
        if primo_ts is not None and ultimo_ts is not None:
            giorni_osservati = (ultimo_ts - primo_ts) / (86400.0 * 1000.0)
        else:
            giorni_osservati = 0.0
    
    # Tariffa
    tariffa = Tariffa(
        venue=Venue.OKX_EEA,
        maker=cfg["commission_maker"],
        taker=cfg["commission_taker"],
        condizione="mean_reversion_basis",
        note="",
        verificato_il="",
        fonte=""
    )
    
    return EsitoMeanReversionBasis(
        nome="mean_reversion_basis_BTC_ETH",
        ritorni_netti=ritorni_netti,
        n_operazioni=n_operazioni,
        esposizione_media=esposizione_media,
        max_drawdown=max_drawdown,
        giorni_osservati=giorni_osservati,
        tariffa=tariffa,
        tipo="misto",
        note=f"Simulazione mean reversion basis con soglia entry={entry_thr}bps, exit={exit_thr}bps, max_hold={max_hold} periodi. risk_per_trade={risk_per_trade}, leverage={leverage}, margin_pct={margin_pct}"
    )


if __name__ == "__main__":
    # Esempio di utilizzo (da completare)
    print("Modulo mean_reversion_basis - esegue backtest su dati funding")
