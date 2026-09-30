"""money.ricerca.portafoglio — il motore di backtest a PORTAFOGLIO (mark-to-market).

PERCHE' QUESTO MODULO ESISTE
============================
Tutti i nodi misurati finora (H, I, P1, P3, P5) calcolano la curva equity come una
SEQUENZA di operazioni: `equity *= (1 + r * esposizione)` per ogni trade, uno dopo
l'altro. E' il modello di un conto che tiene UNA posizione alla volta.

Ma le strategie girano su 10 simboli: in un mercato toro i breakout arrivano insieme e
il conto reale tiene 3-6 posizioni APERTE IN PARALLELO. La curva serializzata quindi:
  - non vede il drawdown INTRA-trade (mark-to-market giornaliero);
  - non vede l'esposizione aggregata (che puo' arrivare al 100% del capitale);
  - tratta trade concorrenti come indipendenti (t-stat e IC gonfiati).

Questo modulo misura la stessa strategia come la vedrebbe l'exchange: capitale reale,
posizioni concorrenti, mark-to-market giornaliero, vincolo di cassa. Il verdetto del
cancello resta quello che e' — ma da qui in avanti si legge ACCANTO al numero di
portafoglio, che e' quello che il conto vivra'.

CONTRATTO
=========
- Spot long-only, nessuna leva: una posizione non impegna piu' cassa di quanta ne esista.
  Un segnale che arriva a cassa esaurita viene SALTATO e contato (mai silenzioso).
- Allocazione per operazione = `esposizione` x equity al momento dell'ingresso (stessa
  semantica del modello serializzato: 0.25 = un quarto del capitale per trade).
- I costi sono quelli del nodo chiamante (`netto_fn`): il modulo non stima costi, li
  applica alla chiusura di ogni posizione — una sola verita' sui costi.
- Mark-to-market GIORNALIERO: l'equity e' cassa + valore di mercato delle posizioni
  aperte, marcata alla chiusura di ogni barra. Il drawdown include il dentro-trade.
- Determinismo: nessun caso, nessun seme, nessuna rete. Stessi input, stessi numeri.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Posizione:
    """Una posizione aperta: capitale impegnato, quantita', prezzo di ingresso."""

    simbolo: str
    allocazione: float
    qty: float
    prezzo_ingresso: float
    ts_ingresso: int
    ts_uscita: int


@dataclass(frozen=True)
class EsitoPortafoglio:
    """Il risultato di un backtest a portafoglio: numeri MISURATI, non estrapolati.

    `max_drawdown` e' calcolato sulla curva mark-to-market giornaliera (include il
    dentro-trade). `max_esposizione` e' il massimo di (valore posizioni / equity):
    sopra 1.0 significa che il conto era piu' investito del suo capitale — impossibile
    senza leva, quindi il valore dice anche se il sizing dichiarato e' sostenibile.
    `operazioni_saltate` conta i segnali che non hanno trovato cassa: sono rendimento
    mancato, e vanno letti, non nascosti.
    """

    capitale_iniziale: float
    capitale_finale: float
    rendimento_totale: float
    cagr: float
    eur_anno: float
    max_drawdown: float
    max_esposizione: float
    max_posizioni: int
    operazioni_eseguite: int
    operazioni_saltate: int
    giorni: float
    esposizione: float
    curva: Tuple[Tuple[int, float], ...]

    def riassunto(self) -> dict:
        return {
            "capitale_iniziale": self.capitale_iniziale,
            "capitale_finale": self.capitale_finale,
            "rendimento_totale": self.rendimento_totale,
            "cagr": self.cagr,
            "eur_anno": self.eur_anno,
            "max_drawdown": self.max_drawdown,
            "max_esposizione": self.max_esposizione,
            "max_posizioni": self.max_posizioni,
            "operazioni_eseguite": self.operazioni_eseguite,
            "operazioni_saltate": self.operazioni_saltate,
            "giorni": self.giorni,
            "esposizione": self.esposizione,
        }


