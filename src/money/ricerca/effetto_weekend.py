"""Nodo K (catena 2, Hermes) — effetto weekend sul giornaliero, long-only.

IPOTESI (anomalia di calendario)
================================
In letteratura crypto il fine settimana ha un drift medio positivo (minore copertura
istituzionale, flussi retail). La regola e' meccanica: si compra all'apertura del sabato
UTC e si vende all'apertura del mercoledi' (o giovedi'). Nessun parametro adattivo, nessun
indicatore: se l'anomalia esiste, e' una proprieta' del calendario, non di una curva
parametrica — il candidato piu' "non fittabile" del progetto.

DOMANDA ONESTA: il drift weekend medio e' storicamente ~0,2-1% per evento; il pedaggio e'
0,550% + slippage. Il criterio 6 (3x) chiede +1,65% netto a giro: e' la misura che decide,
non la letteratura.

ANTI-LOOK-AHEAD: il sabato e' noto a priori (calendario), ingresso all'apertura del sabato,
uscita all'apertura del giorno di uscita. Barre con timestamp di apertura UTC (convenzione
dati): il giorno della settimana si legge dal timestamp, senza nessun prezzo futuro.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
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
    {"giorno_uscita": g} for g in (2, 3)     # weekday(): 2 = mercoledi', 3 = giovedi'
)


def _giorno_settimana(ts_ms: int) -> int:
    """0 = lunedi' ... 6 = domenica, dal timestamp UTC dell'APERTURA della barra."""
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).weekday()


@dataclass(frozen=True)
class Config:
    giorno_uscita: int

    def __str__(self) -> str:
        nome = {2: "mercoledi'", 3: "giovedi'"}[self.giorno_uscita]
        return f"compra sabato -> vendi {nome}"

    def chiave(self) -> str:
        return f"wk_u{self.giorno_uscita}"


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
    motivo: str                   # "calendario" | "fine serie"


def operazioni_simbolo(barre: Sequence[Barra], config: Config,
                       i_da: int = 0, i_a: Optional[int] = None) -> list:
    a = len(barre) - 1 if i_a is None else min(i_a, len(barre) - 1)
    fuori: list = []
    i = max(i_da, 0)
    while i <= a:
        if _giorno_settimana(barre[i].ts) == 5:          # sabato UTC
            # cerca la prima barra il cui giorno sia quello di uscita
            j = i + 1
            while j <= a and _giorno_settimana(barre[j].ts) != config.giorno_uscita:
                j += 1
            if j > a:
                j, motivo = a, "fine serie"
            else:
                motivo = "calendario"
            p_in, p_out = barre[i].apertura, barre[j].apertura
            fuori.append(Operazione(
                simbolo="", indice_ingresso=i, indice_uscita=j,
                ts_ingresso=barre[i].ts, ts_uscita=barre[j].ts,
                prezzo_ingresso=p_in, prezzo_uscita=p_out,
                ritorno_lordo=p_out / p_in - 1.0, motivo=motivo))
            i = j + 1
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
        operazioni, giorni, nome or f"effetto weekend [{config}]",
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
