"""Test del gancio `esposizione_per_op` (vol targeting) sul motore di portafoglio.

PERCHE' QUESTI TEST ESISTONO
============================
La spec P2 riduce l'allocazione nei tratti volatili SENZA toccare il segnale:
`allocazione = f * base * equity` con i costi del nodo invariati, quindi il P&L per
unita' di equity deve valere esattamente `base * f * netto`. Se questo smettesse di
essere vero, la misura P2 misurerebbe un'altra cosa e nessuno se ne accorgerebbe:
questi test lo rendono impossibile.
"""
from __future__ import annotations

import pytest

from money.dati import Barra
from money.ricerca.portafoglio import backtest_portafoglio

T0 = 1_700_000_000_000
PASSO = 86_400_000


def barre(piazze, ts0=T0):
    """piazze: lista di tuple (apertura, chiusura)."""
    return [Barra(ts0 + i * PASSO, a, max(a, c), min(a, c), c, 1000.0)
            for i, (a, c) in enumerate(piazze)]


class Op:
    """Operazione minimale: gli stessi campi che usa il motore."""

    def __init__(self, ts_ingresso, ts_uscita, prezzo_ingresso, prezzo_uscita):
        self.ts_ingresso = ts_ingresso
        self.ts_uscita = ts_uscita
        self.prezzo_ingresso = prezzo_ingresso
        self.prezzo_uscita = prezzo_uscita


def identico(lordo):
    return lordo


def test_frazione_meta_dimezza_il_pnl():
    # +10% con frazione 0.125 su 1000 EUR: 1000 - 125 + 125*1.1 = 1012.5
    x = barre([(100, 100), (100, 100), (110, 110), (110, 110)])
    ops = {"X": [Op(T0 + 1 * PASSO, T0 + 2 * PASSO, 100.0, 110.0)]}
    pieno = backtest_portafoglio({"X": x}, ops, esposizione=0.25, netto_fn=identico)
    meta = backtest_portafoglio({"X": x}, ops, esposizione=0.25, netto_fn=identico,
                                esposizione_per_op=lambda simbolo, op: 0.125)
    assert pieno.capitale_finale == pytest.approx(1025.0, rel=1e-9)
    assert meta.capitale_finale == pytest.approx(1012.5, rel=1e-9)
    assert meta.operazioni_eseguite == 1


def test_frazione_zero_salta_l_operazione():
    # Fail-closed del vol targeting: f=0 => nessuna esposizione, MAI "piena per default".
    x = barre([(100, 100), (100, 100), (110, 110), (110, 110)])
    ops = {"X": [Op(T0 + 1 * PASSO, T0 + 2 * PASSO, 100.0, 110.0)]}
    esito = backtest_portafoglio({"X": x}, ops, esposizione=0.25, netto_fn=identico,
                                 esposizione_per_op=lambda simbolo, op: 0.0)
    assert esito.operazioni_eseguite == 0
    assert esito.operazioni_saltate == 1
    assert esito.capitale_finale == pytest.approx(1000.0, rel=1e-12)


def test_il_gancio_riceve_il_simbolo():
    visti = []
    x = barre([(100, 100), (100, 100), (110, 110), (110, 110)])
    ops = {"X": [Op(T0 + 1 * PASSO, T0 + 2 * PASSO, 100.0, 110.0)]}
    backtest_portafoglio({"X": x}, ops, esposizione=0.25, netto_fn=identico,
                         esposizione_per_op=lambda simbolo, op: (visti.append(simbolo),
                                                                 0.25)[1])
    assert visti == ["X"]


def test_default_invariato():
    x = barre([(100, 100), (100, 100), (110, 110), (110, 110)])
    ops = {"X": [Op(T0 + 1 * PASSO, T0 + 2 * PASSO, 100.0, 110.0)]}
    senza = backtest_portafoglio({"X": x}, ops, esposizione=0.25, netto_fn=identico)
    esplicito_none = backtest_portafoglio({"X": x}, ops, esposizione=0.25,
                                          netto_fn=identico, esposizione_per_op=None)
    assert senza.capitale_finale == esplicito_none.capitale_finale
