#!/usr/bin/env python3
"""money.chiusura_carry — la decisione di chiusura del carry (P34-F2).

PERCHE' ESISTE
==============
Il criterio operativo storico chiudeva il carry quando il netto stimato
tornava >= 0. Il ciclo ADA chiuso il 26/10 lo ha falsificato SUL CONTO
REALE: netto MTM +0,093 USDC, realizzato -0,157 USDC — la condizione chiude
PRIMA del pareggio reale perche' ignora i costi di uscita (fee + basis di
chiusura ~0,25 USDC su nozionale ~90, ~0,28%).

Il criterio corretto per la CHIUSURA ECONOMICA e':
    netto_stimato >= fee_uscita_stimata + basis_uscita_stimato + margine
con fee dalle tariffe verificate di money.costi e basis dallo spread
corrente del book (bid/ask).

Il vecchio criterio "netto >= 0" resta valido SOLO per le chiusure di
emergenza/riduzione di rischio, ed e' un criterio di convenienza, non un
gate: il kill switch vero (carry_chiudi.py) chiude a prescindere.

Fail-closed come il resto del progetto: input non finiti -> rifiuto.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from money.costi import get_tariffa
from money.rischio import _finito


@dataclass(frozen=True)
class CostiUscita:
    """Costi stimati di chiusura del carry (P34-F2), in USDC."""

    fee_uscita: float     # dalle tariffe verificate di money.costi
    basis_uscita: float   # dallo spread corrente del book (bid/ask)
    totale: float
    fonte: str

    @property
    def soglia(self) -> float:
        return self.totale


def stima_costi_uscita(noz_spot: float, noz_perp: float,
                       bid_spot: float, ask_spot: float,
                       bid_perp: float, ask_perp: float,
                       tariffa_spot: str = "okx_eea_con_perp",
                       tariffa_perp: str = "okx_eea_swap_lv1") -> CostiUscita:
    """Stima dei costi di chiusura del carry (P34-F2), mai numeri inventati.

    Fee: taker per lato (la chiusura esce aggressiva), dalle tariffe
    VERIFICATE di money.costi: spot = okx_eea_con_perp (taker 0,10%,
    verificata 2026-10-06 sul conto main), perp = okx_eea_swap_lv1 (taker
    0,05%, verificata 2026-09-25 + fill del canary C1).

    Basis: mezzo spread per gamba (lo spot si vende al bid, la perp si
    ricompra all'ask), dallo spread corrente del book passato dal chiamante.

    Input non finiti o prezzi non positivi -> ValueError (fail-closed: una
    soglia inventata farebbe chiudere in perdita reale).
    """
    ts = get_tariffa(tariffa_spot)
    tp = get_tariffa(tariffa_perp)
    for nome, v in (("noz_spot", noz_spot), ("noz_perp", noz_perp),
                    ("bid_spot", bid_spot), ("ask_spot", ask_spot),
                    ("bid_perp", bid_perp), ("ask_perp", ask_perp)):
        if not _finito(v):
            raise ValueError(f"{nome} non finito: {v!r}")
    for nome, v in (("bid_spot", bid_spot), ("ask_spot", ask_spot),
                    ("bid_perp", bid_perp), ("ask_perp", ask_perp)):
        if v <= 0:
            raise ValueError(f"{nome} non positivo: {v!r} — spread illeggibile")
    fee = noz_spot * ts.taker + noz_perp * tp.taker
    mezzo_spread = lambda b, a: (a - b) / (a + b)  # noqa: E731 (fra il bid e l'ask)
    basis = (noz_spot * mezzo_spread(bid_spot, ask_spot)
             + noz_perp * mezzo_spread(bid_perp, ask_perp))
    return CostiUscita(
        fee_uscita=fee, basis_uscita=basis, totale=fee + basis,
        fonte=(f"fee: {tariffa_spot} (taker {ts.taker:.4%}) + {tariffa_perp} "
               f"(taker {tp.taker:.4%}); basis: mezzo spread per gamba "
               "dal book corrente"))


@dataclass(frozen=True)
class DecisioneChiusura:
    """La decisione di chiusura: economica (P34-F2) o emergenza (netto>=0)."""

    tipo: str             # 'economica' | 'emergenza'
    ok: bool
    motivi: Tuple[str, ...]
    netto_stimato: float
    soglia: float         # fee+basis+margine (economica), 0 (emergenza)

    def __bool__(self) -> bool:
        return self.ok


def chiusura_economica(netto_stimato: float, fee_uscita: float,
                       basis_uscita: float,
                       margine: float = 0.0) -> DecisioneChiusura:
    """P34-F2: la chiusura ECONOMICA chiude solo se il netto copre i costi
    di uscita (fee + basis) piu' l'eventuale margine. Sotto soglia si tiene
    la posizione: chiudere qui = perdita realizzata garantita."""
    if not _finito(netto_stimato):
        return DecisioneChiusura("economica", False,
                                 ("netto stimato non finito",), 0.0, 0.0)
    if not (_finito(fee_uscita) and _finito(basis_uscita) and _finito(margine)):
        return DecisioneChiusura("economica", False,
                                 ("costi di uscita non finiti",), 0.0, 0.0)
    soglia = fee_uscita + basis_uscita + margine
    if netto_stimato < soglia:
        return DecisioneChiusura(
            "economica", False,
            (f"netto stimato {netto_stimato:.4f} USDC < soglia {soglia:.4f} "
             f"USDC (fee_uscita {fee_uscita:.4f} + basis {basis_uscita:.4f} "
             f"+ margine {margine:.4f}): la chiusura economica non e' a "
             "pareggio reale",),
            netto_stimato, soglia)
    return DecisioneChiusura("economica", True,
                             ("netto >= costi di uscita",), netto_stimato,
                             soglia)


def chiusura_emergenza(netto_stimato: float) -> DecisioneChiusura:
    """Il VECCHIO criterio (netto >= 0), ammesso SOLO per chiusure di
    emergenza/riduzione di rischio (P34-F2). E' un criterio di convenienza,
    non un gate: il kill switch vero (carry_chiudi.py) chiude a prescindere
    dal netto — la riduzione di rischio non si negozia."""
    if not _finito(netto_stimato):
        return DecisioneChiusura("emergenza", False,
                                 ("netto stimato non finito",), 0.0, 0.0)
    if netto_stimato < 0:
        return DecisioneChiusura(
            "emergenza", False,
            (f"netto {netto_stimato:.4f} USDC negativo: anche per una "
             "riduzione di rischio conviene dichiararlo esplicitamente "
             "(il kill switch chiude comunque, a parte)",),
            netto_stimato, 0.0)
    return DecisioneChiusura("emergenza", True, ("netto >= 0",),
                             netto_stimato, 0.0)
