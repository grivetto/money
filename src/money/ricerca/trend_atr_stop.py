"""Nodo P1 (coda_catena, Hermes) — trend giornaliero con trailing stop ATR (chandelier).

IPOTESI (dalla misura, non dalla speranza)
==========================================
Pattern trasversale dei 12 nodi: le famiglie trend hanno expectancy NETTA positiva a fee spot
(I Donchian +2,10%, L momentum assoluto +2,61%) ma DD 48-57% e edge concentrato nel blocco
toro. La domanda di P1: un trailing stop ATR taglia il DD SENZA uccidere l'expectancy.
Confronto obbligatorio contro Donchian puro sulla STESSA finestra: stesso edge, meta' DD.

MECCANICA (chandelier exit, dichiarata)
=======================================
Entrata: chiusura(i) > max(massimi[i-canale .. i-1]) -> compro all'apertura di i+1.
Stop: chandelier = max_alto_posizione - k * ATR14(Wilder), mai decrescente. Per la barra j
lo stop si calcola sui dati FINO a j-1 (nessun futuro intraday); se minimo(j) buca lo stop
si esce allo stop, ma se la barra APRE sotto lo stop si esce all'apertura (gap = caso
peggiore). Nessuna uscita a canale opposto: e' lei che lasciava correre i DD nei nodi I/N.
Una posizione alla volta per simbolo; rientro subito dopo uno stop se il segnale regge.

DATI: USDT-lungo (2019-01-01 -> 2026-09-25, confine 2024-06-01). Tre regimi nel campione.
GRIGLIA dichiarata: 6 configurazioni (k x canale). Conferma finale sulle EUR: altra misura.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from ..cancello import Esito
from ..costi import Tariffa
from ..dati import Barra, SerieBarre
from .rsi_mean_reversion import (TARIFFA_ASSUNTA, TIPO_ORDINE, SLIPPAGE_PER_LATO,
                                 ESPOSIZIONE, esito_da_operazioni, pedaggio,
                                 ritorno_netto)

INIZIO_STORIA = "2019-01-01"
FINE_STORIA = "2026-09-25"
CONFINE_ADDESTRAMENTO = "2024-06-01"

#: Universo dichiarato; la copertura >= 95% dal 2019-01-01 decide chi entra davvero
#: (SOL/AVAX/DOT/UNI su OKX partono nel 2020: se entrano con storia corta falsano il
#: confronto, quindi la regola di copertura e' parte della specifica).
SIMBOLI: Tuple[str, ...] = (
    "BTC/USDT", "ETH/USDT", "ADA/USDT", "DOGE/USDT", "LTC/USDT", "LINK/USDT",
    "DOT/USDT", "UNI/USDT", "AVAX/USDT", "SOL/USDT",
)
COPERTURA_MINIMA: float = 0.95

GRIGLIA_ADDESTRAMENTO: Tuple[dict, ...] = tuple(
    {"canale": c, "k_atr": k}
    for c in (20, 40)
    for k in (2.0, 2.5, 3.0)
)

PERIODO_ATR: int = 14


@dataclass(frozen=True)
class Config:
    canale: int
    k_atr: float

    def __str__(self) -> str:
        return f"breakout {self.canale}g + chandelier {self.k_atr:g}xATR"

    def chiave(self) -> str:
        return f"c{self.canale}_k{self.k_atr:g}"


@dataclass(frozen=True)
class Operazione:
    simbolo: str
    indice_ingresso: int
    indice_uscita: int
    ts_ingresso: int
    ts_uscita: int
    prezzo_ingresso: float
    prezzo_uscita: float
    ritorno_lordo: float
    motivo: str                   # "chandelier" | "chandelier a gap" | "fine serie"


def _atr_wilder(barre: Sequence[Barra], i: int, periodo: int = PERIODO_ATR) -> float:
    """ATR di Wilder FINO alla barra i (inclusa): solo passato, mai futuro."""
    if i < periodo:
        return 0.0
    def tr(j: int) -> float:
        b, prec = barre[j], barre[j - 1]
        return max(b.massimo - b.minimo,
                   abs(b.massimo - prec.chiusura), abs(b.minimo - prec.chiusura))
    # semina semplice sul primo `periodo`, poi smoothing di Wilder fino a i
    atr = math.fsum(tr(j) for j in range(1, periodo + 1)) / periodo
    for j in range(periodo + 1, i + 1):
        atr = (atr * (periodo - 1) + tr(j)) / periodo
    return atr


def operazioni_simbolo(barre: Sequence[Barra], config: Config,
                       i_da: int = 0, i_a: Optional[int] = None) -> list:
    a = len(barre) - 1 if i_a is None else min(i_a, len(barre) - 1)
    fuori: list = []
    i = max(i_da, config.canale, PERIODO_ATR + 1)
    while i < a:
        tetto = max(b.massimo for b in barre[i - config.canale:i])
        if barre[i].chiusura > tetto:
            i_ing = i + 1
            if i_ing > a:
                break
            p_in = barre[i_ing].apertura
            alto_max = p_in
            stop = 0.0
            j_out, p_out, motivo = a, barre[a].apertura, "fine serie"
            for j in range(i_ing, a + 1):
                # chandelier sui dati FINO a j-1: la barra j non conosce il proprio futuro
                atr = _atr_wilder(barre, j - 1)
                stop = max(stop, alto_max - config.k_atr * atr)
                b = barre[j]
                if b.minimo <= stop:
                    if b.apertura <= stop:
                        j_out, p_out, motivo = j, b.apertura, "chandelier a gap"
                    else:
                        j_out, p_out, motivo = j, stop, "chandelier"
                    break
                alto_max = max(alto_max, b.massimo)
            fuori.append(Operazione(
                simbolo="", indice_ingresso=i_ing, indice_uscita=j_out,
                ts_ingresso=barre[i_ing].ts, ts_uscita=barre[j_out].ts,
                prezzo_ingresso=p_in, prezzo_uscita=p_out,
                ritorno_lordo=p_out / p_in - 1.0, motivo=motivo))
            i = j_out + 1
        else:
            i += 1
    return fuori


def simula(serie_per_simbolo: dict, config: Config, *,
           nome: Optional[str] = None,
           slippage_per_lato: float = SLIPPAGE_PER_LATO,
           tariffa: Optional[Tariffa] = None, tipo: str = TIPO_ORDINE,
           esposizione: float = ESPOSIZIONE,
           i_da: Optional[int] = None, i_a: Optional[int] = None) -> Esito:
    operazioni: list = []
    primo, ultimo = None, None
    for simbolo, serie in sorted(serie_per_simbolo.items()):
        if len(serie) < config.canale + 4:
            continue
        da = 0 if i_da is None else i_da
        a = len(serie) - 1 if i_a is None else min(i_a, len(serie) - 1)
        if a <= da:
            continue
        trovate = operazioni_simbolo(serie, config, i_da=da, i_a=a)
        operazioni.extend(
            Operazione(simbolo, o.indice_ingresso, o.indice_uscita, o.ts_ingresso,
                       o.ts_uscita, o.prezzo_ingresso, o.prezzo_uscita, o.ritorno_lordo,
                       o.motivo) for o in trovate)
        if primo is None or ultimo is None:
            primo, ultimo = serie[da].ts, serie[a].ts
        else:
            primo = min(primo, serie[da].ts)
            ultimo = max(ultimo, serie[a].ts)
    giorni = (ultimo - primo) / 86_400_000.0 if primo is not None and ultimo is not None else 0.0
    return esito_da_operazioni(
        operazioni, giorni, nome or f"trend atr stop [{config}]",
        slippage_per_lato=slippage_per_lato, tariffa=tariffa, tipo=tipo,
        esposizione=esposizione,
        note=(f"config: {config} | finestra giudicata: {giorni:.1f} giorni"))


def scegli_config(serie_per_simbolo: dict, *, i_da: int, i_a: int,
                  nome: str, tariffa: Optional[Tariffa] = None):
    tabella: list = []
    for parametri in GRIGLIA_ADDESTRAMENTO:
        config = Config(**parametri)
        esito = simula(serie_per_simbolo, config, nome=f"{nome} [{config.chiave()}]",
                       tariffa=tariffa, i_da=i_da, i_a=i_a)
        exp = math.fsum(esito.ritorni_netti) / len(esito.ritorni_netti) if esito.ritorni_netti else float("nan")
        tabella.append({"config": config, "n": esito.n_operazioni, "expectancy_netta": exp})
    valide = [r for r in tabella if r["n"] >= 30 and not math.isnan(r["expectancy_netta"])]
    if not valide:
        valide = [r for r in tabella if not math.isnan(r["expectancy_netta"])]
    if not valide:
        return Config(**GRIGLIA_ADDESTRAMENTO[0]), tabella
    return max(valide, key=lambda r: r["expectancy_netta"])["config"], tabella


def expectancy_lorda(operazioni: Sequence[Operazione]) -> Optional[float]:
    if not operazioni:
        return None
    return math.fsum(o.ritorno_lordo for o in operazioni) / len(operazioni)
