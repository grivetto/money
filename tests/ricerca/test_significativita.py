"""Test per ``significativita.py`` (voce E2).

Solo dati sintetici, seme fisso, assert su valori attesi a mano.
Senza implementazione i test devono fallire.
"""

import numpy as np
import pytest

from money.ricerca.significativita import bootstrap_regola, montecarlo_trade


# --------------------------------------------------------------------------- #
# (a) segnale con potere predittivo forte e noto -> p_value < 0.05
# --------------------------------------------------------------------------- #
def test_bootstrap_segnale_forte_pvalue_basso():
    n = 200
    rendimenti = np.zeros(n)
    # 15 bar con segnale hanno rendimento noto 1.0, gli altri 0.0
    posizioni = np.arange(15)
    rendimenti[posizioni] = 1.0
    segnale = np.zeros(n, dtype=int)
    segnale[posizioni] = 1

    res = bootstrap_regola(rendimenti, segnale, n_sim=1000, seme=42)

    # metrica reale = media dei bar in posizione = 1.0
    assert res["performance_reale"] == pytest.approx(1.0)
    assert res["n_posizioni"] == 15
    assert res["n_sim"] == 1000
    # nessun segnale casuale puo' raggiungere la media 1.0 se non scegliendo
    # tutti e 15 i bar "giusti" (~1/C(200,15)) -> p_value = 1/1001
    assert res["p_value"] == pytest.approx(1.0 / 1001.0)
    assert res["p_value"] < 0.05


# --------------------------------------------------------------------------- #
# (b) segnale senza potere (rumore) -> p_value > 0.05
# --------------------------------------------------------------------------- #
def test_bootstrap_rumore_pvalue_alto():
    rng = np.random.default_rng(123)
    n = 400
    rendimenti = rng.normal(0.0, 1.0, size=n)
    segnale = np.zeros(n, dtype=int)
    # 40 ingressi casuali: nessun potere predittivo reale
    ingressi = rng.choice(n, size=40, replace=False)
    segnale[ingressi] = 1

    res = bootstrap_regola(rendimenti, segnale, n_sim=1000, seme=42)

    # per un segnale senza potere il p-value deve essere non significativo
    assert res["p_value"] > 0.05


# --------------------------------------------------------------------------- #
# (c) determinismo: stesso input + stesso seme -> output identico
# --------------------------------------------------------------------------- #
def test_determinismo_bootstrap():
    rng = np.random.default_rng(7)
    rendimenti = rng.normal(0.0, 1.0, size=300)
    segnale = np.zeros(300, dtype=int)
    segnale[rng.choice(300, size=30, replace=False)] = 1

    a = bootstrap_regola(rendimenti, segnale, n_sim=500, seme=42)
    b = bootstrap_regola(rendimenti, segnale, n_sim=500, seme=42)

    assert a == b
    assert a["p_value"] == b["p_value"]


def test_determinismo_montecarlo():
    rng = np.random.default_rng(11)
    pnl = rng.normal(0.3, 1.0, size=80)

    a = montecarlo_trade(pnl, n_sim=1000, seme=42)
    b = montecarlo_trade(pnl, n_sim=1000, seme=42)

    assert a == b


# --------------------------------------------------------------------------- #
# (d) Monte Carlo: distribuzione degenere (std = 0) e media attesa
# --------------------------------------------------------------------------- #
def test_montecarlo_distribuzione_degenere():
    # PnL costante: qualunque ricampionamento con reimmissione somma sempre
    # allo stesso totale -> distribuzione degenere, std = 0.
    n = 10
    pnl = np.full(n, 2.0)
    res = montecarlo_trade(pnl, n_sim=2000, seme=42)

    atteso = n * 2.0  # = 20.0
    assert res["pnl_media"] == pytest.approx(atteso)
    assert res["pnl_perc5"] == pytest.approx(atteso)
    assert res["pnl_perc95"] == pytest.approx(atteso)
    # PnL sempre positivo -> nessuna probabilita' di PnL finale negativo
    assert res["prob_pnl_negativa"] == 0.0
    # equity sempre crescente -> max drawdown nullo per ogni sim
    assert res["dd_media"] == pytest.approx(0.0)
    assert res["dd_perc95"] == pytest.approx(0.0)


