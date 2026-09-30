#!/usr/bin/env python3
"""Test delle correzioni statistiche: molteplicita', i.i.d., overfitting.

Il difetto che questi test coprono e' dichiarato da `cancello.py` stesso: "il cancello non vede
il numero di tentativi" e "l'autocorrelazione NON viene corretta". Un difetto dichiarato e non
corretto resta un difetto.
"""
from __future__ import annotations

import math
import random

import pytest

from money.statistica import (
    autocorrelazione,
    deviazione,
    intervallo_media_blocchi,
    intervallo_media_iid,
    media,
    n_effettivo,
    pbo_cscv,
    sharpe,
    sharpe_atteso_massimo,
    sharpe_deflazionato,
    t_stat,
    t_stat_newey_west,
    varianza_da_tentativi,
    verdetto_statistico,
)


def _ar1(n: int = 400, rho: float = 0.85, sd: float = 1.0, seme: int = 7):
    """Serie AR(1): e' il caso in cui l'assunzione i.i.d. e' piu' sbagliata."""
    rng = random.Random(seme)
    x = 0.0
    fuori = []
    for _ in range(n):
        x = rho * x + rng.gauss(0.0, sd)
        fuori.append(x)
    return fuori


def _ampiezza(intervallo):
    return intervallo[1] - intervallo[0]


# --- la dipendenza temporale non si puo' ignorare ---------------------------------

def test_il_bootstrap_a_blocchi_allarga_l_intervallo_su_una_serie_autocorrelata():
    """E' il cuore della correzione: l'i.i.d. dichiara stretto cio' che e' largo."""
    serie = _ar1()
    iid = intervallo_media_iid(serie, ricampionamenti=2000)
    blocchi = intervallo_media_blocchi(serie, blocco=20, ricampionamenti=2000)
    assert _ampiezza(blocchi) > _ampiezza(iid) * 1.5


def test_il_bootstrap_a_blocchi_non_allarga_una_serie_indipendente():
    """Se i dati sono davvero indipendenti, i due metodi devono dare quasi lo stesso intervallo."""
    rng = random.Random(11)
    serie = [rng.gauss(0.0, 1.0) for _ in range(400)]
    iid = _ampiezza(intervallo_media_iid(serie, ricampionamenti=2000))
    blocchi = _ampiezza(intervallo_media_blocchi(serie, blocco=1, ricampionamenti=2000))
    assert blocchi == pytest.approx(iid, rel=0.25)


@pytest.mark.parametrize("cattivo", [[], [1.0]])
def test_il_bootstrap_rifiuta_serie_troppo_corte(cattivo):
    with pytest.raises(ValueError):
        intervallo_media_iid(cattivo)
        intervallo_media_blocchi(cattivo, blocco=1)


def test_il_bootstrap_rifiuta_pochi_ricampionamenti():
    with pytest.raises(ValueError):
        intervallo_media_blocchi([1.0, 2.0, 3.0], blocco=1, ricampionamenti=10)


def test_autocorrelazione_e_coerente_col_calcolo_diretto():
    serie = [1.0, 2.0, 3.0, 4.0, 5.0]
    rho1 = autocorrelazione(serie, 1)
    m = media(serie)
    atteso = sum((serie[i] - m) * (serie[i + 1] - m) for i in range(4)) / sum(
        (x - m) ** 2 for x in serie)
    assert rho1 == pytest.approx(atteso)


# --- quante scommesse indipendenti ci sono davvero --------------------------------

def test_n_effettivo_con_durata_media_e_una_divisione():
    assert n_effettivo([0.1] * 10, durata_media_barre=5.0) == pytest.approx(2.0)


def test_n_effettivo_rifiuta_una_durata_non_positiva():
    with pytest.raises(ValueError):
        n_effettivo([0.1, 0.2], durata_media_barre=0.0)


def test_n_effettivo_crolla_su_una_serie_autocorrelata():
    """35 operazioni con autocorrelazione alta non sono 35 scommesse: sono una frazione."""
    serie = _ar1(n=200, rho=0.9)
    assert n_effettivo(serie) < len(serie) / 3


def test_newey_west_allarga_l_errore_standard():
    serie = _ar1(n=600, rho=0.8)
    t_naive = t_stat(serie)
    t_nw, se_nw = t_stat_newey_west(serie)
    assert se_nw is not None and t_nw is not None
    se_naive = deviazione(serie) / math.sqrt(len(serie))
    assert se_nw > se_naive * 1.5
    assert abs(t_nw) < abs(t_naive)


