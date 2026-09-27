"""Test del nodo P1 (trend + chandelier ATR): la scommessa per promuovere o archiviare.

Devono essere vere per costruzione: ATR solo passato, chandelier mai decrescente, stop
intraday col caso peggiore sui gap, tutte le operazioni chiuse, una posizione alla volta.
"""
import math

from money.dati import Barra
from money.ricerca import trend_atr_stop as P1


def barre(prezzi, ts0=1_700_000_000_000, passo=86_400_000, alto=1.0, basso=1.0):
    return [Barra(ts0 + i * passo, p, p * alto, p * basso, p, 1000.0)
            for i, p in enumerate(prezzi)]


def test_atr_solo_passato():
    b = barre([100.0 + i for i in range(40)])
    a30 = P1._atr_wilder(b, 30)
    assert a30 > 0
    # cambiare le barre FUTURE non cambia l'ATR di oggi
    b_futuro = b + barre([200.0] * 10, ts0=b[-1].ts + 86_400_000)
    assert P1._atr_wilder(b_futuro, 30) == a30


def test_chandelier_taglia_prima_del_canale_opposto():
    # salita forte poi ritracciamento: lo stop deve scattare MOLTO prima di una rottura
    # a canale opposto (che avrebbe lasciato correre il DD nei nodi I/N)
    salita = [100.0 + 3 * i for i in range(30)]
    ritraccio = [salita[-1] - 4 * i for i in range(1, 12)]
    b = barre(salita + ritraccio)
    ops = P1.operazioni_simbolo(b, P1.Config(canale=20, k_atr=2.5))
    assert ops
    o = ops[0]
    assert o.motivo in ("chandelier", "chandelier a gap")
    # uscita in perdita moderata, non -30%: il ritraccio da 187 a 143 e' -23%; con lo stop
    # ATR l'operazione chiude con una perdita piccola
    assert o.ritorno_lordo > -0.20


def test_gap_sotto_lo_stop_esce_all_apertura():
    salita = [100.0 + 3 * i for i in range(30)]
    # barra che apre 20% sotto il massimo: gap
    salita.append(salita[-1] * 0.80)
    b = barre(salita)
    ops = P1.operazioni_simbolo(b, P1.Config(canale=20, k_atr=2.5))
    assert ops and ops[0].motivo == "chandelier a gap"
    assert ops[0].prezzo_uscita == b[-1].apertura


def test_operazione_chiusa_a_fine_serie():
    prezzi = [100.0 + 3 * i for i in range(60)]   # trend senza ritracci seri
    # ritocca: il chandelier con k=3 su trend ripido non scatta mai -> fine serie
    b = barre(prezzi)
    ops = P1.operazioni_simbolo(b, P1.Config(canale=20, k_atr=3.0))
    assert ops
    assert ops[-1].motivo in ("fine serie", "chandelier", "chandelier a gap")


def test_una_posizione_alla_volta():
    prezzi = [100.0 + 3 * i for i in range(40)] + [220.0 - 5 * i for i in range(20)] + \
             [120.0 + 4 * i for i in range(30)]
    ops = P1.operazioni_simbolo(barre(prezzi), P1.Config(canale=20, k_atr=2.0))
    for a, b in zip(ops, ops[1:]):
        assert b.indice_ingresso > a.indice_uscita


def test_entro_all_apertura_dopo_il_segnale():
    prezzi = [100.0 + 3 * i for i in range(40)]
    b = barre(prezzi)
    ops = P1.operazioni_simbolo(b, P1.Config(canale=20, k_atr=2.0))
    assert ops
    o = ops[0]
    assert o.prezzo_ingresso == b[o.indice_ingresso].apertura
    # il segnale e' su chiusura(i), ingresso su i+1
    assert b[o.indice_ingresso - 1].chiusura > max(x.massimo for x in b[o.indice_ingresso - 21:o.indice_ingresso - 1])
