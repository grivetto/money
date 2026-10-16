#!/usr/bin/env python3
"""Test veglia flotta — profili, host-match, freschezza file, run con heal iniettato.

Nessuna rete, nessun systemd: l'esecutore dei comandi e' iniettato.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "ops" / "fleet"))

import veglia  # noqa: E402

PROFILO_FINTO = {"unita": ["u1", "u2"], "unita_utente": [], "http": [], "docker": [], "file": []}


class FakeEsegui:
    def __init__(self, risposte=None):
        self.risposte = risposte or {}
        self.chiamate: list[str] = []

    def __call__(self, cmd, timeout=40):
        self.chiamate.append(cmd)
        return self.risposte.get(cmd, (0, "active", ""))


class TestProfili(unittest.TestCase):
    def test_profili_ben_formati(self):
        self.assertGreaterEqual(len(veglia.PROFILI), 3)
        for nome, prof in veglia.PROFILI.items():
            self.assertTrue(prof["unita"], nome)
            for tup in prof["http"]:
                self.assertEqual(len(tup), 3, nome)
                self.assertTrue(str(tup[0]).startswith("http"), nome)
            for f in prof["file"]:
                self.assertEqual(len(f), 2, nome)

    def test_host_match(self):
        self.assertEqual(veglia.profilo_per_host("mc2")[0], "mc2")
        self.assertEqual(veglia.profilo_per_host("MARCODG1.tail1b5252.ts.net")[0], "marcodg1")
        self.assertEqual(veglia.profilo_per_host("nuvola")[0], "nuvola")
        self.assertIsNone(veglia.profilo_per_host("macchina-ignota")[0])


class TestFreschezza(unittest.TestCase):
    def test_file_fresco_e_fermo(self):
        with tempfile.NamedTemporaryFile() as f:
            t = os.path.getmtime(f.name)
            self.assertTrue(veglia.controlla_file(f.name, 60, adesso=t + 5).ok)
            self.assertFalse(veglia.controlla_file(f.name, 60, adesso=t + 3600).ok)


class TestRun(unittest.TestCase):
    def _sandbox(self, tmp):
        self._orig = (veglia.LAST, veglia.LOG, veglia.DIR)
        veglia.DIR = Path(tmp)
        veglia.LAST = Path(tmp) / "last.json"
        veglia.LOG = Path(tmp) / "veglia.log"

    def _restore(self):
        veglia.LAST, veglia.LOG, veglia.DIR = self._orig

    def test_check_tutto_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._sandbox(tmp)
            try:
                f = FakeEsegui()
                code, esiti, _ = veglia.run_veglia(PROFILO_FINTO, "test", Path(tmp) / "st.json",
                                                   esegui=f, heal=False, alert=False)
                self.assertEqual(code, 0)
                self.assertTrue(all(e.ok for e in esiti))
            finally:
                self._restore()

    def test_heal_ripara(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._sandbox(tmp)
            try:
                class F:
                    def __init__(self):
                        self.healed = False
                        self.chiamate: list[str] = []

                    def __call__(self, cmd, timeout=40):
                        self.chiamate.append(cmd)
                        if cmd == "systemctl is-active u1":
                            return (0, "active" if self.healed else "inactive", "")
                        if cmd.startswith("sudo -n systemctl restart u1"):
                            self.healed = True
                            return (0, "", "")
                        return (0, "active", "")

                f = F()
                code, esiti, _ = veglia.run_veglia(PROFILO_FINTO, "test", Path(tmp) / "st.json",
                                                   esegui=f, heal=True, alert=False)
                self.assertEqual(code, 0)
                self.assertTrue(esiti[0].riparato)
                self.assertIn("sudo -n systemctl restart u1", f.chiamate)
            finally:
                self._restore()

    def test_ko_senza_heal(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._sandbox(tmp)
            try:
                f = FakeEsegui({"systemctl is-active u2": (3, "failed", "")})
                code, esiti, _ = veglia.run_veglia(PROFILO_FINTO, "test", Path(tmp) / "st.json",
                                                   esegui=f, heal=False, alert=False)
                self.assertEqual(code, 1)
                self.assertFalse(esiti[1].ok)
            finally:
                self._restore()


if __name__ == "__main__":
    unittest.main()