def test_newey_west_non_e_definito_su_serie_troppo_corte():
    assert t_stat_newey_west([0.1, 0.2]) == (None, None)


def test_t_stat_non_definito_con_dispersione_nulla():
    assert t_stat([0.01] * 10) is None


# --- molteplicita': il massimo di N prove non e' un edge --------------------------

def test_lo_sharpe_atteso_massimo_e_zero_con_un_solo_tentativo():
    assert sharpe_atteso_massimo(1, 1.0) == 0.0


def test_lo_sharpe_atteso_massimo_cresce_coi_tentativi():
    a = sharpe_atteso_massimo(10, 1.0)
    b = sharpe_atteso_massimo(1000, 1.0)
    assert 0.0 < a < b


def test_lo_sharpe_deflazionato_cala_quando_i_tentativi_crescono():
    """Lo stesso risultato, dopo 1 tentativo e dopo 1000, non e' lo stesso oggetto."""
    comuni = dict(sharpe_osservato=0.30, n_osservazioni=250,
                  varianza_sharpe_tentativi=0.01)
    uno = sharpe_deflazionato(n_tentativi=1, **comuni)["dsr"]
    dieci = sharpe_deflazionato(n_tentativi=10, **comuni)["dsr"]
    mille = sharpe_deflazionato(n_tentativi=1000, **comuni)["dsr"]
    assert uno > dieci > mille


def test_lo_sharpe_deflazionato_rifiuta_una_varianza_negativa():
    with pytest.raises(ValueError):
        sharpe_deflazionato(0.3, 100, 10, -1.0)


def test_lo_sharpe_deflazionato_rifiuta_troppe_poche_osservazioni():
    with pytest.raises(ValueError):
        sharpe_deflazionato(0.3, 1, 10, 0.01)


def test_varianza_da_tentativi():
    assert varianza_da_tentativi([1.0, 3.0]) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        varianza_da_tentativi([1.0])


def test_sharpe_annualizzato_e_il_periodico_per_radice_dei_periodi():
    serie = [0.01, -0.005, 0.02, 0.0, 0.015]
    assert sharpe(serie, periodi_anno=365.0) == pytest.approx(sharpe(serie) * math.sqrt(365.0))


# --- PBO: la selezione era informativa o era rumore? ------------------------------

def test_pbo_e_alto_quando_le_configurazioni_sono_rumore():
    """Dieci strategie fatte solo di rumore: la migliore in campione e' una moneta fuori."""
    rng = random.Random(3)
    serie = [[rng.gauss(0.0, 0.02) for _ in range(240)] for _ in range(10)]
    esito = pbo_cscv(serie, blocchi=10)
    assert 0.15 <= esito["pbo"] <= 0.85
    assert esito["n_combinazioni"] > 0


def test_pbo_e_basso_quando_esiste_un_edge_vero():
    """Una configurazione ha un drift reale: vince in campione E fuori. Selezione informativa."""
    rng = random.Random(5)
    serie = [[rng.gauss(0.0005, 0.01) for _ in range(240)] for _ in range(7)]
    serie.append([0.004 + rng.gauss(0.0, 0.002) for _ in range(240)])
    assert pbo_cscv(serie, blocchi=10)["pbo"] < 0.2


def test_pbo_valida_gli_input():
    with pytest.raises(ValueError, match="stessa lunghezza"):
        pbo_cscv([[0.1] * 40, [0.1] * 30], blocchi=10)
    with pytest.raises(ValueError, match="pari"):
        pbo_cscv([[0.1] * 40, [0.1] * 40], blocchi=9)
    with pytest.raises(ValueError, match="almeno 2"):
        pbo_cscv([[0.1] * 40], blocchi=10)


# --- il verdetto statistico, in un posto solo -------------------------------------

def test_il_verdetto_statistico_raccoglie_tutte_le_correzioni():
    serie = _ar1(n=200)
    v = verdetto_statistico(serie, durata_media_barre=20.0, n_tentativi=8,
                            varianza_sharpe_tentativi=0.01, seme=20260101)
    assert v["n"] == 200
    assert v["n_effettivo"] == pytest.approx(10.0)
    assert v["intervallo_iid"] is not None
    assert v["intervallo_blocchi"] is not None
    assert v["t_stat_newey_west"] is not None
    assert v["dsr"] is not None
    assert v["allargamento_blocchi"] > 1.0
    # Riproducibilita': stesso seme, stesso verdetto.
    assert verdetto_statistico(serie, durata_media_barre=20.0, seme=20260101)["intervallo_blocchi"] \
        == v["intervallo_blocchi"]
