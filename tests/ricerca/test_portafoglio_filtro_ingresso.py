"""Test del gancio `filtro_ingresso` (spec P6/mincorr) sul motore di portafoglio.

PERCHE' QUESTI TEST ESISTONO
============================
La spec P6 rifiuta un ingresso quando la correlazione con le posizioni aperte supera
tau, e la misura legge il verdetto sul campione ESECUITO: se il motore ignorasse il
filtro, o lo applicasse DOPO il cap (cambiando conteggi e campione), la misura P6
misurerebbe un'altra cosa e nessuno se ne accorgerebbe. L'ordine dichiarato e':
filtro PRIMA del cap. Questi test lo rendono impossibile da rompere in silenzio.
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


def test_filtro_rifiuta_e_conta():
    # Rifiutato: niente esecuzione, niente cassa impegnata, contatore dedicato.
    x = barre([(100, 100), (100, 100), (110, 110), (110, 110)])
    ops = {"X": [Op(T0 + 1 * PASSO, T0 + 2 * PASSO, 100.0, 110.0)]}
    esito = backtest_portafoglio({"X": x}, ops, esposizione=0.25, netto_fn=identico,
                                 filtro_ingresso=lambda s, o, ts, pos: False)
    assert esito.operazioni_eseguite == 0
    assert esito.operazioni_rifiutate == 1
    assert esito.operazioni_saltate == 0
    assert esito.capitale_finale == pytest.approx(1000.0, rel=1e-12)
    assert esito.esecuzioni == ()


def test_filtro_prima_del_cap():
    # Slot pieno E candidato rifiutato: il conteggio deve andare al FILTRO (prima),
    # non al cap. Se questo cambia, la lettura "saltati vs rifiutati" della misura P6
    # diventa bugiarda.
    x = barre([(100, 100)] * 6)
    ops = {"A": [Op(T0 + 1 * PASSO, T0 + 5 * PASSO, 100.0, 100.0)],
           "B": [Op(T0 + 2 * PASSO, T0 + 3 * PASSO, 100.0, 100.0)]}
    esito = backtest_portafoglio({"A": x, "B": x}, ops, esposizione=0.25,
                                 netto_fn=identico, max_posizioni=1,
                                 filtro_ingresso=lambda s, o, ts, pos: s != "B")
    assert esito.operazioni_eseguite == 1        # A entra
    assert esito.operazioni_rifiutate == 1       # B: rifiutato dal filtro (slot pieno)
    assert esito.operazioni_saltate == 0


def test_esecuzioni_contiene_le_eseguite():
    x = barre([(100, 100), (100, 100), (110, 110), (110, 110)])
    op = Op(T0 + 1 * PASSO, T0 + 2 * PASSO, 100.0, 110.0)
    esito = backtest_portafoglio({"X": x}, {"X": [op]}, esposizione=0.25,
                                 netto_fn=identico,
                                 filtro_ingresso=lambda s, o, ts, pos: True)
    assert esito.esecuzioni == (("X", op),)
    assert esito.operazioni_rifiutate == 0


def test_il_filtro_riceve_le_posizioni_aperte():
    # Il filtro deve vedere le posizioni aperte AL MOMENTO della decisione (e solo quelle).
    visti = {}

    def filtro(s, o, ts, pos):
        visti[s] = sorted(pos.keys())
        return True

    x = barre([(100, 100)] * 6)
    ops = {"A": [Op(T0 + 1 * PASSO, T0 + 4 * PASSO, 100.0, 100.0)],
           "B": [Op(T0 + 2 * PASSO, T0 + 3 * PASSO, 100.0, 100.0)]}
    backtest_portafoglio({"A": x, "B": x}, ops, esposizione=0.25, netto_fn=identico,
                         filtro_ingresso=filtro)
    assert visti == {"A": [], "B": ["A"]}


def test_default_invariato():
    x = barre([(100, 100), (100, 100), (110, 110), (110, 110)])
    ops = {"X": [Op(T0 + 1 * PASSO, T0 + 2 * PASSO, 100.0, 110.0)]}
    senza = backtest_portafoglio({"X": x}, ops, esposizione=0.25, netto_fn=identico)
    esplicito = backtest_portafoglio({"X": x}, ops, esposizione=0.25,
                                     netto_fn=identico, filtro_ingresso=None)
    assert senza.capitale_finale == esplicito.capitale_finale
    assert esplicito.operazioni_rifiutate == 0
    assert len(esplicito.esecuzioni) == 1
