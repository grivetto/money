"""test_tabellone.py — REQ-MERL-20261026-021: riga rendita + benchmark Earn.

Test OFFLINE (zero rete, zero chiavi) delle funzioni pure della riga rendita:
- parse_lending_rate: parsing del tasso Earn pubblico (payload reale come forma)
- finestra_recon: delta funding/fee tra ultima riga e riga ~N giorni prima
  (i campi delle righe sono CUMULATIVI: il delta e' il contributo della finestra)
- earn_stimato_usdc / rendita_riga: aritmetica con numeri noti
- earn_conto: saldo dal campo 'amt' (fallback loanAmt+pendingAmt) e
  fail-visible su saldo/rate 0 (mai +0.00 silenzioso)
- calcola_rendita end-to-end con fixture (jsonl + exchange finto + cambio fisso)
- fail-closed: serie corta, finestra < 1 giorno, equity assente, righe corrotte

Caricamento via importlib con cleanup di sys.modules (stesso pattern di
test_carry_apri.py): il modulo non deve restare in sys.modules dopo i test.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _carica_tabellone():
    """Carica scripts/tabellone.py via importlib, con ccxt stubato e cleanup.

    Stesso pattern di test_carry_apri.py: il modulo fa `import ccxt` in cima e
    la suite deve restare OFFLINE — i test della riga rendita non toccano mai
    ccxt (i chiamanti che lo usano ricevono un exchange finto).
    """
    percorso = REPO / "scripts" / "tabellone.py"
    spec = importlib.util.spec_from_file_location("tabellone_under_test", percorso)
    assert spec is not None and spec.loader is not None, f"modulo non trovato: {percorso}"
    precedenti = set(sys.modules)
    if "ccxt" not in sys.modules:
        sys.modules["ccxt"] = types.ModuleType("ccxt")
    try:
        modulo = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = modulo
        spec.loader.exec_module(modulo)
    finally:
        for nome in set(sys.modules) - precedenti:
            del sys.modules[nome]
    return modulo


def _riga(ts: float, funding: float, fee: float, data: str | None = None) -> dict:
    """Riga di recon.jsonl in forma reale: funding/fee CUMULATIVI per coppia."""
    return {"date": data or "2026-10-28",
            "checked_at": "2026-10-28T06:10:01+00:00",
            "checked_ts": ts,
            "totale": {"funding_usdc": funding, "fee_pagate_usdc": fee}}


# ---------------------------------------------------------------------------
# parse_lending_rate
# ---------------------------------------------------------------------------

def test_parse_lending_rate_estrate():
    tb = _carica_tabellone()
    payload = {"code": "0", "msg": "",
               "data": [{"avgAmt": "", "avgAmtUsd": "", "avgRate": "0.0354",
                         "ccy": "USDC", "estRate": "0.035", "preRate": "0.035"}]}
    assert tb.parse_lending_rate(payload) == {"apy": 0.035, "errore": None}


def test_parse_lending_rate_usa_avgrate_se_estrate_assente():
    tb = _carica_tabellone()
    payload = {"code": "0", "msg": "",
               "data": [{"avgRate": "0.0354", "ccy": "USDC", "estRate": ""}]}
    assert tb.parse_lending_rate(payload)["apy"] == pytest.approx(0.0354)


def test_parse_lending_rate_codice_errore():
    tb = _carica_tabellone()
    out = tb.parse_lending_rate({"code": "50011", "msg": "tasso non disponibile", "data": []})
    assert out["apy"] is None and "50011" not in out["errore"] and "tasso" in out["errore"]


def test_parse_lending_rate_payload_malformato():
    tb = _carica_tabellone()
    out = tb.parse_lending_rate({"code": "0", "data": [{"ccy": "USDC"}]})
    assert out["apy"] is None and out["errore"]


# ---------------------------------------------------------------------------
# leggi_jsonl / finestra_recon
# ---------------------------------------------------------------------------

def test_leggi_jsonl_salta_righe_corrotte(cartella):
    tb = _carica_tabellone()
    f = cartella / "recon.jsonl"
    f.write_text(json.dumps(_riga(100.0, 0.1, 0.2)) + "\n" +
                 "riga corrotta non json\n" +
                 json.dumps(_riga(200.0, 0.3, 0.4)) + "\n")
    assert len(tb.leggi_jsonl(str(f))) == 2


def test_finestra_recon_delta_funding_fee():
    tb = _carica_tabellone()
    giorni = 86400.0
    righe = [
        _riga(1000.0, 0.10, 0.05),          # base (piu' vecchia di 7g)
        _riga(1000.0 + 3 * giorni, 0.25, 0.11),
        _riga(1000.0 + 7 * giorni, 0.40, 0.17),   # ultima: esattamente a 7g
    ]
    out = tb.finestra_recon(righe, giorni=7.0)
    assert out["motivo"] is None
    assert out["giorni"] == pytest.approx(7.0)
    assert out["funding_usdc"] == pytest.approx(0.30)   # 0.40 - 0.10
    assert out["fee_usdc"] == pytest.approx(0.12)       # 0.17 - 0.05
    assert out["n_righe"] == 3


def test_finestra_recon_serie_corta_e_motivo():
    tb = _carica_tabellone()
    out = tb.finestra_recon([_riga(1000.0, 0.1, 0.2)], giorni=7.0)
    assert out["motivo"] and "insufficiente" in out["motivo"]
    assert out.get("funding_usdc") is None


def test_finestra_recon_finestra_minima_rifiutata():
    tb = _carica_tabellone()
    righe = [_riga(1000.0, 0.1, 0.2), _riga(1000.0 + 3600.0, 0.2, 0.3)]  # 1 ora
    out = tb.finestra_recon(righe, giorni=7.0)
    assert out["motivo"] and "1 giorno" in out["motivo"]


def test_finestra_recon_senza_base_usa_la_prima_riga():
    tb = _carica_tabellone()
    # serie di 4 giorni con finestra chiesta 7g: la base e' la prima riga
    giorni = 86400.0
    righe = [_riga(1000.0, 0.10, 0.05), _riga(1000.0 + 4 * giorni, 0.30, 0.13)]
    out = tb.finestra_recon(righe, giorni=7.0)
    assert out["giorni"] == pytest.approx(4.0)
    assert out["funding_usdc"] == pytest.approx(0.20)


def test_finestra_recon_valori_assenti():
    tb = _carica_tabellone()
    r1 = _riga(1000.0, 0.1, 0.2)
    r2 = _riga(1000.0 + 86400.0, 0.2, 0.3)
    del r2["totale"]["funding_usdc"]
    out = tb.finestra_recon([r1, r2], giorni=7.0)
    assert out["motivo"] and "assenti" in out["motivo"]


# ---------------------------------------------------------------------------
# aritmetica: earn stimato e rendita_riga
# ---------------------------------------------------------------------------

def test_earn_stimato_usdc():
    tb = _carica_tabellone()
    # 372.13679033 USDC al 1% annuo su 7 giorni
    atteso = 372.13679033 * 0.01 * 7.0 / 365.0
    assert tb.earn_stimato_usdc(372.13679033, 0.01, 7.0) == pytest.approx(atteso)


def test_rendita_riga_fixture_numeri_noti():
    tb = _carica_tabellone()
    # funding 0.18, fee 0.29, earn 0.07 su 7g, cambio 0.92, equity 1066.30
    out = tb.rendita_riga(0.18, 0.29, 0.07, 7.0, 0.92, 1066.30)
    assert out["netto_usdc_periodo"] == pytest.approx(-0.04)
    assert out["eur_giorno"] == pytest.approx(-0.04 / 7.0 * 0.92, abs=1e-4)
    assert out["pct_giorno"] == pytest.approx(-0.04 / 7.0 * 0.92 / 1066.30 * 100.0, abs=1e-6)


def test_rendita_riga_zero_equity_non_usato():
    tb = _carica_tabellone()
    # il guardiano dell'equity sta in calcola_rendita: qui pct = None, mai divisione per zero
    out = tb.rendita_riga(0.5, 0.2, 0.0, 7.0, 0.92, 0.0)
    assert out["eur_giorno"] == pytest.approx(0.3 / 7.0 * 0.92, abs=1e-4)
    assert out["pct_giorno"] is None


# ---------------------------------------------------------------------------
# calcola_rendita end-to-end con fixture
# ---------------------------------------------------------------------------

class MockEarnEx:
    """Exchange finto: solo financeSavingsBalance, con esito pilotabile."""

    def __init__(self, saldo=372.13679033, tasso="0.01", riga_usdc=True, fallisce=False):
        self.saldo = saldo
        self.tasso = tasso
        self.riga_usdc = riga_usdc
        self.fallisce = fallisce

    def privateGetFinanceSavingsBalance(self):
        if self.fallisce:
            raise ConnectionError("rate limit finto")
        riga = {"ccy": "USDC", "rate": self.tasso, "amt": str(self.saldo),
                "loanAmt": str(self.saldo), "earnings": "0.74531944",
                "pendingAmt": "0", "redemptAmt": ""}
        return {"data": [riga] if self.riga_usdc else [{"ccy": "BTC", "rate": "0", "loanAmt": "0"}]}


def test_calcola_rendita_fixture_completa(cartella):
    tb = _carica_tabellone()
    tb.prezzo_eur = lambda ccy: 0.92 if ccy == "USDC" else 1.0  # cambio fisso, zero rete
    giorni = 86400.0
    righe = [_riga(1000.0, 0.10, 0.05), _riga(1000.0 + 7 * giorni, 0.40, 0.17)]
    f = cartella / "recon.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in righe) + "\n")

    out = tb.calcola_rendita(MockEarnEx(), str(f), 7.0, 1066.30, "2026-10-28 15:30")
    assert out["motivo"] is None
    assert out["funding_usdc"] == pytest.approx(0.30)
    assert out["fee_usdc"] == pytest.approx(0.12)
    # earn stimato: 372.13679033 * 0.01 * 7 / 365 (arrotondato a 6 decimali)
    earn = round(372.13679033 * 0.01 * 7.0 / 365.0, 6)
    assert out["earn_stimato_usdc"] == pytest.approx(earn)
    netto = 0.30 - 0.12 + earn
    assert out["eur_giorno"] == pytest.approx(netto / 7.0 * 0.92, abs=1e-4)
    assert out["pct_giorno"] == pytest.approx(netto / 7.0 * 0.92 / 1066.30 * 100.0, abs=1e-6)
    assert out["data_calcolo"] == "2026-10-28 15:30"


def test_calcola_rendita_equity_assente():
    tb = _carica_tabellone()
    out = tb.calcola_rendita(MockEarnEx(), "/tmp/nonesiste.jsonl", 7.0, None, "d")
    assert out["motivo"] and "equity" in out["motivo"]


def test_calcola_rendita_recon_mancante():
    tb = _carica_tabellone()
    out = tb.calcola_rendita(MockEarnEx(), "/tmp/recon-inesistente-021.jsonl",
                             7.0, 1000.0, "d")
    assert out["motivo"] and "recon non leggibile" in out["motivo"]


def test_calcola_rendita_earn_assente_assume_zero(cartella):
    tb = _carica_tabellone()
    tb.prezzo_eur = lambda ccy: 0.92
    giorni = 86400.0
    righe = [_riga(1000.0, 0.10, 0.05), _riga(1000.0 + 7 * giorni, 0.40, 0.17)]
    f = cartella / "recon.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in righe) + "\n")

    out = tb.calcola_rendita(MockEarnEx(riga_usdc=False), str(f), 7.0, 1000.0, "d")
    assert out["motivo"] is None
    assert out["earn_stimato_usdc"] == 0.0
    assert "nota_earn" in out and "assunto 0" in out["nota_earn"]
    # rendita = funding - fee, senza Earn
    assert out["eur_giorno"] == pytest.approx((0.30 - 0.12) / 7.0 * 0.92, abs=1e-4)


def test_calcola_rendita_earn_errore_rete_assume_zero(cartella):
    tb = _carica_tabellone()
    tb.prezzo_eur = lambda ccy: 0.92
    giorni = 86400.0
    righe = [_riga(1000.0, 0.10, 0.05), _riga(1000.0 + 7 * giorni, 0.40, 0.17)]
    f = cartella / "recon.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in righe) + "\n")

    out = tb.calcola_rendita(MockEarnEx(fallisce=True), str(f), 7.0, 1000.0, "d")
    assert out["motivo"] is None
    assert out["earn_stimato_usdc"] == 0.0
    assert "nota_earn" in out and "rate limit finto" in out["nota_earn"]


# ---------------------------------------------------------------------------
# earn_conto: campo 'amt' totale + fail-visible (review REQ-MD1-20261029-002)
# ---------------------------------------------------------------------------

class MockEarnExRiga:
    """Exchange finto con la riga USDC pilotabile campo per campo (forma reale)."""

    def __init__(self, riga: dict):
        self._riga = riga

    def privateGetFinanceSavingsBalance(self):
        return {"data": [dict(self._riga)]}


def test_earn_conto_saldo_da_amt_totale():
    tb = _carica_tabellone()
    # in finestra di (ri)prestito loanAmt puo' essere 0 mentre amt resta il totale
    riga = {"ccy": "USDC", "amt": "372.16481559", "rate": "0.01",
            "loanAmt": "0", "pendingAmt": "372.16481559",
            "earnings": "0.77", "redemptAmt": ""}
    out = tb.earn_conto(MockEarnExRiga(riga))
    assert out["errore"] is None
    assert out["saldo_usdc"] == pytest.approx(372.16481559)
    assert out["apy"] == pytest.approx(0.01)


def test_earn_conto_fallback_loan_piu_pending_senza_amt():
    tb = _carica_tabellone()
    riga = {"ccy": "USDC", "rate": "0.01", "loanAmt": "372.1637828",
            "pendingAmt": "0.00103279", "earnings": "0.77", "redemptAmt": ""}
    out = tb.earn_conto(MockEarnExRiga(riga))
    assert out["errore"] is None
    assert out["saldo_usdc"] == pytest.approx(372.16481559)


def test_earn_conto_saldo_zero_fail_visible():
    tb = _carica_tabellone()
    riga = {"ccy": "USDC", "amt": "0", "rate": "0.01", "loanAmt": "0",
            "pendingAmt": "0", "earnings": "0", "redemptAmt": ""}
    out = tb.earn_conto(MockEarnExRiga(riga))
    assert out["saldo_usdc"] == 0.0
    assert out["apy"] is None
    assert out["errore"] and "saldo" in out["errore"]


def test_earn_conto_rate_zero_fail_visible():
    tb = _carica_tabellone()
    riga = {"ccy": "USDC", "amt": "372.16481559", "rate": "0",
            "loanAmt": "372.16481559", "pendingAmt": "0",
            "earnings": "0", "redemptAmt": ""}
    out = tb.earn_conto(MockEarnExRiga(riga))
    assert out["saldo_usdc"] == pytest.approx(372.16481559)
    assert out["apy"] is None
    assert out["errore"] and "rate" in out["errore"]


def test_calcola_rendita_loanamt_zero_non_stima_zero_silenzioso(cartella):
    """Caso B della diagnosi: loanAmt=0 con amt>0 -> earn NON 0,00 silenzioso."""
    tb = _carica_tabellone()
    tb.prezzo_eur = lambda ccy: 0.92
    giorni = 86400.0
    righe = [_riga(1000.0, 0.10, 0.05), _riga(1000.0 + 7 * giorni, 0.40, 0.17)]
    f = cartella / "recon.jsonl"
    f.write_text("\n".join(json.dumps(r) for r in righe) + "\n")

    riga = {"ccy": "USDC", "amt": "372.16481559", "rate": "0.01",
            "loanAmt": "0", "pendingAmt": "372.16481559",
            "earnings": "0.77", "redemptAmt": ""}
    out = tb.calcola_rendita(MockEarnExRiga(riga), str(f), 7.0, 1066.30, "d")
    assert out["motivo"] is None
    earn = round(372.16481559 * 0.01 * 7.0 / 365.0, 6)
    assert out["earn_stimato_usdc"] == pytest.approx(earn)
    assert "nota_earn" not in out
