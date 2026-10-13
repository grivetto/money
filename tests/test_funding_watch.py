"""Test offline di scripts/funding_watch.py (nessuna rete: `get` viene sostituito)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("funding_watch", ROOT / "scripts" / "funding_watch.py")
fw = importlib.util.module_from_spec(spec)
sys.modules["funding_watch"] = fw
spec.loader.exec_module(fw)


def test_lordo_annuo_default_okx():
    """0,01%/8h (default OKX) -> ~10,95%/anno lordo."""
    assert fw.lordo_annuo_pct(0.0001) == pytest.approx(10.95, abs=0.01)


def test_lordo_annuo_zero_e_negativo():
    assert fw.lordo_annuo_pct(0.0) == 0.0
    assert fw.lordo_annuo_pct(-0.0001) < 0


def test_netto_spalma_i_costi_sui_giorni():
    """Tenuta piu' lunga => i costi di ingresso/uscita pesano meno."""
    n30 = fw.netto_annuo_pct(0.0001, 30)
    n180 = fw.netto_annuo_pct(0.0001, 180)
    assert n30 < n180 < fw.lordo_annuo_pct(0.0001)
    assert n30 == pytest.approx(10.95 - 0.3 * 365 / 30, abs=0.05)   # 0,30% round-trip -> 3,65%/anno a 30g


def test_netto_giorni_non_validi():
    with pytest.raises(ValueError):
        fw.netto_annuo_pct(0.0001, 0)


def test_rendimento_su_capitale_leva():
    """Leva 1x: capitale = notional (spot) + margine (perp) => meta' del netto."""
    assert fw.rendimento_su_capitale(10.0, 1.0) == pytest.approx(5.0)
    assert fw.rendimento_su_capitale(10.0, 2.0) == pytest.approx(10.0 / 1.5)


def test_alert_senza_token_non_invia(monkeypatch):
    """Senza credenziali Telegram non parte nessuna chiamata."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    out = {"sopra_soglia": [{"instId": "X-USD_UM_XPERP-310404", "lordo_annuo_pct": 20.0,
                             "netto_annuo_pct": 19.0, "rend_capitale_leva1_pct": 9.5}],
           "ts": "t", "soglia_pct": 12.0, "giorni_tenuta": 30.0}
    assert fw.invia_alert(out) is False


def test_alert_invia_e_dedup(monkeypatch, tmp_path):
    """Con credenziali invia una volta, poi tace entro il cooldown (stessa firma)."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "finto")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setattr(fw, "STATO_ALERT", tmp_path / "stato_alert.json")
    inviati = []

    class _R:
        def read(self):
            return b"{}"

    def fake_urlopen(req, timeout=None):
        inviati.append(req)
        return _R()

    monkeypatch.setattr(fw.urllib.request, "urlopen", fake_urlopen)
    out = {"sopra_soglia": [{"instId": "X-USD_UM_XPERP-310404", "lordo_annuo_pct": 20.0,
                             "netto_annuo_pct": 19.0, "rend_capitale_leva1_pct": 9.5}],
           "ts": "t", "soglia_pct": 12.0, "giorni_tenuta": 30.0}
    assert fw.invia_alert(out) is True
    assert len(inviati) == 1
    assert fw.invia_alert(out) is False        # dedup: stessa firma entro il cooldown
    assert len(inviati) == 1


def test_scansione_classifica(monkeypatch):
    """SOPRA_SOGLIA / SOTTO_SOGLIA / ILLIQUIDO con dati finti."""
    istru = [{"instId": "AAA-USD_UM_XPERP-310404", "state": "live"},
             {"instId": "BBB-USD_UM_XPERP-310404", "state": "live"},
             {"instId": "CCC-USD_UM_XPERP-310404", "state": "live"},
             {"instId": "DDD-USD_UM_XPERP-310404", "state": "dead"}]
    ticks = [
        {"instId": "AAA-USD_UM_XPERP-310404", "volCcy24h": "500000", "bidPx": "10.00", "askPx": "10.01"},
        {"instId": "BBB-USD_UM_XPERP-310404", "volCcy24h": "500000", "bidPx": "10.00", "askPx": "10.01"},
        {"instId": "CCC-USD_UM_XPERP-310404", "volCcy24h": "10", "bidPx": "10.00", "askPx": "10.01"},
    ]
    rates = {"AAA-USD_UM_XPERP-310404": "0.0005",   # 54,75%/anno -> sopra
             "BBB-USD_UM_XPERP-310404": "0.0001",   # 10,95%/anno -> sotto
             "CCC-USD_UM_XPERP-310404": "0.0005"}   # sopra come rate ma illiquido

    def fake_get(path, params=None):
        if path.endswith("/instruments"):
            return istru
        if path.endswith("/tickers"):
            return ticks
        if path.endswith("/funding-rate"):
            return [{"instId": params["instId"], "fundingRate": rates[params["instId"]]}]
        return []

    monkeypatch.setattr(fw, "get", fake_get)
    monkeypatch.setattr(fw, "time", type("T", (), {"sleep": staticmethod(lambda _s: None)}))
    out = fw.scansione(soglia_pct=12.0, giorni_tenuta=30.0, max_strumenti=10)

    verdi = {r["instId"]: r["verdetto"] for r in out["strumenti"]}
    assert verdi["AAA-USD_UM_XPERP-310404"] == "SOPRA_SOGLIA"
    assert verdi["BBB-USD_UM_XPERP-310404"] == "SOTTO_SOGLIA"
    assert verdi["CCC-USD_UM_XPERP-310404"] == "ILLIQUIDO"
    assert "DDD" not in str(verdi)          # strumento non live escluso
    assert out["n_esaminati"] == 3
    assert len(out["sopra_soglia"]) == 1
    assert out["strumenti"][0]["instId"] == "AAA-USD_UM_XPERP-310404"   # ordinati per lordo
