"""test_funding_carry_p34.py — P34-F1 (stima funding del gate) e P34-F4
(verifica tariffa X-Perp).

Disciplina del progetto: per ogni regola un test che la fa scattare. Ogni
test fallisce sul codice pre-P34 (il gate usava il min degli ultimi 3
periodi e non verificava la tariffa di listino).
"""
from __future__ import annotations

import pytest

from money.funding_carry import (
    TARIFFA_XPERP_DICHIARATA,
    stima_funding,
    verifica_tariffa_xperp,
)


class MockFundingP34:
    """Solo endpoint funding: tariffa corrente e history pilotabili."""

    def __init__(self, corrente="0.0001", storia=None):
        self.corrente = corrente
        self.storia = list(storia or [])

    def publicGetPublicFundingRate(self, params):
        return {"data": [{"fundingRate": self.corrente}]}

    def publicGetPublicFundingRateHistory(self, params):
        return {"data": [{"fundingRate": str(v)} for v in self.storia]}


# ── F1: X-Perp (tariffa fissa) ──────────────────────────────────────────────

def test_xperp_corrente_uguale_dichiarata_ok_e_fonte():
    s = stima_funding(MockFundingP34(corrente="0.0001"),
                      "DOT-USD_UM_XPERP-310808")
    assert s.ok
    assert s.valore == pytest.approx(TARIFFA_XPERP_DICHIARATA, abs=1e-15)
    assert "tariffa fissa X-Perp" in s.fonte
    assert s.periodi == 0


def test_xperp_corrente_scostata_rifiuta_con_motivo():
    """La tariffa di listino e' cambiata: allarme, MAI apertura."""
    s = stima_funding(MockFundingP34(corrente="0.00015"),
                      "DOT-USD_UM_XPERP-310808")
    assert not s.ok
    assert "cambiata" in s.motivo
    assert "0.01500000%" in s.motivo


def test_xperp_corrente_negativa_rifiuta():
    """Il segno si conserva anche su X-Perp: tariffa negativa = rifiuto."""
    s = stima_funding(MockFundingP34(corrente="-0.0001"),
                      "DOT-USD_UM_XPERP-310808")
    assert not s.ok
    assert s.valore < 0


# ── F1: SWAP (p10 rolling) ──────────────────────────────────────────────────

def test_swap_p10_positivo_con_finestra_sufficiente():
    storia = [0.0001] * 29 + [0.0005, 0.0006]
    s = stima_funding(MockFundingP34(storia=storia), "DOT-USDT-SWAP")
    assert s.ok
    assert s.valore == pytest.approx(0.0001, abs=1e-12)
    assert "p10 rolling" in s.fonte
    assert s.periodi == 31


def test_swap_p10_negativo_conserva_segno_e_rifiuta():
    """Lezione fix audit 19/10: il segno si conserva — p10 negativo =
    il gate vede un valore negativo e rifiuta."""
    storia = ["-0.0002"] * 30 + ["0.0001"] * 5
    s = stima_funding(MockFundingP34(storia=storia), "DOT-USDT-SWAP")
    assert not s.ok
    assert s.valore < 0
    assert "non positivo" in s.motivo


def test_swap_campione_insufficiente_rifiuta():
    """n < 30 -> rifiuto con motivo, mai un default permissivo."""
    s = stima_funding(MockFundingP34(storia=["0.0001"] * 12), "DOT-USDT-SWAP")
    assert not s.ok
    assert "campione insufficiente" in s.motivo
    assert s.periodi == 12


def test_strumento_ignoto_rifiuta():
    s = stima_funding(MockFundingP34(), "DOT-FOO-BAR")
    assert not s.ok
    assert "non riconosciuto" in s.motivo


def test_lettura_fallita_fail_closed():
    class Boom:
        def publicGetPublicFundingRate(self, params):
            raise RuntimeError("rete giu'")

    s = stima_funding(Boom(), "DOT-USD_UM_XPERP-310808")
    assert not s.ok
    assert s.valore == 0.0
    assert "fallita" in s.motivo


# ── F4: watchdog tariffa ────────────────────────────────────────────────────

def test_verifica_tariffa_uguale_ok():
    ok, motivo = verifica_tariffa_xperp(0.0001)
    assert ok and motivo == ""


def test_verifica_tariffa_scostata_allarme():
    ok, motivo = verifica_tariffa_xperp(0.0002)
    assert not ok
    assert "0.02000000%" in motivo and "0.01000000%" in motivo
