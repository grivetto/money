"""Nodo O (catena 2, Hermes) — reversal a 2 giorni, orizzonte cortissimo, long-only.

IPOTESI (reversal ultra-breve, documentato in equity, da verificare in crypto)
=============================================================================
Dopo `n_giu` chiusure consecutive in calo, il giorno seguente tende al rimbalzo: microstruttura
(venditori a mercato esauriti) piu' che "valore". E' la famiglia con piu' operazioni del
progetto: orizzonte di `tenuta` giorni, decine di eventi per simbolo. Il costo e' dichiarato
fatale in partenza se il rimbalzo medio e' sotto il pedaggio: 0,550% + slippage su una
tenuta di 2-4 giorni vuole dire chiedere un rimbalzo medio > 1,65% netto a giro.

PERCHE' NON E' IL NODO H: H usa un oscillatore (RSI) con uscita a soglia e stop tempo di 20
giorni — swing trading. Qui: trigger = sequenza di segni (tutto o niente), orizzonte 2-4
giorni, nessun indicatore. Statisticamente e' un test sui RUN (sequenze), non sui livelli.

ANTI-LOOK-AHEAD: la sequenza si misura sulle chiusure FINO a i-1, ingresso all'apertura di i,
uscita all'apertura di i+tenuta. Nessuna sovrapposizione: una posizione alla volta.
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
    {"n_giu": n, "tenuta": t}
    for n in (2, 3)
    for t in (2, 4)
)


@dataclass(frozen=True)
class Config:
    n_giu: int
    tenuta: int

    def __str__(self) -> str:
        return f"dopo {self.n_giu} chiusure in calo -> tieni {self.tenuta}g"

    def chiave(self) -> str:
        return f"g{self.n_giu}_t{self.tenuta}"


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
    motivo: str                   # "tenuta" | "fine serie"


def operazioni_simbolo(barre: Sequence[Barra], config: Config,
                       i_da: int = 0, i_a: Optional[int] = None) -> list:
    a = len(barre) - 1 if i_a is None else min(i_a, len(barre) - 1)
    fuori: list = []
    i = max(i_da, config.n_giu)
    while i <= a:
        if all(barre[i - k].chiusura < barre[i - k - 1].chiusura
               for k in range(config.n_giu)):
            i_ing = i
            j_out = min(i_ing + config.tenuta, a)
            motivo = "tenuta" if j_out == i_ing + config.tenuta else "fine serie"
            p_in, p_out = barre[i_ing].apertura, barre[j_out].apertura
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
        if len(serie) < config.n_giu + config.tenuta + 2:
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
        operazioni, giorni, nome or f"reversal 2 giorni [{config}]",
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
