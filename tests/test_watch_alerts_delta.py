#!/usr/bin/env python3
"""Test Δ (cambio vs resto), soglia-campanello e digest composto — 16/10/26.

Il capitale resta in dollari (decisione owner): il numero in € oscilla col cambio.
Contratto di questi test:
- `_attribuzione` scompone Δequity = effetto cambio + resto su serie sintetiche;
- `check_equity` allarma sotto SOGLIA_EUR col motivo, non spamma, manda il rientro;
- il digest compone le righe Δ senza rete (ssh e banco iniettati).

Nessuna rete: `_fetch_infra`, `_ssh`, `_banco_rows` e l'invio Telegram sono iniettati.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from conftest import cartella_temporanea  # noqa: E402

_ALERTS = Path(__file__).resolve().parents[1] / "ops" / "alerts"
if str(_ALERTS) not in sys.path:
    sys.path.insert(0, str(_ALERTS))

import alert_lib  # noqa: E402
import watch_alerts  # noqa: E402

_BASE = {"total_equity": 1100.0,
         "balances": {"OKX main": {"ok": True, "savings_ok": True}},
         "equity_breakdown": {"OKX main": {"ok": True, "eur": 1100.0}}}


def _riga_banco(ts: str, eq: float, rate: float, usdc: float = 1000.0) -> dict:
    """Campione sintetico del banco: tutto l'USDC in Simple Earn, niente cripto."""
    return {
        "timestamp": ts,
        "equity_eur": eq,
        "equity_trading_eur": 0.0,
        "equity_funding_eur": 0.0,
        "equity_savings_eur": usdc * rate,
        "saldi_trading": {"USDC": 0.0, "EUR": 0.0},
        "saldi_funding": {"USDC": 0.0},
        "saldi_savings": {"USDC": usdc},
    }


_BANCO_2GG = [
    _riga_banco("2026-10-15T12:00:10Z", 900.0, 0.900),
    _riga_banco("2026-10-16T12:00:10Z", 891.0, 0.891),  # solo cambio: -9.00
]


class TestAttribuzione(unittest.TestCase):
    def test_solo_cambio(self) -> None:
        delta, cambio, resto = watch_alerts._attribuzione(_BANCO_2GG, 86400)
        self.assertAlmostEqual(delta, -9.0, places=6)
        self.assertAlmostEqual(cambio, -9.0, places=6)
        self.assertAlmostEqual(resto, 0.0, places=6)

    def test_cambio_piu_fee(self) -> None:
        rows = [dict(_BANCO_2GG[0]), _riga_banco("2026-10-16T12:00:10Z", 890.5, 0.891)]
        delta, cambio, resto = watch_alerts._attribuzione(rows, 86400)
        self.assertAlmostEqual(delta, -9.5, places=6)
        self.assertAlmostEqual(cambio, -9.0, places=6)
        self.assertAlmostEqual(resto, -0.5, places=6)

    def test_serie_insufficiente(self) -> None:
        self.assertIsNone(watch_alerts._attribuzione([], 86400))
        self.assertIsNone(watch_alerts._attribuzione(_BANCO_2GG[:1], 86400))


class TestParseBanco(unittest.TestCase):
    def test_filtra_righe_non_valide(self) -> None:
        testo = "\n".join([
            '{"timestamp": "2026-10-16T12:00:00Z", "equity_eur": 1097.0}',
            "non-json",
            '{"timestamp": "2026-10-16T12:05:00Z"}',
            "",
            '{"timestamp": "2026-10-16T12:10:00Z", "equity_eur": 1096.5}',
        ])
        out = watch_alerts._parse_banco(testo)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[-1]["equity_eur"], 1096.5)


