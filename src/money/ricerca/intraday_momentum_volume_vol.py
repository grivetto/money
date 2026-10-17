"""money.ricerca.intraday_momentum_volume_vol — Simulatore di momentum intraday condizionato da volume e volatilità.

Questo modulo implementa la ricerca pre-registrata descritta in
docs/ipotesi/intraday_momentum_volume_vol_BTC_ETH.md e piano dati in
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


class EsitoIntradayMomentum(Esito):
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
    "simboli": ["BTC/USDT", "ETH/USDT"],
    "timeframe": "5m",
    "volume_entry_multiplier": 2.0,
    "volatility_entry_multiplier": 1.2,
    "atr_period": 14,
    "volume_ma_period": 20,
    "holding_periods": 4,  # numero di periodi di timeframe da tenere
    "slippage_per_side": 0.0004,
    "commission_taker": 0.0005,
    "commission_maker": 0.0002,
    "leverage_max": 2.0,
    "margin_init_pct": 0.05,
    "risk_per_trade_pct": 0.01,  # 1% del capitale da allocare come margine per trade
    "min_operazioni_train": 30,
    "capitale_riferimento_eur": 1000.0,
}


def simula_intraday_momentum_volume_vol(
    data_inizio: str,
    data_fine: str,
    config: Optional[dict] = None,
) -> EsitoIntradayMomentum:
    """Esegue una semplificata strategia di momentum basata su volume e ATR."""
    cfg = carica_config(config)
    
    # Percorso dati OHLCV
    data_path = Path("/home/sergio/money/data/ohlcv_xperp.jsonl")
    if not data_path.exists():
        raise FileNotFoundError(f"Dati OHLCV non trovati: {data_path}")
    
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
    simboli = cfg["simboli"]  # spot symbols es. BTC/USDT
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
    volume_mult = cfg["volume_entry_multiplier"]
    vol_mult = cfg["volatility_entry_multiplier"]
    atr_period = cfg["atr_period"]
    vol_ma_period = cfg["volume_ma_period"]
    holding_periods = cfg["holding_periods"]
    slippage = cfg["slippage_per_side"]
    commission_taker = cfg["commission_taker"]
    commission_maker = cfg["commission_maker"]
    leverage = cfg["leverage_max"]
    margin_pct = cfg["margin_init_pct"]
    risk_per_trade = cfg["risk_per_trade_pct"]
    capitale = cfg["capitale_riferimento_eur"]
    
    # Precalcoliamo medie mobili e ATR per ogni simbolo
    tutti_ritorni: List[float] = []
    primo_ts = None
    ultimo_ts = None
    
    for sym in simboli:
        lst = by_symbol[sym]
        if len(lst) < max(atr_period, vol_ma_period) + 1:
            continue  # insufficienti per indicatori
        # Calcoliamo close precedenti per TR
        closes = [float(r["close"]) for r in lst]
        highs = [float(r["high"]) for r in lst]
        lows = [float(r["low"]) for r in lst]
        volumes = [float(r["volume"]) for r in lst]
        opens = [float(r["open"]) for r in lst]
        # True Range
        tr = [0.0] * len(lst)
        for i in range(len(lst)):
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - (closes[i-1] if i>0 else closes[i]))
            lc = abs(lows[i] - (closes[i-1] if i>0 else closes[i]))
            tr[i] = max(hl, hc, lc)
        # ATR media mobile semplice
        atr = [0.0] * len(lst)
        for i in range(len(lst)):
            if i < atr_period:
                atr[i] = sum(tr[:i+1]) / (i+1)
            else:
                atr[i] = sum(tr[i-atr_period+1:i+1]) / atr_period
        # Volume media mobile semplice
        vol_ma = [0.0] * len(lst)
        for i in range(len(lst)):
            if i < vol_ma_period:
                vol_ma[i] = sum(volumes[:i+1]) / (i+1)
            else:
                vol_ma[i] = sum(volumes[i-vol_ma_period+1:i+1]) / vol_ma_period
        
        position = 0  # 0 flat, 1 long, -1 short
        entry_price = 0.0
        entry_ts = 0
        
        for i in range(len(lst)):
            ts = lst[i]["ts"]
            close = closes[i]
            volume = volumes[i]
            open_price = opens[i]
            if primo_ts is None or ts < primo_ts:
                primo_ts = ts
            if ultimo_ts is None or ts > ultimo_ts:
                ultimo_ts = ts
            
            if position == 0:
                # condizioni di ingresso: volume spike
                if volume > volume_mult * vol_ma[i]:
                    # direzione dal ritorno intraday (close - open)
                    ret = (close - open_price) / open_price if open_price != 0 else 0.0
                    if ret > 0:
                        position = 1
                        entry_price = close
                        entry_ts = ts
                    elif ret < 0:
                        position = -1
                        entry_price = close
                        entry_ts = ts
            else:
                # check exit: holding period exceeded or reversal signal
                periods_held = (ts - entry_ts) // (5*60*1000)  # assuming 5m timeframe in ms
                exit_signal = False
                if periods_held >= holding_periods:
                    exit_signal = True
                else:
                    # reversal: volume spike in opposite direction
                    if volume > volume_mult * vol_ma[i]:
                        ret = (close - open_price) / open_price if open_price != 0 else 0.0
                        if position == 1 and ret < 0:
                            exit_signal = True
                        elif position == -1 and ret > 0:
                            exit_signal = True
                if exit_signal:
                    # compute PnL fraction of capitale
                    # price change from entry to exit
                    price_change_pct = (close - entry_price) / entry_price if entry_price != 0 else 0.0
                    # gross return = price_change_pct * position (since long profits if price up)
                    gross = price_change_pct * position
                    # margin allocated per trade
                    margin_alloc = capitale * risk_per_trade
                    # notional given leverage and margin requirement
                    notional = margin_alloc * leverage / margin_pct
                    # profit in EUR = gross * notional
                    profit_eur = gross * notional
                    profit_fraction = profit_eur / capitale
                    # subtract costs: round trip commission + slippage (assume taker)
                    cost_per_trade = 2.0 * (commission_taker + slippage)  # apertura e chiusura
                    profit_fraction -= cost_per_trade
                    tutti_ritorni.append(profit_fraction)
                    position = 0
                    entry_price = 0.0
                    entry_ts = 0
        # If still open at end, close at last close
        if position != 0:
            close = closes[-1]
            price_change_pct = (close - entry_price) / entry_price if entry_price != 0 else 0.0
            gross = price_change_pct * position
            margin_alloc = capitale * risk_per_trade
            notional = margin_alloc * leverage / margin_pct
            profit_eur = gross * notional
            profit_fraction = profit_eur / capitale
            cost_per_trade = 2.0 * (commission_taker + slippage)
            profit_fraction -= cost_per_trade
            tutti_ritorni.append(profit_fraction)
            position = 0
    
    n_operazioni = len(tutti_ritorni)
    if n_operazioni == 0:
        ritorni_netti = ()
        esposizione_media = 0.0
        max_drawdown = 0.0
        giorni_osservati = 0.0
    else:
        ritorni_netti = tuple(tutti_ritorni)
        # esposizione media: frazione di capitale utilizzata come margine per trade (media)
        esposizione_media = risk_per_trade  # margin_alloc / capitale
        # drawdown semplice
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
        condizione="intraday_momentum_volume_vol",
        note="",
        verificato_il="",
        fonte=""
    )
    
    return EsitoIntradayMomentum(
        nome="intraday_momentum_volume_vol_BTC_ETH",
        ritorni_netti=ritorni_netti,
        n_operazioni=n_operazioni,
        esposizione_media=esposizione_media,
        max_drawdown=max_drawdown,
        giorni_osservati=giorni_osservati,
        tariffa=tariffa,
        tipo="misto",
        note=f"Simulazione momentum volume/vol con volume_mult={volume_mult}, vol_mult={vol_mult}, holding={holding_periods} periodi. risk_per_trade={risk_per_trade}, leverage={leverage}, margin_pct={margin_pct}"
    )


if __name__ == "__main__":
    print("Modulo intraday_momentum_volume_vol - esegue backtest su dati OHLCV")
