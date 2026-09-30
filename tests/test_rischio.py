#!/usr/bin/env python3
"""Test del motore di rischio: ogni guardia ha un test che la fa **scattare**.

Una guardia senza un test che la viola e' una guardia che non esiste: e' la lezione di
\`tools/kill_switch.py:16\`, che definisce \`DRAWDOWN_THRESHOLD\` e non lo confronta con niente.
"""
from __future__ import annotations

import math

import pytest

from money.rischio import (
    KILL_SWITCH_AZIONI,
    ParametriRischio,
    StatoRischio,
    dimensione_da_rischio,
    distanza_liquidazione,
    fattore_vol_target,
    kelly_frazionario,
    kill_switch_azioni,
    stop_da_atr,
    verifica_pre_trade,
)

GIORNO_MS = 86_400_000
T0 = 1_700_000_000_000


def _ordine(**kw):
    """Un ordine sano di default: equity 10.000, acquisto a 100 con stop a 95, 5 unita'."""
    base = dict(equity=10_000.0, simbolo="BTC/EUR", lato="buy", prezzo=100.0,
                quantita=5.0, prezzo_stop=95.0, leva=1.0)
    base.update(kw)
    return verifica_pre_trade(**base)


# --- stop e dimensionamento ------------------------------------------------------

def test_stop_da_atr_dal_lato_giusto():
    assert stop_da_atr(100.0, 2.0, "buy") == pytest.approx(95.0)
    assert stop_da_atr(100.0, 2.0, "sell") == pytest.approx(105.0)


@pytest.mark.parametrize("prezzo,atr", [(0.0, 2.0), (100.0, 0.0)])
def test_stop_da_atr_rifiuta_input_degeneri(prezzo, atr):
    with pytest.raises(ValueError):
        stop_da_atr(prezzo, atr, "buy")


def test_dimensione_da_rischio_rispetta_il_budget():
    """10.000 di equity, 0,25% di rischio, stop a 5 punti: 25/5 = 5 unita' esatte."""
    q = dimensione_da_rischio(10_000.0, 100.0, 95.0, 0.0025)
    assert q == pytest.approx(5.0)
    assert q * abs(100.0 - 95.0) == pytest.approx(25.0)


def test_dimensione_da_rischio_rifiuta_stop_coincidente():
    with pytest.raises(ValueError, match="coincidente"):
        dimensione_da_rischio(10_000.0, 100.0, 100.0)


def test_kelly_negativo_non_si_dimensiona():
    """Con edge <= 0 la size e' zero: non si dimensiona un'operazione a expectancy negativa."""
    assert kelly_frazionario(-0.01, 0.05) == 0.0
    assert kelly_frazionario(0.0, 0.05) == 0.0


def test_kelly_frazionario_e_troncato_a_uno():
    assert kelly_frazionario(10.0, 0.01) == 1.0


# --- vol targeting: la formula della spec P2 -------------------------------------

def _serie(sd_giornaliera: float, n: int = 30):
    """Rendimenti alternati +/- sd: deviazione standard controllata e media ~0."""
    return [sd_giornaliera if i % 2 == 0 else -sd_giornaliera for i in range(n)]


def test_vol_target_riduce_l_esposizione_quando_la_volatilita_e_alta():
    f = fattore_vol_target(_serie(0.05), vol_target_annua=0.60)
    assert 0.0 < f < 1.0
    # 5% giornaliero -> ~95% annualizzato -> il fattore dev'essere ~0,6
    assert f == pytest.approx(0.60 / (math.sqrt(365.0) * 0.05 * math.sqrt(30 / 29)), rel=0.05)


def test_vol_target_non_aumenta_l_esposizione_quando_la_volatilita_e_bassa():
    assert fattore_vol_target(_serie(0.005), vol_target_annua=0.60) == 1.0


def test_vol_target_fallisce_chiuso_senza_dati():
    """Meno di due osservazioni: nessun dato, nessuna esposizione. Non 'piena per default'."""
    assert fattore_vol_target([]) == 0.0
    assert fattore_vol_target([0.01]) == 0.0
    assert fattore_vol_target([0.01, 0.01]) == 0.0   # varianza nulla: non si presume niente


def test_vol_target_rifiuta_un_target_non_positivo():
    with pytest.raises(ValueError):
        fattore_vol_target(_serie(0.02), vol_target_annua=0.0)


def test_distanza_liquidazione():
    assert distanza_liquidazione(1.0) == 1.0
    assert distanza_liquidazione(2.0) == pytest.approx(0.495)
    assert distanza_liquidazione(4.0) == pytest.approx(0.245)


# --- il controllo pre-trade -------------------------------------------------------

def test_un_ordine_corretto_e_ammesso():
    d = _ordine()
    assert d.ok and bool(d)
    assert d.quantita == pytest.approx(5.0)
    assert d.nozionale == pytest.approx(500.0)
    assert d.rischio_eur == pytest.approx(25.0)


def test_stop_dal_lato_sbagliato_e_rifiutato():
    d = _ordine(prezzo_stop=105.0)
    assert not d.ok
    assert any("sotto l'ingresso" in m for m in d.motivi)


def test_uno_stop_assente_e_rifiutato():
    d = _ordine(prezzo_stop=0.0)
    assert not d.ok


@pytest.mark.parametrize("kw", [{"prezzo": float("nan")}, {"equity": float("nan")},
                                {"quantita": float("inf")}])
