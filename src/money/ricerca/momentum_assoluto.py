"""Nodo L (catena 2, Hermes) — momentum ASSOLUTO sul giornaliero (Antonacci), long-only.

IPOTESI (time-series momentum, diverso dal breakout)
====================================================
Non si compra la rottura di un canale (nodi C/I): si sta lunghi SOLO se il rendimento degli
ultimi `lookback` giorni e' positivo, altrimenti si sta fermi. E' un filtro di esposizione,
non un segnale di forza relativa: il mercato decide QUANDO stare dentro, non COSA comprare.
In un campione con un grande ribasso, questa regola dovrebbe stare fuori nei tratti peggiori:
il suo valore, se esiste, e' il drawdown ridotto — e il criterio 4 (maxDD <= 25%) e' quello
che il nodo I ha fallito con il 56,8%.

ANTI-LOOK-AHEAD: rendimento calcolato sulle chiusure FINO a i, scambio all'apertura di i+1.
Ogni tratto lungo continuo e' un'Operazione.
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

INIZIO_STORIA = "2023-12-01"
FINE_STORIA = "2026-09-25"
CONFINE_ADDESTRAMENTO = "2025-09-01"
SIMBOLI: Tuple[str, ...] = (
    "BTC/EUR", "ETH/EUR", "SOL/EUR", "ADA/EUR", "DOGE/EUR", "LTC/EUR", "LINK/EUR",
    "DOT/EUR", "AVAX/EUR", "UNI/EUR",
)
COPERTURA_MINIMA: float = 0.95

GRIGLIA_ADDESTRAMENTO: Tuple[dict, ...] = tuple(
    {"lookback": lb} for lb in (60, 90, 126)
)


@dataclass(frozen=True)
class Config:
    lookback: int

    def __str__(self) -> str:
        return f"long se ritorno {self.lookback}g > 0, altrimenti fermo"

    def chiave(self) -> str:
        return f"ma{self.lookback}"


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
    motivo: str                   # "momentum spento" | "fine serie"


def operazioni_simbolo(barre: Sequence[Barra], config: Config,
                       i_da: int = 0, i_a: Optional[int] = None) -> list:
    a = len(barre) - 1 if i_a is None else min(i_a, len(barre) - 1)
    fuori: list = []
    i = max(i_da, config.lookback)
    aperto: Optional[int] = None
    while i < a:
        r_lb = barre[i].chiusura / barre[i - config.lookback].chiusura - 1.0
        if aperto is None and r_lb > 0:
            aperto = i + 1
        elif aperto is not None and r_lb <= 0:
            p_in, p_out = barre[aperto].apertura, barre[i + 1].apertura
            fuori.append(Operazione(
                simbolo="", indice_ingresso=aperto, indice_uscita=i + 1,
                ts_ingresso=barre[aperto].ts, ts_uscita=barre[i + 1].ts,
                prezzo_ingresso=p_in, prezzo_uscita=p_out,
                ritorno_lordo=p_out / p_in - 1.0, motivo="momentum spento"))
            aperto = None
        i += 1
    if aperto is not None and aperto <= a:
        p_in, p_out = barre[aperto].apertura, barre[a].apertura
        fuori.append(Operazione(
            simbolo="", indice_ingresso=aperto, indice_uscita=a,
            ts_ingresso=barre[aperto].ts, ts_uscita=barre[a].ts,
            prezzo_ingresso=p_in, prezzo_uscita=p_out,
            ritorno_lordo=p_out / p_in - 1.0, motivo="fine serie"))
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
        if len(serie) < config.lookback + 4:
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
        operazioni, giorni, nome or f"momentum assoluto [{config}]",
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
        return Config(**GRIGLIA_ADDESTRAMENTO[0]), tabella
    return max(valide, key=lambda r: r["expectancy_netta"])["config"], tabella
