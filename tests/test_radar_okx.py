#!/usr/bin/env python3
"""Test radar OKX — estrazione dal feed, filtro chiavi, dedup dello stato.

Nessuna rete: si testano le funzioni pure su un campione sintetico.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "ops" / "radar"))

import radar_okx  # noqa: E402

CAMPIONE = {"code": "0", "data": [{"details": [
    {"annType": "campaigns", "title": "OKX Learn & Earn: quiz rewards for USDC",
     "url": "https://e/learn-1", "pTime": "1791452260555"},
    {"annType": "others", "title": "OKX to rename USD/USD spot trading pairs",
     "url": "https://e/rename-2", "pTime": 1791428420332},
]}]}


class TestEstraiEFiltro(unittest.TestCase):
    def test_estrai(self):
        items = radar_okx.estrai(CAMPIONE)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["titolo"][:10], "OKX Learn ")
        self.assertGreater(items[0]["ts"], 1_700_000_000)

    def test_filtra(self):
        f = radar_okx.filtra(radar_okx.estrai(CAMPIONE))
        self.assertEqual([i["url"] for i in f], ["https://e/learn-1"])


class TestStatoEDedup(unittest.TestCase):
    def test_nuovi_e_dedup(self):
        items = radar_okx.estrai(CAMPIONE)
        adesso = 1791452260.0
        self.assertEqual(len(radar_okx.nuovi_da_notificare(items, {}, adesso=adesso)), 2)
        visti = {"https://e/learn-1": adesso}
        nuovi = radar_okx.nuovi_da_notificare(items, visti, adesso=adesso)
        self.assertEqual([i["url"] for i in nuovi], ["https://e/rename-2"])

    def test_vecchie_escluse(self):
        items = radar_okx.estrai(CAMPIONE)
        adesso = 1791452260.0 + 90 * 86400
        self.assertEqual(radar_okx.nuovi_da_notificare(items, {}, adesso=adesso), [])

    def test_roundtrip_stato(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "seen.json"
            radar_okx.salva_visti(p, {"https://e/x": 1.5})
            self.assertEqual(radar_okx.carica_visti(p), {"https://e/x": 1.5})


if __name__ == "__main__":
    unittest.main()
