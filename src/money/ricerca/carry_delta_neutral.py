"""money.ricerca.carry_delta_neutral — Simulatore di carry delta-neutral (spot long / perpetual short) per BTC ed ETH.

Questo modulo implementa la ricerca pre-registrata descritta in
docs/ipotesi/funding_carry_delta_neutral.md e piano dati in
docs/piano_dati.md.

Non esegue ordini live: produce solo dati di backtest e un Esito
da passare a money.cancello per il giudizio.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .. import statistica
from ..costi import Tariffa, get_tariffa, movimento_minimo
from .funding_scan import carica_serie  # reuse existing loader

# ----------------------------------------------------------------------
# Configurazione di default (può essere sovrascritta da file JSON)
# ----------------------------------------------------------------------
DEFAULT_CONFIG = {
    "simboli": ["BTC/USDT", "ETH/USDT"],  # spot symbols
    "perpetual_suffix": ":USDT",           # OKX perpetual USDT margined
    "timeframe_funding": "8h",             # funding every 8h
    "basis_entry_bps": 5.0,                # entrare se |basis| <= questa soglia (basis points)
    "basis_exit_bps": 20.0,                # uscire anticipatamente se |basis| > questa soglia
    "delta_threshold_pct": 10.0,           # max delta deviazione prima di chiudere (percentuale del valore spot)
    "slippage_per_side": 0.0004,           # 0.04% come in altri moduli
    "commission_taker": 0.0005,            # 0.05% taker fee (placeholder, da money.costi)
    "commission_maker": 0.0002,            # 0.02% maker fee
    "leverage_max": 2.0,                   # leva massima sulle gambes
    "margin_init_pct": 0.05,               # margine iniziale richiesto (5% del notional)
    "min_operazioni_train": 30,            # minimo operazioni per considerare il training valido
    "capitale_riferimento_eur": 1000.0,    # capitale di riferimento per il cancello
}


@dataclass(frozen=True)
class TradeRecord:
    """Registro di un singolo trade (apertura/chiusura/riequilibrio)."""
    timestamp: int          # ms UTC
    simbolo: str
    lato: str               # "long" o "short"
    asset: str              # "spot" o "perp"
    prezzo: float           # prezzo di esecuzione (mid + slippage segno)
    size: float             # quantità (BTC o ETH)
    notional: float         # prezzo * size (USD)
    commissione: float      # costo commissione (in USD)
    slippage_costo: float   # costo slippage (in USD)
    totale_costo: float     # commissione + slippage
    funding_accrued: float  # funding guadagnato/pagato durante il periodo (USD) - settato alla chiusura
    pnl: float              # PnL netto della gamba (USD) - settato alla chiusura
    nota: str = ""        # descrizione (apertura, chiusura, riequilibrio)


@dataclass
class PosizioneAperta:
    """Stato di una posizione delta-neutral aperta."""
    simbolo: str
    timestamp_apertura: int
    size: float               # quantità spot (long) e stessa notional perp (short)
    prezzo_spot_apertura: float
    prezzo_perp_apertura: float
    notional: float           # spot prezzo * size (USD)
    margine_impegnato: float  # margine richiesto dalla perp (notional * margin_init_pct)
    trade_apertura_spot: TradeRecord
    trade_apertura_perp: TradeRecord
    # funding accumulato da quando è aperta (aggiornato ad ogni funding)
    funding_accumulato: float = 0.0


@dataclass(frozen=True)
class EsitoCarry:
    """Esito della simulazione, pronto per money.cancello."""
    nome: str
    ritorni_netti: Tuple[float, ...]   # frazione di capitale per operazione (round trip)
    n_operazioni: int
    esposizione_media: float             # frazione media di capitale impegnata per operazione
    max_drawdown: float                  # massimo drawdown frazionale (0-1)
    giorni_osservati: float              # giorni di calendario tra primo e ultimo trade
    tariffa: Tariffa                     # tariffa assunta (usata per criterio 6)
    tipo: str = "misto"                  # tipo di esecuzione (misto per entrata/uscita taker)
    note: str = ""


# ----------------------------------------------------------------------
# Funzioni di caricamento e utilità
# ----------------------------------------------------------------------
def carica_config(config_path: Optional[Path] = None) -> dict:
    """Carica configurazione da JSON, altrimenti usa DEFAULT_CONFIG."""
    config = DEFAULT_CONFIG.copy()
    if config_path and config_path.exists():
        with config_path.open("r", encoding="utf-8") as f:
            user_cfg = json.load(f)
            config.update(user_cfg)
    return config


def normalizza_simbolo_perpetual(simbolo_spot: str, suffix: str) -> str:
    """Converte spot symbol (es. BTC/USDT) in perpetual symbol (BTC/USDT:USDT)."""
    return f"{simbolo_spot}{suffix}"


def calcola_size_da_notional(notional_usd: float, prezzo: float, leva: float, margin_pct: float) -> Tuple[float, float]:
    """Date un notional desiderato in USD, restituisce size e margine richiesto.

    Alla leva L, il capitale necessario per una posizione di notional N è N / L.
    Tuttavia il margine iniziale richiesto dallo exchange è spesso una percentuale del notional.
    Usiamo il massimo tra i due requisiti.
    """
    size = notional_usd / prezzo
    margine_da_leva = notional_usd / leva          # capitale necessario se si usa leva
    margine_da_exchange = notional_usd * margin_pct # margine richiesto dallo exchange
    margine = max(margine_da_leva, margine_da_exchange)
    return size, margine


# ----------------------------------------------------------------------
# Simulazione principale
# ----------------------------------------------------------------------
def simula_carry_delta_neutral(
    data_inizio: str,
    data_fine: str,
    config: Optional[dict] = None,
) -> EsitoCarry:
    """Esegue la simulazione del carry delta-neutral nel periodo [data_inizio, data_fine].

    Parametri
    ---------
    data_inizio, data_fine: stringhe ISO 8601 o timestamp ms (verranno normalizzate da raccoglitore_funding).
    config: dict di configurazione; se None usa DEFAULT_CONFIG.

    Ritorna
    -------
    EsitoCarry con ritorni netti per operazione (round trip) e altre metriche.
    """
    config = carica_config(None if config is None else config)

    # Carica dati funding (riusiamo la funzione esistente)
    # Nota: la funzione carica_serie restituisce un dict per simbolo di SerieFunding
    # ma noi abbiamo bisogno anche di mark/index price. L'attuale raccoglitore_funding
    # salva anche mark e index? In realtà il file funding_xperp.jsonl contiene solo funding e basis_pp.
    # Per ora assumiamo che basis_pp sia sufficiente e che mark/index siano disponibili
    # tramite un altro feed; per semplicità, usiamo il prezzo spot come proxy di entrambi.
    # Questo è una limitazione da migliorare in futuro.
    # Per ora simuliamo usando solo funding e assuming mark==index (basis 0).
    # In futuro, estendere il raccoglitore per salvare mark/index.
    # Dato lo scopo, procediamo con una semplificazione: il basis non è considerato
    # (entrambe le gambe allo stesso prezzo) e l'edge deriva solo dal funding.
    # Questo è comunque utile per testare la pipeline.

    # TODO: sostituire con caricamento reale di mark/index quando disponibile.
    raise NotImplementedError("Simulatore da completare con dati mark/index")


if __name__ == "__main__":
    # Esempio di utilizzo (da completare)
    print("Modulo carry_delta_neutral - da implementare")
