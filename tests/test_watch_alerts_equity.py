#!/usr/bin/env python3
"""Test della guardia equity del watchdog — lezione 11/10/26.

Il capitale OKX vive su TRE comparti (trading, funding, Simple Earn): letti solo
trading+funding, l'equity apparve crollata (~1.100 -> ~120 EUR) senza che NULLA
allarmasse. Questi test fissano `watch_alerts.check_equity()`: crollo >30% vs
massimo 24h, letture per-conto incomplete, valori assenti — ogni condizione deve
allarmare, rispettare l'anti-spam e rientrare.

Nessuna rete: `_fetch_infra` e l'invio Telegram sono iniettati su una cartella
isolata (convenzione `cartella_temporanea` del repo).
"""
from __future__ import annotations

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


class TestCheckEquity(unittest.TestCase):
    """Contratto della guardia: allarme su crollo/lettura incompleta, rientro, niente spam."""

    def setUp(self) -> None:
        self.dir = cartella_temporanea("eq")
        self.inviati: list[str] = []
        self._orig = (alert_lib.DIR, alert_lib.STATE, alert_lib.SPOOL,
                      alert_lib.invia_o_spool, watch_alerts.EQUITY_STATO,
                      watch_alerts._fetch_infra)
        alert_lib.DIR = self.dir
        alert_lib.STATE = self.dir / "state.json"
        alert_lib.SPOOL = self.dir / "spool.jsonl"
        alert_lib.invia_o_spool = self._finto_invio
        watch_alerts.EQUITY_STATO = self.dir / "equity_24h.json"
        self.payload = dict(_BASE)
        watch_alerts._fetch_infra = lambda: self.payload

    def _finto_invio(self, testo: str) -> bool:
        self.inviati.append(testo)
        return True

    def tearDown(self) -> None:
        (alert_lib.DIR, alert_lib.STATE, alert_lib.SPOOL, alert_lib.invia_o_spool,
         watch_alerts.EQUITY_STATO, watch_alerts._fetch_infra) = self._orig

    def _run(self) -> int:
        n0 = len(self.inviati)
        watch_alerts.check_equity()
        return len(self.inviati) - n0

    # -- crollo --------------------------------------------------------------
    def test_stabile_non_invia(self) -> None:
        self.assertEqual(self._run(), 0)

    def test_crollo_allarma_e_il_rientro_chiude(self) -> None:
        self.assertEqual(self._run(), 0)                 # stabilizza il massimo a 1100
        self.payload = {**_BASE, "total_equity": 120.0}  # il «120 vs 1.100»
        self.assertEqual(self._run(), 1)
        self.assertIn("crollo", self.inviati[-1])
        self.assertIn("1100", self.inviati[-1])          # riferisce il massimo 24h
        self.payload = dict(_BASE)
        self.assertEqual(self._run(), 1)
        self.assertIn("rientrata", self.inviati[-1])

    def test_crollo_persistente_non_spamma(self) -> None:
        self._run()
        self.payload = {**_BASE, "total_equity": 120.0}
        self.assertEqual(self._run(), 1)
        self.assertEqual(self._run(), 0)                 # stesso problema: nessun bis

    # -- letture incomplete ----------------------------------------------------
    def test_savings_non_letto_allarma(self) -> None:
        self.payload = {**_BASE,
                        "balances": {"OKX main": {"ok": True, "savings_ok": False}}}
        self.assertEqual(self._run(), 1)
        self.assertIn("Simple Earn", self.inviati[-1])
        self.payload = dict(_BASE)
        self.assertEqual(self._run(), 1)
        self.assertIn("di nuovo complete", self.inviati[-1])

    def test_conto_non_letto_allarma(self) -> None:
        self.payload = {**_BASE,
                        "equity_breakdown": {"OKX mc2sub1": {"ok": False, "eur": 0.0}}}
        self.assertEqual(self._run(), 1)
        self.assertIn("mc2sub1", self.inviati[-1])

    # -- valori assenti ---------------------------------------------------------
    def test_total_mancante_allarma(self) -> None:
        self.payload = {"balances": {}}
        self.assertEqual(self._run(), 1)
        self.assertIn("total_equity", self.inviati[-1])
        self.payload = dict(_BASE)
        self.assertEqual(self._run(), 1)
        self.assertIn("di nuovo presente", self.inviati[-1])


if __name__ == "__main__":
    unittest.main()
