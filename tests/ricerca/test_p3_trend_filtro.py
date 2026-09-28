"""Test del nodo P3 (trend + filtro di regime SMA200) — integrato da Hermes 2026-09-29.

La consegna di agent-zero non passava la review (canale che includeva la barra corrente ->
ingressi impossibili; uscite con NameError; test che fallivano 3/6). Questi test bloccano
quei bug per costruzione, sui casi che contano: filtro di regime, esecuzione all'apertura
successiva, uscite (entrambe le varianti), fine serie, anti-look-ahead, griglia, costi.
"""
import pytest

from money.dati import Barra
from money.ricerca import p3_trend_filtro_200g as P3

T0 = 1_700_000_000_000
PASSO = 86_400_000


def barre(piazze, ts0=T0):
    """piazze: lista di tuple (apertura, massimo, minimo, chiusura)."""
    return [Barra(ts0 + i * PASSO, o, h, l, c, 1000.0) for i, (o, h, l, c) in enumerate(piazze)]


def piatto(n, prezzo=100.0):
    return [(prezzo, prezzo * 1.01, prezzo * 0.99, prezzo)] * n


def test_breakout_sotto_la_sma_non_apre():
    # discesa 100 -> 60, breakout del canale a 65 ma SOTTO la SMA200 (~70,2): il filtro blocca
    serie = barre(piatto(100) + [(60, 61, 59, 60)] * 148
                  + [(60.5, 66, 59, 65), (65, 66, 64, 65.5)])
    ops = P3.operazioni_simbolo(serie, P3.Config(20, "canale20"))
    assert ops == []


def test_breakout_sopra_la_sma_apre_all_apertura_successiva():
    serie = barre(piatto(200) + [(100, 103, 100, 102), (102.5, 104, 102, 103)]
                  + [(103, 104, 102, 103)] * 4)
    ops = P3.operazioni_simbolo(serie, P3.Config(20, "canale20"))
    assert len(ops) == 1
    o = ops[0]
    assert o.indice_ingresso == 201
    assert o.prezzo_ingresso == 102.5           # apertura di i+1, NON la chiusura del segnale (102)
    assert o.motivo == "fine serie"             # serie finita in posizione -> liquidata
    assert o.indice_uscita == len(serie) - 1


def test_uscita_canale20_eseguita_all_apertura():
    serie = barre(piatto(200) + [
        (100, 103, 100, 102),      # 200: segnale
        (102.5, 103, 100, 101),    # 201: in posizione
        (101, 102, 97, 98.5),      # 202: chiusura 98.5 < min(minimi[182..201]) = 99 -> uscita
        (98.5, 99, 90, 95),        # 203: esecuzione all'apertura
        (94.5, 96, 93, 94),
    ])
    ops = P3.operazioni_simbolo(serie, P3.Config(20, "canale20"))
    assert len(ops) == 1
    o = ops[0]
    assert o.motivo == "canale20"
    assert o.indice_uscita == 203
    assert o.prezzo_uscita == 98.5


def test_uscita_sma200():
    serie = barre(piatto(200) + [
        (100, 103, 100, 102),      # 200: segnale
        (102.5, 103, 100, 101),    # 201: in posizione
        (101, 102, 94, 95),        # 202: chiusura 95 < SMA200(~100,5) -> uscita
        (95, 96, 90, 92),          # 203: esecuzione all'apertura
    ])
    ops = P3.operazioni_simbolo(serie, P3.Config(20, "sma200"))
    assert len(ops) == 1
    o = ops[0]
    assert o.motivo == "sma200"
    assert o.indice_uscita == 203
    assert o.prezzo_uscita == 95


def test_posizione_chiusa_a_fine_serie():
    crescita = []
    c = 100.0
    for _ in range(16):
        c = c * 1.02
        crescita.append((c / 1.02, c * 1.001, c * 0.99, c))
    serie = barre(piatto(200) + crescita)
    ops = P3.operazioni_simbolo(serie, P3.Config(20, "canale20"))
    assert len(ops) == 1
    o = ops[0]
    assert o.indice_ingresso == 201
    assert o.motivo == "fine serie"
    assert o.indice_uscita == len(serie) - 1
    for op in ops:  # nessuna posizione fantasma: tutto chiuso, sempre
        assert op.indice_ingresso < op.indice_uscita <= len(serie) - 1
        assert op.prezzo_uscita > 0


def test_nessun_look_ahead():
    base = piatto(200) + [
        (100, 103, 100, 102),
        (102.5, 103, 100, 101),
        (101, 102, 97, 98.5),
        (98.5, 99, 90, 95),
        (94.5, 96, 93, 94),
    ]
    taglio = barre(base)
    con_futuro = barre(base + [(94, 95, 93, 94)] * 3 + [(500, 505, 495, 502)] * 30)
    a = P3.operazioni_simbolo(taglio, P3.Config(20, "canale20"))
    b = P3.operazioni_simbolo(con_futuro, P3.Config(20, "canale20"))
    assert a and b
    assert a[0] == b[0]                 # il futuro non cambia le decisioni gia' prese


def test_griglia_quattro_config_distinte():
    griglia = P3.GRIGLIA_ADDESTRAMENTO
    assert len(griglia) == 4
    coppie = {(d["canale"], d["uscita"]) for d in griglia}
    assert coppie == {(20, "canale20"), (20, "sma200"), (40, "canale20"), (40, "sma200")}
    assert len({P3.Config(**d).chiave() for d in griglia}) == 4


def test_sma_allineata_e_solo_passato():
    chiusure = [100.0] * 199 + [110.0] + [200.0] * 10
    sma = P3._sma(chiusure)
    assert sma[198] is None
    assert sma[199] == pytest.approx(sum(chiusure[:200]) / 200)
    atteso = sma[199]
    mutate = chiusure[:200] + [999.0] * 20
    assert P3._sma(mutate)[199] == atteso   # il futuro non cambia la SMA di oggi


def test_ritorno_netto_include_fee_e_slippage():
    lordo = 0.02
    atteso = (1 - 0.0004) * (1 + lordo) * (1 - 0.0004) - 1 - 0.0055
    assert P3.ritorno_netto(lordo) == pytest.approx(atteso, abs=1e-5)
    assert P3.ritorno_netto(lordo) < lordo


def test_scegli_config_struttura():
    crescita = []
    c = 100.0
    for _ in range(16):
        c = c * 1.02
        crescita.append((c / 1.02, c * 1.001, c * 0.99, c))
    dati = {"X": barre(piatto(200) + crescita)}
    config, tabella = P3.scegli_config(dati, i_da=0, i_a=len(dati["X"]) - 1, nome="test")
    assert isinstance(config, P3.Config)
    assert len(tabella) == 4
    for riga in tabella:
        assert {"config", "n", "expectancy_netta"} <= set(riga)
