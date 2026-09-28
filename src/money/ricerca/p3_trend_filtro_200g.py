"""Nodo P3 (coda_catena) — trend con filtro di regime SMA200, long-only spot.

IPOTESI (dal filone P1/P5, non dalla speranza)
==============================================
I 13 nodi misurati finora: l'edge trend esiste (Donchian 10 majors: expectancy +7,99%
netta per operazione, copertura 14,5x il pedaggio, IC90 positivo) ma il DD resta l'unico
ostacolo sostanziale (47%). P1 ha provato a domarlo dall'USCITA (trailing stop ATR):
smentito — il chandelier peggiora tutto (DD 55,6%, expectancy -1,07%). P5 ha provato a
irrobustire il segnale allargando l'universo: l'edge NON regge l'allargamento (t 1,44).
Questo nodo attacca il DD dal lato ESPOSIZIONE: si compra il breakout SOLO in regime
toro strutturale (chiusura sopra la SMA200); sotto la media, nessun trade. Meno tempo
esposto nei regimi sbagliati = drawdown potenzialmente minore a parita' di segnale.

MECCANICA (dal brief, vincolante)
=================================
Entrata: chiusura(i) > max(massimi[i-N .. i-1]) E chiusura(i) > SMA200(i) -> apertura i+1.
Uscita, la PRIMA delle due (decisione su chiusura d, esecuzione apertura d+1):
  - rottura del minimo a 20 barre: chiusura(d) < min(minimi[d-20 .. d-1])  [controllata prima]
  - chiusura sotto SMA200: chiusura(d) < SMA200(d)                        [controllata seconda]
Una posizione alla volta; niente rientro sulla barra di uscita; serie che finisce in
posizione -> liquidazione all'apertura dell'ultima barra (motivo "fine serie").
SMA200: media semplice delle ultime 200 chiusure FINO alla barra di decisione inclusa;
prima di 200 chiusure nessun ingresso.

ANTI-LOOK-AHEAD, DICHIARATO
===========================
Canale calcolato sulle N barre PRECEDENTI (i-N .. i-1): la barra del segnale non entra
mai nel massimo. L'esecuzione e' sempre all'apertura della barra successiva alla decisione.
La barra di esecuzione non entra nel segnale.

GRIGLIA dichiarata per intero: 4 configurazioni (N in {20,40} x uscita {canale20, sma200}).
Il cancello non corregge per il numero di tentativi: il numero sta qui, scritto, prima dei dati.

NOTA DI INTEGRAZIONE (2026-09-29)
=================================
Modulo RISCRITTO da Hermes sulla consegna di agent-zero (23/09-28/09), che presentava bug
bloccanti: canale con la barra corrente inclusa -> zero ingressi possibili; NameError nelle
uscite; simula/scegli_config mancanti; 5 copie del corpo della funzione. Il brief e' stato
rispettato alla lettera; slippage 4 bps = stessa assunzione dei nodi comparabili (il brief
ne citava 5 come arrotondamento) per non falsare il confronto A/B con Donchian/P1.
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

#: Finestra corretta 2026-09-27: eea.okx.com serve gli alt/USDT solo dal ~2020-06; con
#: 2020-10-01 il paniere e' completo (10/10, copertura >=95%). Verifica invariata.
INIZIO_STORIA = "2020-10-01"
FINE_STORIA = "2026-09-25"
CONFINE_ADDESTRAMENTO = "2024-06-01"

SIMBOLI: Tuple[str, ...] = (
    "BTC/USDT", "ETH/USDT", "ADA/USDT", "DOGE/USDT", "LTC/USDT", "LINK/USDT",
    "DOT/USDT", "UNI/USDT", "AVAX/USDT", "SOL/USDT",
)
COPERTURA_MINIMA: float = 0.95

PERIODO_SMA: int = 200
CANALE_USCITA: int = 20

GRIGLIA_ADDESTRAMENTO: Tuple[dict, ...] = tuple(
    {"canale": n, "uscita": u}
    for n in (20, 40)
    for u in ("canale20", "sma200")
)


@dataclass(frozen=True)
class Config:
    canale: int
    uscita: str

    def __str__(self) -> str:
        return f"breakout {self.canale}g | uscita {self.uscita}"

    def chiave(self) -> str:
        return f"n{self.canale}_{self.uscita}"


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
    motivo: str                   # "canale20" | "sma200" | "fine serie"


def _sma(chiusure: Sequence[float], periodo: int = PERIODO_SMA) -> list:
    """SMA allineata alle chiusure (None prima di `periodo` barre). Solo dati passati."""
    out: list = [None] * len(chiusure)
    if len(chiusure) < periodo:
        return out
    finestra = math.fsum(chiusure[:periodo])
    out[periodo - 1] = finestra / periodo
    for i in range(periodo, len(chiusure)):
        finestra += chiusure[i] - chiusure[i - periodo]
        out[i] = finestra / periodo
    return out


# --- il motore ------------------------------------------------------------------------------

def operazioni_simbolo(barre: Sequence[Barra], config: Config,
                       i_da: int = 0, i_a: Optional[int] = None) -> list:
    """Le operazioni della regola su un simbolo, fra gli indici dati.

    Entrata (decisione su chiusura i, esecuzione apertura i+1): breakout del canale a
    `config.canale` barre (strettamente sopra il massimo delle barre precedenti) E chiusura
    sopra la SMA200. Uscita (decisione su chiusura d, esecuzione apertura d+1), la prima
    delle due: rottura del minimo a 20 barre, poi chiusura sotto SMA200. Una posizione alla
    volta; dopo l'uscita si riparte dalla barra successiva.
    """
    a = len(barre) - 1 if i_a is None else min(i_a, len(barre) - 1)
    sma = _sma([b.chiusura for b in barre])
    fuori: list = []
    i = max(i_da, PERIODO_SMA - 1, config.canale)
    while i < a:
        tetto = max(b.massimo for b in barre[i - config.canale:i])
        if (sma[i] is not None and barre[i].chiusura > tetto
                and barre[i].chiusura > sma[i]):
            i_ing = i + 1
            p_in = barre[i_ing].apertura
            j_out, p_out, motivo = a, barre[a].apertura, "fine serie"
            for j in range(i_ing + 1, a + 1):
                d = j - 1
                if (config.uscita == "canale20" and d >= CANALE_USCITA
                        and barre[d].chiusura < min(b.minimo for b in barre[d - CANALE_USCITA:d])):
                    j_out, p_out, motivo = j, barre[j].apertura, "canale20"
                    break
                if (config.uscita == "sma200" and sma[d] is not None
                        and barre[d].chiusura < sma[d]):
                    j_out, p_out, motivo = j, barre[j].apertura, "sma200"
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


# --- da operazioni a Esito (identico agli altri nodi: una sola verita' sui costi) -----------

def curva_equity(ritorni: Sequence[float], esposizione: float = ESPOSIZIONE) -> Tuple[float, list]:
    equity, massimo, dd, curva = 1.0, 1.0, 0.0, [1.0]
    for r in ritorni:
        equity *= (1.0 + r * esposizione)
        curva.append(equity)
        massimo = max(massimo, equity)
        if massimo > 0:
            dd = max(dd, 1.0 - equity / massimo)
    return dd, curva


# --- API pubblica ---------------------------------------------------------------------------

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
        if len(serie) < PERIODO_SMA + 4:
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
        operazioni, giorni, nome or f"trend filtro sma200 [{config}]",
        slippage_per_lato=slippage_per_lato, tariffa=tariffa, tipo=tipo,
        esposizione=esposizione,
        note=(f"config: {config} | simboli usati: {usati} | "
              f"finestra giudicata: {giorni:.1f} giorni ({giorni / 365.0:.2f} anni)"))


def scegli_config(serie_per_simbolo: dict, *, i_da: int, i_a: int,
                  nome: str, tariffa: Optional[Tariffa] = None):
    """Prova TUTTA la griglia in addestramento, sceglie per expectancy netta. Tabella completa."""
    tabella: list = []
    for parametri in GRIGLIA_ADDESTRAMENTO:
        config = Config(**parametri)
        esito = simula(serie_per_simbolo, config, nome=f"{nome} [{config.chiave()}]",
                       tariffa=tariffa, i_da=i_da, i_a=i_a)
        exp = math.fsum(esito.ritorni_netti) / len(esito.ritorni_netti) if esito.ritorni_netti else float("nan")
        tabella.append({"config": config, "n": esito.n_operazioni, "expectancy_netta": exp})
    # n >= 30 IN ADDESTRAMENTO, non solo al cancello (lezione DSH 2026-09-27: una
    # configurazione scelta su 12 operazioni e' una configurazione scelta sul rumore).
    valide = [r for r in tabella if r["n"] >= 30 and not math.isnan(r["expectancy_netta"])]
    if not valide:
        return Config(**GRIGLIA_ADDESTRAMENTO[0]), tabella
    return max(valide, key=lambda r: r["expectancy_netta"])["config"], tabella


def expectancy_lorda(operazioni: Sequence[Operazione]) -> Optional[float]:
    if not operazioni:
        return None
    return math.fsum(o.ritorno_lordo for o in operazioni) / len(operazioni)