def test_montecarlo_media_lista_mista():
    # media della distribuzione del PnL finale ~ n * media(lista)
    pnl = np.array([1.0, -0.5, 2.0, 0.3, -1.0])
    n = pnl.size
    media_lista = pnl.mean()  # 0.36
    atteso = n * media_lista  # 1.8

    res = montecarlo_trade(pnl, n_sim=5000, seme=42)

    # tolleranza dichiarata: 0.15 (errore std della media ~0.034)
    assert res["pnl_media"] == pytest.approx(atteso, abs=0.15)


def test_montecarlo_alternato_somma_media_nulla():
    # Serie alternata [+1,-1,...] di lunghezza pari: la MEDIA della lista e' 0,
    # quindi la media della distribuzione del PnL finale e' n * 0 = 0.
    #
    # Nota di rigore: con ricampionamento CON REIMMISSIONE (come da spec) la
    # somma NON e' costante: std = sqrt(n) * std(lista) = sqrt(n). La
    # "distribuzione degenere (std = 0)" e' il caso PnL costante, verificato in
    # test_montecarlo_distribuzione_degenere. Qui verifichiamo la proprieta'
    # statistica corretta della serie alternata.
    pnl = np.array([1.0, -1.0] * 10)  # n = 20, media = 0
    n = pnl.size
    res = montecarlo_trade(pnl, n_sim=20000, seme=42)

    assert res["pnl_media"] == pytest.approx(0.0, abs=0.1)
    assert res["pnl_perc50"] == pytest.approx(0.0, abs=0.1)
    # std attesa della somma con reimmissione = sqrt(n) (tolleranza dichiarata)
    # ricostruiamo la std dai percentili 5-95: ~3.29 sigma -> sigma = (p95-p5)/3.29
    sigma_stimata = (res["pnl_perc95"] - res["pnl_perc5"]) / 3.2897
    assert sigma_stimata == pytest.approx(np.sqrt(n), rel=0.1)


def test_montecarlo_drawdown_dal_valore_iniziale():
    # FIX di integrazione (Artu', verifica indipendente): il max drawdown
    # deve includere il punto di partenza (0). Una serie che perde subito
    # ha drawdown pari alla discesa dal valore iniziale.
    # n=1, PnL -3 -> equity [0,-3] -> dd = 3 (prima del fix: 0).
    res = montecarlo_trade(np.array([-3.0]), n_sim=100, seme=42)
    assert res["dd_media"] == pytest.approx(3.0)
    assert res["dd_perc95"] == pytest.approx(3.0)
    # PnL costante negativo: dd = n * |pnl| = 3 (qualunque ricampionamento).
    res2 = montecarlo_trade(np.array([-1.0, -1.0, -1.0]), n_sim=100, seme=42)
    assert res2["dd_media"] == pytest.approx(3.0)
    # Caso misto deterministico per enumerazione: [-5, +10], 4 combinazioni
    # equiprobabili -> dd: 10, 5, 5, 0 -> media 5.0.
    res3 = montecarlo_trade(np.array([-5.0, 10.0]), n_sim=8000, seme=42)
    assert res3["dd_media"] == pytest.approx(5.0, abs=0.1)


# --------------------------------------------------------------------------- #
# (e) guardie: ValueError esplicito
# --------------------------------------------------------------------------- #
def test_bootstrap_input_vuoto():
    with pytest.raises(ValueError):
        bootstrap_regola(np.array([]), np.array([]), n_sim=10, seme=1)


def test_bootstrap_lunghezze_diverse():
    with pytest.raises(ValueError):
        bootstrap_regola(np.array([1.0, 2.0, 3.0]), np.array([1, 0]), n_sim=10, seme=1)


def test_bootstrap_segnale_tutto_zero():
    with pytest.raises(ValueError):
        bootstrap_regola(np.array([1.0, 2.0, 3.0]), np.array([0, 0, 0]), n_sim=10, seme=1)


def test_bootstrap_segnale_tutto_uno():
    with pytest.raises(ValueError):
        bootstrap_regola(np.array([1.0, 2.0, 3.0]), np.array([1, 1, 1]), n_sim=10, seme=1)


def test_montecarlo_input_vuoto():
    with pytest.raises(ValueError):
        montecarlo_trade(np.array([]), n_sim=10, seme=1)


def test_seme_obbligatorio():
    with pytest.raises(ValueError):
        bootstrap_regola(np.array([1.0, 2.0, 3.0, 4.0]), np.array([1, 0, 1, 0]),
                         n_sim=10, seme=None)
