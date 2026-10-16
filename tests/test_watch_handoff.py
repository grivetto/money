"""Test del watcher consegne handoff (parti pure: scansione + dedup).

Il modulo e' uno script CLI in ops/alerts/; qui si testano le funzioni pure
senza toccare il bridge reale (tmp_path) e senza rete/Telegram.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "ops" / "alerts" / "watch_handoff.py"


def _carica():
    spec = importlib.util.spec_from_file_location("watch_handoff", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_scansiona_trova_solo_ready(tmp_path):
    w = _carica()
    root = tmp_path / "bridge"
    (root / "dsh-mc2" / "handoff" / "P21").mkdir(parents=True)
    (root / "dsh-mc2" / "handoff" / "P21" / "READY").write_text("")
    # cartella senza READY: non deve contare
    (root / "dsh" / "handoff" / "VECCHIO").mkdir(parents=True)

    trovati = w.scansiona(root)
    assert trovati == ["dsh-mc2/handoff/P21/READY"]


def test_dedup_primo_avvistamento_e_ripetizione(tmp_path):
    w = _carica()
    trovati = ["dsh-mc2/handoff/P21/READY"]
    assert w.nuovi([], trovati) == trovati  # primo avvistamento: notifica
    assert w.nuovi(trovati, trovati) == []  # gia' visto: nessun doppione


def test_root_inesistente_non_esplode(tmp_path):
    w = _carica()
    assert w.scansiona(tmp_path / "vuoto") == []
    assert w.nuovi([], w.scansiona(tmp_path / "vuoto")) == []
