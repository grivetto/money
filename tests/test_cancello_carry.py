#!/usr/bin/env python3
"""Test del gate CARRY (`money.esecuzione.cancello_carry`).

Disciplina del progetto: per ogni regola un test che la fa SCATTARE.
Il gate deve RIFIUTARE quando una condizione del carry non e' soddisfatta,
e AMMETTERE solo l'hedge group delta-neutral economico.
"""
from __future__ import annotations

import pytest

from money.esecuzione.cancello_carry import DecisioneCarry, gate_carry


def test_ammette_un_carry_delta_neutrale_economico():
    """Il caso base: 1x, delta quasi zero, funding che copre i costi in 30 giorni."""
    d = gate_carry(nozionale=90.0, funding_atteso=0.0001,   # 0,01%/8h
                   costo_ciclo=0.0034,                       # 0,34% per ciclo
                   delta_relativo=0.0)
    assert d.ok, d.motivi
    assert d.periodi_payback == pytest.approx(34.0, rel=0.01)
    assert d.distanza_liq > 0.9


def test_rifiuta_se_funding_negativo():
    """Funding negativo = il carry paga invece di incassare."""
    d = gate_carry(nozionale=90.0, funding_atteso=-0.0001,
                   costo_ciclo=0.0034, delta_relativo=0.0)
    assert not d.ok
    assert any("funding" in m for m in d.motivi)


def test_rifiuta_se_payback_troppo_lungo():
    """Funding minuscolo: i costi non si ripagano in tempo utile."""
    d = gate_carry(nozionale=90.0, funding_atteso=0.00001,   # 0,001%/8h
                   costo_ciclo=0.0034, delta_relativo=0.0)
    assert not d.ok
    assert any("payback" in m for m in d.motivi)


def test_rifiuta_se_delta_troppo_alto():
    """Le gambe non allineate = esposizione direzionale non voluta."""
    d = gate_carry(nozionale=90.0, funding_atteso=0.0001,
                   costo_ciclo=0.0034, delta_relativo=0.02)   # 2%
    assert not d.ok
    assert any("delta" in m for m in d.motivi)


def test_rifiuta_se_leva_non_e_1x():
    """Il carry non usa leva: 2x e' un altro strumento, un'altra classe di rischio."""
    d = gate_carry(nozionale=90.0, funding_atteso=0.0001,
                   costo_ciclo=0.0034, delta_relativo=0.0, leva=2.0)
    assert not d.ok
    assert any("leva" in m for m in d.motivi)


def test_rifiuta_se_costo_ciclo_non_credibile():
    """Costi a zero = fotografia sbagliata: non si apre su numeri inventati."""
    d = gate_carry(nozionale=90.0, funding_atteso=0.0001,
                   costo_ciclo=0.0, delta_relativo=0.0)
    assert not d.ok
    assert any("costo" in m for m in d.motivi)


def test_rifiuta_nozionale_non_positivo():
    d = gate_carry(nozionale=0.0, funding_atteso=0.0001,
                   costo_ciclo=0.0034, delta_relativo=0.0)
    assert not d.ok
    assert any("nozionale" in m for m in d.motivi)


def test_fail_closed_su_input_non_finito():
    """Un NaN non passa: mai un default permissivo."""
    d = gate_carry(nozionale=float("nan"), funding_atteso=0.0001,
                   costo_ciclo=0.0034, delta_relativo=0.0)
    assert not d.ok
    assert any("non finito" in m for m in d.motivi)


def test_il_gate_e_vero_o_falso():
    """La decisione e' utilizzabile come booleano (come Decisione del gate direzionale)."""
    buono = gate_carry(nozionale=90.0, funding_atteso=0.0001,
                       costo_ciclo=0.0034, delta_relativo=0.0)
    cattivo = gate_carry(nozionale=90.0, funding_atteso=-0.0001,
                         costo_ciclo=0.0034, delta_relativo=0.0)
    assert bool(buono) is True
    assert bool(cattivo) is False


def test_la_distanza_di_liquidazione_e_quella_della_funzione_esistente():
    """Il gate NON reinventa la distanza: usa `rischio.distanza_liquidazione`."""
    from money.rischio import distanza_liquidazione
    attesa = distanza_liquidazione(1.0)
    d = gate_carry(nozionale=90.0, funding_atteso=0.0001,
                   costo_ciclo=0.0034, delta_relativo=0.0)
    assert d.distanza_liq == pytest.approx(attesa)