def test_un_valore_non_finito_rifiuta_l_ordine(kw):
    """Fail-closed: un NaN non e' un numero grande, e' un'assenza."""
    d = _ordine(**kw)
    assert not d.ok
    assert any("finito" in m for m in d.motivi)


def test_equity_non_positiva_rifiuta():
    assert not _ordine(equity=0.0).ok


def test_la_concentrazione_eccessiva_e_rifiutata():
    d = _ordine(quantita=30.0)          # nozionale 3.000 > 25% di 10.000
    assert not d.ok
    assert any("concentrazione" in m or "dell'equity" in m for m in d.motivi)


def test_il_calore_di_portafoglio_e_rifiutato():
    """0,25% + 0,25% non deve superare l'1%: qui si porta l'apertura a 80 e si sfora."""
    d = _ordine(rischio_aperto_eur=80.0)
    assert not d.ok
    assert any("calore" in m for m in d.motivi)


def test_la_correlazione_alta_dimezza_la_size_ma_ammette():
    d = _ordine(correlazione_media=0.9)
    assert d.ok
    assert d.quantita == pytest.approx(2.5)
    assert any("correlazione" in m for m in d.motivi)


def test_la_leva_oltre_il_massimo_e_rifiutata():
    d = _ordine(leva=3.0)
    assert not d.ok
    assert any("leva" in m for m in d.motivi)


def test_una_liquidazione_troppo_vicina_e_rifiutata():
    """Con leva 4 la liquidazione e' a 24,5%: sotto il minimo del 25%, si rifiuta."""
    larghi = ParametriRischio(leva_massima=10.0)
    d = _ordine(leva=4.0, parametri=larghi)
    assert not d.ok
    assert any("liquidazione" in m for m in d.motivi)


def test_la_concentrazione_sulla_stessa_beta_e_rifiutata():
    """N bot long sulla stessa beta sono una posizione sola travestita."""
    d = _ordine(esposizione_beta_eur=4900.0, beta_del_simbolo=1.0)
    assert not d.ok
    assert any("beta" in m for m in d.motivi)


def test_il_nozionale_sotto_il_minimo_e_rifiutato():
    d = _ordine(quantita=0.001)         # nozionale 0,10 < 1,00
    assert not d.ok
    assert any("minimo" in m for m in d.motivi)


# --- il governatore dei drawdown --------------------------------------------------

def test_il_governatore_fallisce_chiuso_senza_osservazioni():
    """Un sistema che non sa quanto vale non opera. E' il contrario di peak_capital = 200."""
    a = StatoRischio().arresto()
    assert a is not None and a.livello == "stato_inattendibile"
    assert "equity" in a.motivo


def test_il_governatore_azzera_la_giornata_dopo_una_perdita():
    s = StatoRischio()
    s.aggiorna(T0, 10_000.0)
    s.aggiorna(T0 + 3_600_000, 9_700.0)                 # -3% nella giornata
    assert s.arresto().livello == "giornaliero"
    s.aggiorna(T0 + GIORNO_MS, 9_700.0)                 # giorno nuovo: la perdita di giornata riparte
    assert s.arresto() is None
    assert s.perdita_giorno() == pytest.approx(0.0)


def test_il_governatore_fa_scattare_l_arresto_al_dieci_per_cento():
    s = StatoRischio()
    s.aggiorna(T0, 10_000.0)
    s.aggiorna(T0 + 3_600_000, 8_900.0)                 # -11% dal picco
    a = s.arresto()
    assert a is not None and a.livello == "arresto"
    assert s.drawdown_da_picco() == pytest.approx(0.11)


def test_il_governatore_chiude_al_venti_per_cento():
    s = StatoRischio()
    s.aggiorna(T0, 10_000.0)
    s.aggiorna(T0 + 3_600_000, 7_900.0)                 # -21% dal picco
    assert s.arresto().livello == "chiusura"


def test_il_governatore_rifiuta_una_serie_non_monotona():
    s = StatoRischio()
    s.aggiorna(T0 + 10_000, 10_000.0)
    with pytest.raises(ValueError, match="monotona"):
        s.aggiorna(T0, 9_000.0)


def test_il_governatore_rifiuta_un_equity_non_positivo():
    s = StatoRischio()
    with pytest.raises(ValueError):
        s.aggiorna(T0, 0.0)


def test_il_governatore_rivaluta_la_perdita_settimanale():
    s = StatoRischio()
    s.aggiorna(T0, 10_000.0)
    s.aggiorna(T0 + 2 * GIORNO_MS, 9_400.0)             # -6% dal picco: sotto il 10% di arresto
    a = s.arresto()
    assert a is not None and a.livello in ("settimanale", "giornaliero")


# --- il kill switch: la sequenza e' il contenuto ----------------------------------

def test_le_azioni_del_kill_switch_sono_in_ordine_e_complete():
    azioni = kill_switch_azioni("test")
    assert azioni[0] == "motivo: test"
    assert len(azioni) == 1 + len(KILL_SWITCH_AZIONI) == 7
    corpo = azioni[1:]
    assert "scheduler" in corpo[0]                      # prima lo scheduler: i watchdog riavviano
    assert "client_id" in corpo[1]                      # mai un cancel-all
    assert "chiudere le posizioni" in corpo[2]          # il legacy si fermava al passo 2
    assert "ledger" in corpo[3]
    assert "RUMOROSO" in corpo[4]                       # alert_sent = True senza inviare: mai piu'
    assert "riconciliare" in corpo[5]
