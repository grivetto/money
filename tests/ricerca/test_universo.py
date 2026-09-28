"""Test della selezione universo (P5).

I criteri sono dichiarati nella spec P5; questi test li rendono verificabili:
copertura di finestra, guardia sulla prima barra (allineamento), esclusioni motivate.
"""
from money.dati import Barra, SerieBarre
from money.ricerca import universo as U

PASSO = 86_400_000
INIZIO = 1_600_000_000_000  # 2020-09-13T12:26:40Z, irrilevante: contano gli offset
FINE = INIZIO + 99 * PASSO


def serie(ts_lista, timeframe="1d"):
    return SerieBarre([Barra(ts, 1.0, 1.0, 1.0, 1.0, 1.0) for ts in ts_lista],
                      venue="okx_eea", simbolo="X/USDT", timeframe=timeframe)


def piena(n=100, passo=PASSO, t0=INIZIO):
    return serie([t0 + i * passo for i in range(n)])


def test_copertura_finestra_piena():
    s = piena()
    assert U.copertura_finestra(s, INIZIO, FINE) == 1.0


def test_copertura_finestra_con_buchi():
    ts = [INIZIO + i * PASSO for i in range(100)]
    del ts[30:45]  # 15 barre mancanti su 100
    s = serie(ts)
    assert abs(U.copertura_finestra(s, INIZIO, FINE) - 0.85) < 1e-12


def test_inclusa_serie_piena():
    assert U.motivo_esclusione(piena(), inizio_ms=INIZIO, fine_ms=FINE) is None


def test_esclusa_per_storia_corta():
    s = serie([INIZIO + (30 + i) * PASSO for i in range(70)])
    motivo = U.motivo_esclusione(s, inizio_ms=INIZIO, fine_ms=FINE)
    assert motivo is not None and "storia corta" in motivo


def test_esclusa_per_copertura():
    ts = [INIZIO + i * PASSO for i in range(100)]
    del ts[10:30]  # 20 barre mancanti = 80%
    motivo = U.motivo_esclusione(serie(ts), inizio_ms=INIZIO, fine_ms=FINE)
    assert motivo is not None and "copertura" in motivo


def test_esclusa_serie_troppo_corta():
    motivo = U.motivo_esclusione(piena(n=30), inizio_ms=INIZIO, fine_ms=FINE)
    assert motivo is not None and "serie corta" in motivo


def test_esclusa_storia_tronca():
    s = serie([INIZIO + i * PASSO for i in range(100) if i < 70])
    motivo = U.motivo_esclusione(s, inizio_ms=INIZIO, fine_ms=FINE)
    assert motivo is not None and ("storia tronca" in motivo or "copertura" in motivo)


def test_tolleranza_prima_barra():
    # 5 giorni di ritardo: dentro la tolleranza (7), copertura comunque >= 95%
    s = piena(n=100, t0=INIZIO + 5 * PASSO)
    assert U.motivo_esclusione(s, inizio_ms=INIZIO, fine_ms=FINE) is None
    # 8 giorni di ritardo: fuori tolleranza
    s2 = piena(n=100, t0=INIZIO + 8 * PASSO)
    motivo = U.motivo_esclusione(s2, inizio_ms=INIZIO, fine_ms=FINE)
    assert motivo is not None and "storia corta" in motivo


def test_barre_attese_estremi():
    assert U.barre_attese(INIZIO, FINE, PASSO) == 100
    assert U.barre_attese(INIZIO, INIZIO, PASSO) == 1
    assert U.barre_attese(FINE, INIZIO, PASSO) == 0
    assert U.barre_attese(INIZIO, FINE, 0) == 0