def backtest_portafoglio(
    serie_per_simbolo: Dict[str, Sequence[Any]],
    operazioni_per_simbolo: Dict[str, Sequence[Any]],
    *,
    esposizione: float,
    netto_fn: Callable[[float], float],
    capitale: float = 1000.0,
    max_posizioni: Optional[int] = None,
    esposizione_per_op: Optional[Callable[[str, Any], float]] = None,
) -> EsitoPortafoglio:
    """Simula il conto reale: posizioni concorrenti, cassa vincolata, MTM giornaliero.

    `serie_per_simbolo`: simbolo -> sequenza di barre (con `.ts` e `.chiusura`).
    `operazioni_per_simbolo`: simbolo -> sequenza di operazioni del nodo (con
    `ts_ingresso`, `ts_uscita`, `prezzo_ingresso`, `prezzo_uscita`).
    `netto_fn`: lordo -> netto (fee + slippage), la funzione di costo del nodo.
    `max_posizioni`: tetto opzionale alle posizioni concorrenti (None = solo la cassa).
    `esposizione_per_op`: gancio per la frazione (0..1] della SINGOLA operazione,
    `(simbolo, op) -> frazione`; se assente si usa `esposizione` fissa. E' il gancio
    del vol targeting (P2): con allocazione = f * base * equity e costi del nodo
    invariati, il P&L per unita' di equity vale `base * f * netto` — la formula della
    spec P2, senza un secondo modello di costo.

    Ordine di lavorazione di ogni giorno: prima le USCITE (liberano cassa), poi gli
    INGRESSI (consumano cassa), poi il MARK-TO-MARKET alla chiusura. E' l'ordine che
    farebbe un bot reale, e rende il vincolo di cassa vincolante come nella realta'.
    """
    chiusure: Dict[str, Dict[int, float]] = {
        s: {b.ts: b.chiusura for b in serie} for s, serie in serie_per_simbolo.items()
    }
    ingressi: Dict[int, List[Tuple[str, Any]]] = {}
    uscite: Dict[int, List[Tuple[str, Any]]] = {}
    for simbolo, ops in operazioni_per_simbolo.items():
        for o in ops:
            ingressi.setdefault(o.ts_ingresso, []).append((simbolo, o))
            uscite.setdefault(o.ts_uscita, []).append((simbolo, o))

    giorni = sorted({b.ts for serie in serie_per_simbolo.values() for b in serie})
    if not giorni:
        return _vuoto(capitale, esposizione)

    cassa = capitale
    posizioni: Dict[str, Posizione] = {}
    ultimi: Dict[str, float] = {}
    curva: List[Tuple[int, float]] = []
    picco = capitale
    max_dd = 0.0
    max_esp = 0.0
    max_pos = 0
    eseguite = 0
    saltate = 0

    for ts in giorni:
        # Le uscite si processano PRIMA degli ingressi: la cassa liberata oggi e'
        # disponibile per i segnali di oggi (e' l'ordine che farebbe un bot reale).
        for simbolo, o in uscite.get(ts, ()):
            pos = posizioni.pop(simbolo, None)
            if pos is None:
                continue
            lordo = o.prezzo_uscita / pos.prezzo_ingresso - 1.0
            cassa += pos.allocazione * (1.0 + netto_fn(lordo))
        for simbolo, o in ingressi.get(ts, ()):
            if max_posizioni is not None and len(posizioni) >= max_posizioni:
                saltate += 1
                continue
            equity_ora = cassa + math.fsum(
                p.qty * ultimi.get(s, p.prezzo_ingresso) for s, p in posizioni.items())
            frazione = (esposizione_per_op(simbolo, o)
                        if esposizione_per_op is not None else esposizione)
            allocazione = frazione * equity_ora
            if allocazione <= 0.0 or cassa < allocazione:
                saltate += 1
                continue
            cassa -= allocazione
            posizioni[simbolo] = Posizione(
                simbolo=simbolo, allocazione=allocazione,
                qty=allocazione / o.prezzo_ingresso,
                prezzo_ingresso=o.prezzo_ingresso,
                ts_ingresso=ts, ts_uscita=o.ts_uscita)
            eseguite += 1
        for simbolo, mappa in chiusure.items():
            prezzo = mappa.get(ts)
            if prezzo is not None:
                ultimi[simbolo] = prezzo
        valore = math.fsum(p.qty * ultimi.get(s, p.prezzo_ingresso)
                           for s, p in posizioni.items())
        equity = cassa + valore
        curva.append((ts, equity))
        if equity > picco:
            picco = equity
        if picco > 0.0:
            max_dd = max(max_dd, 1.0 - equity / picco)
        if equity > 0.0:
            max_esp = max(max_esp, valore / equity)
        max_pos = max(max_pos, len(posizioni))

    finale = curva[-1][1]
    giorni_osservati = (giorni[-1] - giorni[0]) / 86_400_000.0
    anni = giorni_osservati / 365.0
    rendimento = finale / capitale - 1.0
    cagr = ((finale / capitale) ** (1.0 / anni) - 1.0) if anni > 0 and finale > 0 else 0.0
    eur_anno = (rendimento / anni * capitale) if anni > 0 else 0.0
    return EsitoPortafoglio(
        capitale_iniziale=capitale, capitale_finale=finale,
        rendimento_totale=rendimento, cagr=cagr, eur_anno=eur_anno,
        max_drawdown=max_dd, max_esposizione=max_esp, max_posizioni=max_pos,
        operazioni_eseguite=eseguite, operazioni_saltate=saltate,
        giorni=giorni_osservati, esposizione=esposizione, curva=tuple(curva))


def _vuoto(capitale: float, esposizione: float) -> EsitoPortafoglio:
    """Nessuna barra: nessun numero. Non un'eccezione — un esito vuoto e dichiarato."""
    return EsitoPortafoglio(
        capitale_iniziale=capitale, capitale_finale=capitale,
        rendimento_totale=0.0, cagr=0.0, eur_anno=0.0,
        max_drawdown=0.0, max_esposizione=0.0, max_posizioni=0,
        operazioni_eseguite=0, operazioni_saltate=0, giorni=0.0,
        esposizione=esposizione, curva=())
