"""Nodo P10 — momentum CROSS-SEZIONALE long/flat (rotazione top-k), giornaliero, USDT-lungo.

IPOTESI (diversa dal momentum ASSOLUTO del nodo L)
==================================================
Il nodo L decide QUANDO stare dentro (rendimento del singolo simbolo > 0). Qui si decide
COSA tenere: alla chiusura di ogni barra si ordinano i simboli per rendimento relativo
`r = chiusura(i)/chiusura(i-L) - 1` e si tiene il miglior `k`. E' selezione tra strumenti,
non timing del singolo: il riferimento e' il paniere, e non esiste un secondo motore che
guardi la storia del solo simbolo.

MECCANICA (anti-lookahead per costruzione)
==========================================
- Ranking alla CHIUSURA della barra `i` sulle chiusure FINO a `i` (mai oltre). La chiusura
  di `i` esiste in produzione solo quando la barra e' chiusa: e' il momento della decisione.
- Ribilanciamento ogni `R` barre: composizione target = top-`k` per `r`.
- Esecuzione: SOLO i cambi di composizione all'APERTURA della barra `i+1` (escono i
  venduti, entrano i comprati). Chi era in paniere e resta NON viene toccato: niente churn
  artificiale, e la sua operazione resta una sola (un solo giro di costi).
- Allocazione: `equity / k` per posizione, equipesata e dichiarata. Si realizza con l'hook
  `esposizione_per_op` del motore di portafoglio (`portafoglio.py`, commit e6ff1c7f): il
  motore applica la frazione al capitale del momento, come farebbe un bot reale.
- Costi: `money.costi` per il pedaggio (default `okx_eea_spot`, misto) + 4 bp di slippage
  per lato, esattamente come Donchian/P2. Scenario secondario `okx_eea_con_perp`.
  Nessuna leva, cassa vincolante, mai short.
- Con meno di `k` candidati validi si tengono i disponibili; con 0 candidati si e' flat.
  In entrambi i casi l'allocazione resta `equity / k` (dichiarato): il capitale non
  investito resta in cassa, non viene spalmato sui pochi superstiti.

COSA NON DIMOSTRA
=================
Questo modulo NON giudica e NON sceglie la configurazione: produce operazioni e le fa
girare sul motore di portafoglio. La griglia e' dichiarata in `GRIGLIA_ADDESTRAMENTO`
(8 varianti, PRIMA dei numeri) e il verdetto resta di `money.cancello`.

CONVENZIONE DI FINE FINESTRA
============================
L'ultima barra e' riservata alla liquidazione finale ("fine serie", all'apertura). Un
ingresso sull'ultima barra non avrebbe nemmeno una barra di detenzione e pagherebbe costi
per zero movimento: non viene eseguito. E' una scelta dichiarata, non un buco.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..costi import Tariffa, get_tariffa, movimento_minimo
from .portafoglio import EsitoPortafoglio, backtest_portafoglio
from .rsi_mean_reversion import (TARIFFA_ASSUNTA, TIPO_ORDINE, SLIPPAGE_PER_LATO,
                                 ritorno_netto)

# --- dati e assunzioni: le stesse degli altri nodi della catena ----------------------------

#: La spec P10 usa l'universo USDT-lungo (stessa finestra di P3/P11): eea.okx.com serve
#: gli alt/USDT solo dal ~2020-06, quindi dal 2020-10-01 il paniere e' completo.
INIZIO_STORIA = "2020-10-01"
FINE_STORIA = "2026-09-25"
CONFINE_ADDESTRAMENTO = "2024-06-01"

SIMBOLI: Tuple[str, ...] = (
    "BTC/USDT", "ETH/USDT", "ADA/USDT", "DOGE/USDT", "LTC/USDT", "LINK/USDT",
    "DOT/USDT", "UNI/USDT", "AVAX/USDT", "SOL/USDT",
)
COPERTURA_MINIMA: float = 0.95

#: Tariffa secondaria dichiarata dalla spec (conto con X-Perps).
TARIFFA_SECONDARIA: str = "okx_eea_con_perp"

CAPITALE_DEFAULT: float = 1000.0

#: Griglia dichiarata PRIMA dei numeri: {k: 2, 3} x {L: 60, 120} x {R: 7, 14} = 8.
GRIGLIA_ADDESTRAMENTO: Tuple[dict, ...] = tuple(
    {"k": k, "lookback": lookback, "ribilancio": ribilancio}
    for k in (2, 3)
    for lookback in (60, 120)
    for ribilancio in (7, 14)
)


@dataclass(frozen=True)
class Config:
    """Una configurazione della griglia: top-`k` ogni `ribilancio` barre, momentum `lookback`."""

    k: int
    lookback: int
    ribilancio: int

    def __post_init__(self) -> None:
        if self.k <= 0:
            raise ValueError(f"k dev'essere >= 1, ricevuto {self.k}")
        if self.lookback < 1:
            raise ValueError(f"lookback dev'essere >= 1, ricevuto {self.lookback}")
        if self.ribilancio < 1:
            raise ValueError(f"ribilancio dev'essere >= 1, ricevuto {self.ribilancio}")

    def __str__(self) -> str:
        return (f"top {self.k} | momentum {self.lookback}g | "
                f"ribilancio ogni {self.ribilancio}g")

    def chiave(self) -> str:
        return f"k{self.k}_l{self.lookback}_r{self.ribilancio}"


@dataclass(frozen=True)
class Operazione:
    """Un tratto lungo continuo di un simbolo: dall'ingresso all'uscita dal paniere.

    `motivo` descrive l'uscita: "ribilancio" (il simbolo e' uscito dal top-k) oppure
    "fine serie" (liquidazione all'ultima barra della finestra).
    """

    simbolo: str
    indice_ingresso: int
    indice_uscita: int
    ts_ingresso: int
    ts_uscita: int
    prezzo_ingresso: float
    prezzo_uscita: float
    ritorno_lordo: float
    motivo: str


# --- ranking e composizione: il cuore cross-sezionale --------------------------------------

def rendimento_momentum(serie: Sequence[Any], i: int, lookback: int) -> Optional[float]:
    """`r = chiusura(i)/chiusura(i-L) - 1` sulle sole barre FINO a `i` (nessun futuro).

    Ritorna `None` se la storia non basta o se i prezzi non sono utilizzabili: un simbolo
    senza base positiva non e' un candidato, non un candidato con rendimento zero.
    """
    if i < lookback or i >= len(serie):
        return None
    c_now = serie[i].chiusura
    c_then = serie[i - lookback].chiusura
    if not (math.isfinite(c_now) and math.isfinite(c_then)):
        return None
    if c_then <= 0.0 or c_now <= 0.0:
        return None
    return c_now / c_then - 1.0


def composizione_target(serie_per_simbolo: Dict[str, Sequence[Any]], i: int,
                        config: Config) -> List[str]:
    """I migliori `k` simboli per momentum alla CHIUSURA di `i` (solo dati fino a `i`).

    Ordine: rendimento decrescente; a parita' di rendimento, simbolo crescente (determinismo,
    niente dipendenza dall'ordine del dizionario). Meno di `k` candidati validi = si tengono
    i disponibili; zero candidati = lista vuota (flat).
    """
    forze: List[Tuple[float, str]] = []
    for simbolo in sorted(serie_per_simbolo):
        r = rendimento_momentum(serie_per_simbolo[simbolo], i, config.lookback)
        if r is not None:
            forze.append((r, simbolo))
    forze.sort(key=lambda coppia: (-coppia[0], coppia[1]))
    return [simbolo for _, simbolo in forze[:config.k]]


# --- il motore: composizione -> operazioni ---------------------------------------------------

def operazioni_paniere(serie_per_simbolo: Dict[str, Sequence[Any]], config: Config,
                       i_da: int = 0, i_a: Optional[int] = None) -> List[Operazione]:
    """Le operazioni della rotazione top-k, in indici di barra del paniere allineato.

    Le serie sono indicizzate per POSIZIONE (stesse date, come gli altri nodi a paniere).
    La finestra giudicata e' `[i_da, i_a]`; il primo ribilanciamento e' a
    `max(i_da, lookback)` e poi ogni `ribilancio` barre. Decisione alla chiusura di `i`,
    esecuzione all'apertura di `i+1`. Chi resta nel target non produce nessuna operazione:
    la sua posizione continua.
    """
    simboli = sorted(serie_per_simbolo)
    if not simboli:
        return []
    n_barre = min(len(serie_per_simbolo[s]) for s in simboli)
    if n_barre < 2:
        return []
    a = n_barre - 1 if i_a is None else min(i_a, n_barre - 1)
    inizio = max(i_da, config.lookback)

    detenute: Dict[str, Tuple[int, float]] = {}   # simbolo -> (indice ingresso, prezzo ingresso)
    operazioni: List[Operazione] = []

    i = inizio
    # L'ultima barra e' riservata alla liquidazione finale: si decide solo se all'ingresso
    # (i+1) resta almeno una barra di detenzione PRIMA dell'ultima. Vedi docstring di modulo.
    while i + 1 < a:
        target = composizione_target(serie_per_simbolo, i, config)
        i_scambio = i + 1

        # USCITE: chi era in paniere e non e' piu' nel target, all'apertura di i+1.
        for simbolo in sorted(detenute):
            if simbolo in target:
                continue
            indice_ingresso, prezzo_ingresso = detenute.pop(simbolo)
            serie = serie_per_simbolo[simbolo]
            prezzo_uscita = serie[i_scambio].apertura
            operazioni.append(Operazione(
                simbolo=simbolo, indice_ingresso=indice_ingresso, indice_uscita=i_scambio,
                ts_ingresso=serie[indice_ingresso].ts, ts_uscita=serie[i_scambio].ts,
                prezzo_ingresso=prezzo_ingresso, prezzo_uscita=prezzo_uscita,
                ritorno_lordo=prezzo_uscita / prezzo_ingresso - 1.0, motivo="ribilancio"))

        # INGRESSI: chi entra nel target e non era in paniere, all'apertura di i+1.
        for simbolo in target:
            if simbolo in detenute:
                continue
            serie = serie_per_simbolo[simbolo]
            prezzo_ingresso = serie[i_scambio].apertura
            detenute[simbolo] = (i_scambio, prezzo_ingresso)

        i += config.ribilancio

    # Liquidazione finale: chi e' ancora in paniere esce all'apertura dell'ultima barra.
    for simbolo in sorted(detenute):
        indice_ingresso, prezzo_ingresso = detenute[simbolo]
        serie = serie_per_simbolo[simbolo]
        prezzo_uscita = serie[a].apertura
        operazioni.append(Operazione(
            simbolo=simbolo, indice_ingresso=indice_ingresso, indice_uscita=a,
            ts_ingresso=serie[indice_ingresso].ts, ts_uscita=serie[a].ts,
            prezzo_ingresso=prezzo_ingresso, prezzo_uscita=prezzo_uscita,
            ritorno_lordo=prezzo_uscita / prezzo_ingresso - 1.0, motivo="fine serie"))

    return operazioni


# --- aggancio al motore di portafoglio --------------------------------------------------------

def pedaggio(tariffa: Optional[Tariffa] = None, tipo: str = TIPO_ORDINE) -> float:
    """Il pedaggio di un giro, dalla tariffa (default `okx_eea_spot`). Riusa `money.costi`."""
    return movimento_minimo(tariffa or get_tariffa(TARIFFA_ASSUNTA), tipo)


def netto_fn(tariffa: Optional[Tariffa] = None, tipo: str = TIPO_ORDINE,
             slippage_per_lato: float = SLIPPAGE_PER_LATO) -> Callable[[float], float]:
    """Il `netto_fn` del motore di portafoglio: fee di `money.costi` + slippage per lato.

    Una sola verita' sui costi: e' la stessa funzione dei nodi Donchian/P2/P3 (importata da
    `rsi_mean_reversion`, che a sua volta legge `money.costi`).
    """
    def netto(lordo: float) -> float:
        return ritorno_netto(lordo, slippage_per_lato=slippage_per_lato,
                             tariffa=tariffa, tipo=tipo)
    return netto


def esposizione_per_op(config: Config) -> Callable[[str, Any], float]:
    """L'hook `esposizione_per_op`: `equity / k` per posizione, equipesato e dichiarato.

    Ritorna una frazione COSTANTE `1/k`: il motore la moltiplica per l'equity al momento
    dell'ingresso. Con meno di `k` posizioni il capitale non usato resta in cassa.
    """
    frazione = 1.0 / config.k
    return lambda simbolo, op: frazione


def backtest(serie_per_simbolo: Dict[str, Sequence[Any]], config: Config, *,
             capitale: float = CAPITALE_DEFAULT, tariffa: Optional[Tariffa] = None,
             tipo: str = TIPO_ORDINE, slippage_per_lato: float = SLIPPAGE_PER_LATO,
             i_da: int = 0, i_a: Optional[int] = None) -> EsitoPortafoglio:
    """Gira la rotazione top-k sul motore di portafoglio (MTM, cassa vincolante, no leva).

    `serie_per_simbolo` e' la finestra da giudicare (il motore di portafoglio la marca per
    intero): passare la finestra gia' ritagliata. Gli indici di `operazioni_paniere`
    provengono dalla serie piena via `i_da`/`i_a`; il motore di portafoglio allinea per ts.
    """
    operazioni = operazioni_paniere(serie_per_simbolo, config, i_da=i_da, i_a=i_a)
    per_simbolo: Dict[str, List[Operazione]] = {}
    for o in operazioni:
        per_simbolo.setdefault(o.simbolo, []).append(o)
    return backtest_portafoglio(
        serie_per_simbolo, per_simbolo,
        esposizione=1.0 / config.k,
        netto_fn=netto_fn(tariffa=tariffa, tipo=tipo, slippage_per_lato=slippage_per_lato),
        capitale=capitale,
        esposizione_per_op=esposizione_per_op(config))
