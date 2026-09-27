"""Nodo I (catena parallela, Hermes) — breakout di canale Donchian sul giornaliero, long-only.

IPOTESI
=======
La tartaruga classica: si compra la forza (chiusura oltre il massimo degli ultimi N giorni,
calcolato SENZA la barra corrente) e si resta dentro finche' la forza regge, uscendo alla
rottura del minimo degli ultimi M giorni. Trend-following puro: poche operazioni, movimenti
grandi — la forma che il criterio 6 (expectancy >= 3x pedaggio = 1,650% netti) premia sul
giornaliero, se il campione toro 2023-12 -> 2026-09 ha davvero avuto trend cavalcabili.

PERCHE' NON E' IL NODO C
========================
Il nodo C (momento 4h) lavora su canale a 4h con orizzonte fisso: tante operazioni piccole,
pedaggio che mangia tutto. Qui: canale giornaliero, NESSUN orizzonte fisso — l'uscita e'
solo la rottura del canale opposto. Il trade-off e' dichiarato: meno operazioni (il vincolo
n >= 30 e' a rischio su 2,8 anni) contro movimenti medi per operazione piu' grandi.

ANTI-LOOK-AHEAD, DICHIARATO
===========================
Canale calcolato sulle N barre PRECEDENTI (i-N .. i-1), segnale sulla chiusura di i,
esecuzione all'apertura di i+1. Le posizioni aperte a fine serie vengono chiuse all'ultima
apertura disponibile: un'operazione non chiusa non entra nei ritorni come se fosse chiusa
(la lezione del profit factor infinito del nodo F).

GRIGLIA dichiarata per intero: 6 configurazioni (N x M). Il cancello non corregge per il
numero di tentativi: il numero sta qui, scritto, prima dei risultati.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from ..cancello import Esito
from ..costi import Tariffa, get_tariffa, movimento_minimo
from ..dati import Barra, SerieBarre

SLIPPAGE_PER_LATO: float = 0.0004
TARIFFA_ASSUNTA: str = "okx_eea_spot"
TIPO_ORDINE: str = "misto"
ESPOSIZIONE: float = 0.25

INIZIO_STORIA = "2023-12-01"
FINE_STORIA = "2026-09-25"
CONFINE_ADDESTRAMENTO = "2025-09-01"

SIMBOLI: Tuple[str, ...] = (
    "BTC/EUR", "ETH/EUR", "SOL/EUR", "ADA/EUR", "DOGE/EUR", "LTC/EUR", "LINK/EUR",
    "DOT/EUR", "AVAX/EUR", "UNI/EUR",
)

COPERTURA_MINIMA: float = 0.95

GRIGLIA_ADDESTRAMENTO: Tuple[dict, ...] = tuple(
    {"canale_entrata": n, "canale_uscita": m}
    for n in (20, 40, 55)
    for m in (10, 20)
)


@dataclass(frozen=True)
class Config:
    canale_entrata: int
    canale_uscita: int

    def __str__(self) -> str:
        return f"entrata {self.canale_entrata}g | uscita {self.canale_uscita}g"

    def chiave(self) -> str:
        return f"e{self.canale_entrata}_u{self.canale_uscita}"


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
    motivo: str                   # "rottura canale" | "fine serie"


def pedaggio(tariffa: Optional[Tariffa] = None, tipo: str = TIPO_ORDINE) -> float:
    return movimento_minimo(tariffa or get_tariffa(TARIFFA_ASSUNTA), tipo)


def ritorno_netto(lordo: float, slippage_per_lato: float = SLIPPAGE_PER_LATO,
                  tariffa: Optional[Tariffa] = None, tipo: str = TIPO_ORDINE) -> float:
    eseguito = (1.0 - slippage_per_lato) * (1.0 + lordo) * (1.0 - slippage_per_lato) - 1.0
    return eseguito - pedaggio(tariffa, tipo)


# --- il motore ------------------------------------------------------------------------------

def operazioni_simbolo(barre: Sequence[Barra], config: Config,
                       i_da: int = 0, i_a: Optional[int] = None) -> list:
    """Breakout di canale su un simbolo. Canale: massimi/minimi delle N barre PRECEDENTI.

    Entrata: chiusura(i) > max(massimi[i-N .. i-1]) -> compro all'apertura di i+1.
    Uscita: chiusura(j-1) < min(minimi[j-1-M .. j-2]) -> vendo all'apertura di j.
    """
    a = len(barre) - 1 if i_a is None else min(i_a, len(barre) - 1)
    n, m = config.canale_entrata, config.canale_uscita
    fuori: list = []
    i = max(i_da, n)
    while i < a:
        tetto = max(b.massimo for b in barre[i - n:i])
        if barre[i].chiusura > tetto:
            i_ing = i + 1
            if i_ing > a:
                break
            p_in = barre[i_ing].apertura
            j_out, p_out, motivo = a, barre[a].apertura, "fine serie"
            for j in range(i_ing + 1, a + 1):
                if j - 1 - m >= 0:
                    pavimento = min(b.minimo for b in barre[j - 1 - m:j - 1])
                    if barre[j - 1].chiusura < pavimento:
                        j_out, p_out, motivo = j, barre[j].apertura, "rottura canale"
                        break
            fuori.append(Operazione(
                simbolo="", indice_ingresso=i_ing, indice_uscita=j_out,
                ts_ingresso=barre[i_ing].ts, ts_uscita=barre[j_out].ts,
                prezzo_ingresso=p_in, prezzo_uscita=p_out,
                ritorno_lordo=p_out / p_in - 1.0, motivo=motivo))
            i = j_out + 1
        else:
            i += 1
    return fuori


# --- da operazioni a Esito (identico al nodo C) ----------------------------------------------

def curva_equity(ritorni: Sequence[float], esposizione: float = ESPOSIZIONE) -> Tuple[float, list]:
    equity, massimo, dd, curva = 1.0, 1.0, 0.0, [1.0]
    for r in ritorni:
        equity *= (1.0 + r * esposizione)
        curva.append(equity)
        massimo = max(massimo, equity)
        if massimo > 0:
            dd = max(dd, 1.0 - equity / massimo)
    return dd, curva


def esito_da_operazioni(operazioni: Sequence[Operazione], giorni: float, nome: str,
                        slippage_per_lato: float = SLIPPAGE_PER_LATO,
                        tariffa: Optional[Tariffa] = None, tipo: str = TIPO_ORDINE,
                        esposizione: float = ESPOSIZIONE, note: str = "") -> Esito:
    ordinate = sorted(operazioni, key=lambda o: (o.ts_ingresso, o.simbolo))
    netti = tuple(ritorno_netto(o.ritorno_lordo, slippage_per_lato, tariffa, tipo)
                  for o in ordinate)
    lordi = tuple(o.ritorno_lordo for o in ordinate)
    dd, _ = curva_equity(netti, esposizione)
    t = tariffa or get_tariffa(TARIFFA_ASSUNTA)
    return Esito(
        nome=nome, ritorni_netti=netti, n_operazioni=len(netti),
        esposizione_media=esposizione, max_drawdown=dd,
        giorni_osservati=float(giorni), tariffa=t, tipo=tipo,
        note=(f"{note} | lordo medio "
              f"{(math.fsum(lordi) / len(lordi) * 100 if lordi else 0.0):+.4f}% | "
              f"pedaggio {pedaggio(t, tipo) * 100:.3f}% + slippage "
              f"{2 * slippage_per_lato * 100:.3f}% ({slippage_per_lato * 100:.3f}%/lato)").strip())


def giorni_osservati(serie: SerieBarre) -> float:
    if len(serie) < 2:
        return 0.0
    return (serie.ultima.ts - serie.prima.ts) / 86_400_000.0


def copertura_barre(serie: SerieBarre) -> float:
    if len(serie) < 2:
        return 0.0
    durata = serie.durata_barra_ms
    attese = (serie.ultima.ts - serie.prima.ts) // durata + 1
    return len(serie) / attese if attese > 0 else 0.0


def simula(serie_per_simbolo: dict, config: Config, *,
           nome: Optional[str] = None,
           slippage_per_lato: float = SLIPPAGE_PER_LATO,
           tariffa: Optional[Tariffa] = None, tipo: str = TIPO_ORDINE,
           esposizione: float = ESPOSIZIONE,
           i_da: Optional[int] = None, i_a: Optional[int] = None) -> Esito:
    operazioni: list = []
    primo, ultimo = None, None
    usati = 0
    for simbolo, serie in sorted(serie_per_simbolo.items()):
        if len(serie) < config.canale_entrata + 4:
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
        usati += 1
        if primo is None or ultimo is None:
            primo, ultimo = serie[da].ts, serie[a].ts
        else:
            primo = min(primo, serie[da].ts)
            ultimo = max(ultimo, serie[a].ts)
    giorni = (ultimo - primo) / 86_400_000.0 if primo is not None and ultimo is not None else 0.0
    return esito_da_operazioni(
        operazioni, giorni, nome or f"donchian breakout [{config}]",
        slippage_per_lato=slippage_per_lato, tariffa=tariffa, tipo=tipo,
        esposizione=esposizione,
        note=(f"config: {config} | simboli usati: {usati} | "
              f"finestra giudicata: {giorni:.1f} giorni ({giorni / 365.0:.2f} anni)"))


def scegli_config(serie_per_simbolo: dict, *, i_da: int, i_a: int,
                  nome: str, tariffa: Optional[Tariffa] = None):
    tabella: list = []
    for parametri in GRIGLIA_ADDESTRAMENTO:
        config = Config(**parametri)
        esito = simula(serie_per_simbolo, config, nome=f"{nome} [{config.chiave()}]",
                       tariffa=tariffa, i_da=i_da, i_a=i_a)
        exp = math.fsum(esito.ritorni_netti) / len(esito.ritorni_netti) if esito.ritorni_netti else float("nan")
        tabella.append({"config": config, "n": esito.n_operazioni, "expectancy_netta": exp})
    valide = [r for r in tabella if r["n"] >= 10 and not math.isnan(r["expectancy_netta"])]
    if not valide:
        return Config(**GRIGLIA_ADDESTRAMENTO[0]), tabella
    return max(valide, key=lambda r: r["expectancy_netta"])["config"], tabella


def expectancy_lorda(operazioni: Sequence[Operazione]) -> Optional[float]:
    if not operazioni:
        return None
    return math.fsum(o.ritorno_lordo for o in operazioni) / len(operazioni)
