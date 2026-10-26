"""test_chiusura_carry_p34.py — P34-F2: la chiusura economica non chiude
PRIMA del pareggio reale.

Fixture: il ciclo ADA chiuso il 26/10 (prove/REGISTRO_ESPERIMENTI.md,
voce 26/10): netto MTM alla chiusura +0,093 USDC, realizzato -0,157 USDC
perche' mancavano fee di uscita + basis (~0,25 USDC su nozionale ~90).
Con la regola P34 la chiusura economica rifiuta, quella di emergenza
(vecchio criterio netto >= 0) accetta.
"""
from __future__ import annotations

import pytest

from money.chiusura_carry import (
    chiusura_economica,
    chiusura_emergenza,
    stima_costi_uscita,
)


# ── fixture ADA 26/10 (criterio di accettazione 3 della REQ) ────────────────

def test_ada_26_10_economica_rifiuta_emergenza_accetta():
    """netto 0,093 < fee_uscita+basis 0,25: economica rifiuta, emergenza accetta."""
    dec_e = chiusura_economica(netto_stimato=0.093,
                               fee_uscita=0.121, basis_uscita=0.129)
    assert not dec_e.ok
    assert dec_e.soglia == pytest.approx(0.25)
    assert "pareggio reale" in " ".join(dec_e.motivi)
    dec_x = chiusura_emergenza(netto_stimato=0.093)
    assert dec_x.ok


# ── la soglia ───────────────────────────────────────────────────────────────

def test_economica_chiude_solo_sopra_soglia():
    assert chiusura_economica(0.25, 0.121, 0.129).ok
    assert not chiusura_economica(0.2499, 0.121, 0.129).ok


def test_economica_margine_alza_la_soglia():
    assert chiusura_economica(0.26, 0.121, 0.129, margine=0.01).ok
    assert not chiusura_economica(0.2599, 0.121, 0.129, margine=0.01).ok


def test_input_non_finiti_fail_closed():
    assert not chiusura_economica(float("nan"), 0.1, 0.1).ok
    assert not chiusura_economica(0.1, float("inf"), 0.1).ok
    assert not chiusura_emergenza(float("inf")).ok


# ── emergenza: il vecchio criterio netto >= 0 ───────────────────────────────

def test_emergenza_netto_negativo_rifiuta():
    dec = chiusura_emergenza(-0.05)
    assert not dec.ok
    assert "negativo" in " ".join(dec.motivi)


# ── stima costi di uscita dalle tariffe verificate di money.costi ───────────

def test_stima_costi_uscita_da_tariffe_costi_py():
    """Fee: spot taker 0,10% + perp taker 0,05%. Basis: mezzo spread per
    gamba (spot venduto al bid, perp ricomprata all'ask)."""
    c = stima_costi_uscita(noz_spot=90.0, noz_perp=90.0,
                           bid_spot=0.998, ask_spot=1.002,
                           bid_perp=0.998, ask_perp=1.002)
    assert c.fee_uscita == pytest.approx(90.0 * 0.0010 + 90.0 * 0.0005)
    mezzo = 0.004 / 2.0          # (1.002-0.998)/(1.002+0.998)
    assert c.basis_uscita == pytest.approx(90.0 * mezzo + 90.0 * mezzo)
    assert c.totale == pytest.approx(c.fee_uscita + c.basis_uscita)
    assert "okx_eea_con_perp" in c.fonte and "okx_eea_swap_lv1" in c.fonte


def test_stima_costi_uscita_input_non_finito_solleva():
    with pytest.raises(ValueError):
        stima_costi_uscita(float("nan"), 90.0, 0.998, 1.002, 0.998, 1.002)


def test_stima_costi_uscita_prezzo_non_positivo_solleva():
    with pytest.raises(ValueError):
        stima_costi_uscita(90.0, 90.0, 0.0, 1.002, 0.998, 1.002)
