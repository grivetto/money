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
    alert_tariffa_xperp_solo_aperte,
    coppia_canary_aperta,
    coppie_con_posizione_aperta,
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


# ── Review P34 29/10 (F3): tariffa SOLO per coppie con posizione aperta ─────

def test_watch_tariffa_solo_coppie_aperte():
    """Review F3: con ADA chiusa e DOT aperta nello stato, uno scostamento
    tariffa genera UN solo alert (DOT). ADA — chiusa dal 26/10 — NON viene
    nemmeno confrontata: era lo spam di ALERT/RECOVERY su coppia chiusa."""
    stato = {"coppie": {
        "DOT": {"aperta": True, "ct_perp": 253.0},
        "ADA": {"aperta": False, "ct_perp": 0.0},
    }}
    correnti = {
        "DOT-USD_UM_XPERP-310808": 0.00015,   # scostata + aperta → 1 alert
        "ADA-USD_UM_XPERP-310404": 0.0002,    # scostata MA chiusa → 0 alert
        "DOGE-USD_UM_XPERP-310404": 0.0002,   # non tracciata nello stato → skip
        "LINK-USD_UM_XPERP-310523": 0.0001,
        "LTC-USD_UM_XPERP-310404": 0.0001,
        "AVAX-USD_UM_XPERP-310530": 0.0001,
    }
    alert = alert_tariffa_xperp_solo_aperte(stato, correnti)
    assert [a[0] for a in alert] == ["DOT-USD_UM_XPERP-310808"]
    assert "0.01500000%" in alert[0][1]
    assert "0.01000000%" in alert[0][1]


def test_watch_tariffa_nessuna_coppia_aperta_nessun_alert():
    """Stato senza coppie aperte (o illeggibile → coppie {}): nessun
    confronto, nessun alert — l'allarme tariffa non esiste dove il carry
    non esiste."""
    stato = {"coppie": {"DOT": {"aperta": False}, "ADA": {"aperta": False}}}
    alert = alert_tariffa_xperp_solo_aperte(
        stato, {"DOT-USD_UM_XPERP-310808": 0.0002})
    assert alert == []
    assert alert_tariffa_xperp_solo_aperte({}, {}) == []


# ── Review P34 follow-up REQ-024 (29/10): copertura tariffa CANARY DOGE ─────

CANARY_APERTO_REQ24 = {"status": "open",
                       "inst": "DOGE-USD_UM_XPERP-310404",
                       "last_delta": 0.11}


def test_watch_tariffa_canary_aperto_copre_doge():
    """REQ-024: con DOT aperta (carry_stato) e canary DOGE aperto
    (canary_state.json) il filtro copre ESATTAMENTE {DOT, DOGE} (ok=2) e ADA
    chiusa resta saltata: DOGE era il buco di F3, ora e' di nuovo nel watch."""
    stato = {"coppie": {"DOT": {"aperta": True}, "ADA": {"aperta": False}}}
    assert coppie_con_posizione_aperta(
        stato, CANARY_APERTO_REQ24) == {"DOT", "DOGE"}
    correnti = {
        "DOT-USD_UM_XPERP-310808": 0.0001,
        "DOGE-USD_UM_XPERP-310404": 0.0001,
        "ADA-USD_UM_XPERP-310404": 0.0002,   # chiusa: MAI confrontata
    }
    assert alert_tariffa_xperp_solo_aperte(
        stato, correnti, canary_stato=CANARY_APERTO_REQ24) == []


def test_watch_tariffa_canary_scostato_allarma():
    """Il canary e' lo strumento su cui si incassa funding: uno scostamento
    della sua tariffa DEVE produrre l'alert (prima di REQ-024 era saltato)."""
    stato = {"coppie": {"DOT": {"aperta": True}}}
    correnti = {
        "DOT-USD_UM_XPERP-310808": 0.0001,    # in linea
        "DOGE-USD_UM_XPERP-310404": 0.00015,  # scostata + canary aperto
    }
    alert = alert_tariffa_xperp_solo_aperte(
        stato, correnti, canary_stato=CANARY_APERTO_REQ24)
    assert [a[0] for a in alert] == ["DOGE-USD_UM_XPERP-310404"]
    assert "0.01500000%" in alert[0][1]


def test_watch_tariffa_canary_chiuso_mai_confrontato():
    """Canary chiuso: la coppia NON entra nel filtro (coppie chiuse mai) e
    non c'e' nulla da segnalare (nessun WARN)."""
    stato = {"coppie": {"DOT": {"aperta": True}}}
    chiuso = {"status": "closed", "inst": "DOGE-USD_UM_XPERP-310404"}
    assert coppia_canary_aperta(chiuso) == (None, None)
    assert coppie_con_posizione_aperta(stato, chiuso) == {"DOT"}
    assert alert_tariffa_xperp_solo_aperte(
        stato, {"DOGE-USD_UM_XPERP-310404": 0.0002},
        canary_stato=chiuso) == []


def test_watch_tariffa_canary_assente_o_illeggibile_warn():
    """Stato canary assente/illeggibile -> (None, motivo) per il WARN del
    watchdog, MAI eccezioni e MAI alert finto: senza stato verificabile la
    copertura DOGE non si inventa (la tariffa scostata qui sotto non deve
    produrre alcun alert)."""
    stato = {"coppie": {"DOT": {"aperta": True}}}
    correnti = {"DOGE-USD_UM_XPERP-310404": 0.0002}
    for rotto in (None, "stringa-non-dict", {}, {"status": ""},
                  {"status": "open"}):   # inst mancante
        coppia, motivo = coppia_canary_aperta(rotto)
        assert coppia is None and motivo
        assert alert_tariffa_xperp_solo_aperte(
            stato, correnti, canary_stato=rotto) == []
