"""Nodo J (catena 2, Hermes) — rotazione a forza relativa sul paniere, giornaliero.

IPOTESI (momentum CROSS-SEZIONALE, non temporale)
=================================================
Non "questo simbolo e' in trend" (nodi C/I/L) ma "QUESTO simbolo e' piu' forte DEGLI ALTRI":
ogni `frequenza` barre si tengono solo le `n_posizioni` coppie col miglior rendimento
`lookback`. Il meccanismo e' diverso dal trend-following: qui si vende chi ha gia' reso per
comprare chi sta rendendo di piu', e il riferimento e' il paniere, non la storia del simbolo.

DOMANDA ONESTA DELLA MISURA
===========================
La rotazione costa un giro completo a ogni cambio (0,550%): con rotazione ogni 20 barre e
3 posizioni il pedaggio annuo sul capitale ruotato e' ~10%. Il segnale cross-sezionale deve
valere piu' di quello — e' esattamente cio' che il criterio 6 misura.

ANTI-LOOK-AHEAD: rendimenti calcolati sulle chiusure FINO alla barra i, scambi all'apertura
di i+1. Ogni finestra di detenzione e' un'Operazione (compra all'apertura, vendi all'apertura).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from ..cancello import Esito
from ..costi import Tariffa
from ..dati import SerieBarre
from .rsi_mean_reversion import (TARIFFA_ASSUNTA, TIPO_ORDINE, SLIPPAGE_PER_LATO,
                                 ESPOSIZIONE, copertura_barre, curva_equity,
                                 esito_da_operazioni, expectancy_lorda as _exp_lorda,
                                 giorni_osservati, pedaggio, ritorno_netto)

INIZIO_STORIA = "2023-12-01"
FINE_STORIA = "2026-09-25"
CONFINE_ADDESTRAMENTO = "2025-09-01"

SIMBOLI: Tuple[str, ...] = (
    "BTC/EUR", "ETH/EUR", "SOL/EUR", "ADA/EUR", "DOGE/EUR", "LTC/EUR", "LINK/EUR",
    "DOT/EUR", "AVAX/EUR", "UNI/EUR",
)

COPERTURA_MINIMA: float = 0.95

GRIGLIA_ADDESTRAMENTO: Tuple[dict, ...] = tuple(
    {"lookback": lb, "n_posizioni": np_, "frequenza": fr}
    for lb in (60, 90, 126)
    for np_ in (2, 3)
    for fr in (20,)
)


@dataclass(frozen=True)
class Config:
    lookback: int
    n_posizioni: int
    frequenza: int

    def __str__(self) -> str:
        return (f"lookback {self.lookback}g | top {self.n_posizioni} | "
                f"ribilancio ogni {self.frequenza}g")

    def chiave(self) -> str:
        return f"l{self.lookback}_n{self.n_posizioni}_f{self.frequenza}"


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
    motivo: str                   # "ribilancio" | "fine serie"


def operazioni_paniere(serie_per_simbolo: dict, config: Config,
                       i_da: int = 0, i_a: Optional[int] = None) -> list:
    """Rotazione su un paniere allineato per indice di barra (stesse date, stesse posizioni).

    Le serie dell'universo primario hanno la stessa lunghezza (stessa data di inizio): il
    ribilancio a indice i usa le chiusure FINO a i e scambia all'apertura di i+1.
    """
    simboli = sorted(serie_per_simbolo)
    serie = [serie_per_simbolo[s] for s in simboli]
    n_barre = min(len(s) for s in serie)
    a = n_barre - 1 if i_a is None else min(i_a, n_barre - 1)
    inizio = max(i_da, config.lookback)
    fuori: list = []
    detenute: list = []          # simboli attualmente in posizione, in ordine di forza
    for i in range(inizio, a):
        if (i - inizio) % config.frequenza == 0:
            forze = []
            for s, serie_s in zip(simboli, serie):
                c_now = serie_s[i].chiusura
                c_then = serie_s[i - config.lookback].chiusura
                if c_then > 0:
                    forze.append((c_now / c_then - 1.0, s))
            forze.sort(reverse=True)
            nuove = [s for _, s in forze[:config.n_posizioni]]
            i_scambio = i + 1
            if i_scambio > a:
                break
            for s in nuove:
                if s not in detenute:
                    detenute.append(s)
                    fuori.append([s, i_scambio, None])   # [simbolo, indice ingresso, uscita]
            detenute = nuove
    # Uscite, dichiarate: chi esce dalla top-N vende all'apertura del ribilancio in cui esce;
    # chi resta fino in fondo vende all'ultima apertura disponibile ("fine serie").
    operazioni: list = []
    for s, i_ing, _ in fuori:
        # trova il primo ribilancio dopo i_ing in cui s non e' piu' in top-N
        serie_s = serie_per_simbolo[s]
        i_out = a
        motivo = "fine serie"
        for j in range(i_ing, a):
            if (j - inizio) % config.frequenza == 0:
                forze = []
                for s2, serie2 in zip(simboli, serie):
                    c_now = serie2[j].chiusura
                    c_then = serie2[j - config.lookback].chiusura
                    if c_then > 0:
                        forze.append((c_now / c_then - 1.0, s2))
                forze.sort(reverse=True)
                if s not in [x for _, x in forze[:config.n_posizioni]]:
                    i_out = j + 1
                    motivo = "ribilancio"
                    break
        i_out = min(i_out, a)
        p_in = serie_s[i_ing].apertura
        p_out = serie_s[i_out].apertura
        operazioni.append(Operazione(
            simbolo=s, indice_ingresso=i_ing, indice_uscita=i_out,
            ts_ingresso=serie_s[i_ing].ts, ts_uscita=serie_s[i_out].ts,
            prezzo_ingresso=p_in, prezzo_uscita=p_out,
            ritorno_lordo=p_out / p_in - 1.0, motivo=motivo))
    return operazioni


def simula(serie_per_simbolo: dict, config: Config, *,
           nome: Optional[str] = None,
           slippage_per_lato: float = SLIPPAGE_PER_LATO,
           tariffa: Optional[Tariffa] = None, tipo: str = TIPO_ORDINE,
           esposizione: float = ESPOSIZIONE,
           i_da: Optional[int] = None, i_a: Optional[int] = None) -> Esito:
    operazioni = operazioni_paniere(serie_per_simbolo, config, i_da=i_da or 0, i_a=i_a)
    # giorni della FINESTRA GIUDICATA (i_da..i_a), non di tutta la serie:
    # gonfiare il denominatore sottostima operazioni/anno ed EUR/anno.
    _da = 0 if i_da is None else i_da
    primo = min((s[_da].ts for s in serie_per_simbolo.values() if len(s) > _da), default=None)
    _a = min(i_a, min(len(s) for s in serie_per_simbolo.values()) - 1) if i_a is not None \
        else max(len(s) for s in serie_per_simbolo.values()) - 1
    ultimo = max((s[min(_a, len(s) - 1)].ts for s in serie_per_simbolo.values() if len(s)), default=None)
    giorni = (ultimo - primo) / 86_400_000.0 if primo is not None and ultimo is not None else 0.0
    return esito_da_operazioni(
        operazioni, giorni, nome or f"rotazione forza relativa [{config}]",
        slippage_per_lato=slippage_per_lato, tariffa=tariffa, tipo=tipo,
        esposizione=esposizione,
        note=(f"config: {config} | paniere: {len(serie_per_simbolo)} | "
              f"finestra giudicata: {giorni:.1f} giorni"))


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


def expectancy_lorda(operazioni) -> Optional[float]:
    return _exp_lorda(operazioni)