class TestSogliaEquity(unittest.TestCase):
    """check_equity sotto SOGLIA_EUR: allarme col motivo, anti-spam, rientro."""

    def setUp(self) -> None:
        self.dir = cartella_temporanea("soglia")
        self.inviati: list[str] = []
        self._orig = (alert_lib.DIR, alert_lib.STATE, alert_lib.SPOOL,
                      alert_lib.invia_o_spool, watch_alerts.EQUITY_STATO,
                      watch_alerts._fetch_infra, watch_alerts._banco_rows)
        alert_lib.DIR = self.dir
        alert_lib.STATE = self.dir / "state.json"
        alert_lib.SPOOL = self.dir / "spool.jsonl"
        alert_lib.invia_o_spool = self._finto_invio
        watch_alerts.EQUITY_STATO = self.dir / "equity_24h.json"
        self.payload = dict(_BASE)
        watch_alerts._fetch_infra = lambda: self.payload
        watch_alerts._banco_rows = lambda n=600: list(_BANCO_2GG)

    def _finto_invio(self, testo: str) -> bool:
        self.inviati.append(testo)
        return True

    def tearDown(self) -> None:
        (alert_lib.DIR, alert_lib.STATE, alert_lib.SPOOL, alert_lib.invia_o_spool,
         watch_alerts.EQUITY_STATO, watch_alerts._fetch_infra,
         watch_alerts._banco_rows) = self._orig

    def _run(self) -> int:
        n0 = len(self.inviati)
        watch_alerts.check_equity()
        return len(self.inviati) - n0

    def test_sotto_soglia_allarma_col_motivo(self) -> None:
        self.assertEqual(self._run(), 0)                    # baseline 1100: silenzio
        self.payload = {**_BASE, "total_equity": 1085.0}
        self.assertEqual(self._run(), 1)
        msg = self.inviati[-1]
        self.assertIn("sotto", msg)
        self.assertIn("1085", msg)
        self.assertIn("24h", msg)                           # motivo incluso
        self.assertIn("cambio", msg)

    def test_soglia_non_spamma(self) -> None:
        self._run()
        self.payload = {**_BASE, "total_equity": 1085.0}
        self.assertEqual(self._run(), 1)
        self.assertEqual(self._run(), 0)                    # persistente: nessun bis

    def test_rientro_sopra_soglia(self) -> None:
        self._run()
        self.payload = {**_BASE, "total_equity": 1085.0}
        self.assertEqual(self._run(), 1)
        self.payload = dict(_BASE)
        self.assertEqual(self._run(), 1)
        self.assertIn("sopra la soglia", self.inviati[-1])

    def test_crollo_non_duplica_la_soglia(self) -> None:
        self._run()
        self.payload = {**_BASE, "total_equity": 120.0}
        n = self._run()
        self.assertEqual(n, 1)                              # solo il messaggio crollo
        self.assertIn("crollo", self.inviati[-1])


class TestDigestComposto(unittest.TestCase):
    """Il digest compone capitale + Δ24h/Δ7g + canary senza rete."""

    def setUp(self) -> None:
        class _R:
            def __init__(self, rc: int = 0, out: str = "") -> None:
                self.returncode = rc
                self.stdout = out
        self._R = _R
        self._orig = (watch_alerts._ssh, watch_alerts._banco_rows)
        payload = {"equity_breakdown": {"OKX main": {"eur": 1097.2}},
                   "bots": {"a": {"status": "running"}, "b": {"status": "running"}}}

        def fake_ssh(cmd: str, timeout: int = 40):  # noqa: ANN001
            if "8912" in cmd:
                return _R(0, json.dumps(payload))
            if "canary_carry" in cmd:
                return _R(0, "C1 DOGE: net +0.05 USDC")
            return _R(0, "")

        watch_alerts._ssh = fake_ssh
        watch_alerts._banco_rows = lambda n=2500: list(_BANCO_2GG)

    def tearDown(self) -> None:
        (watch_alerts._ssh, watch_alerts._banco_rows) = self._orig

    def test_righe_delta_presenti(self) -> None:
        testo = watch_alerts._componi_digest()
        self.assertIn("Capitale OKX main: 1097.20", testo)
        self.assertIn("Flotta: 2 running", testo)
        self.assertIn("Δ24h:", testo)
        self.assertIn("cambio", testo)
        self.assertIn("Canary:", testo)


if __name__ == "__main__":
    unittest.main()
