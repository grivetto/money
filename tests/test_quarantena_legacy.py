#!/usr/bin/env python3
"""Test della quarantena di `legacy/`.

Il progetto precedente non e' una base su cui costruire: e' memoria di cosa e' stato provato.
Questi test impediscono che diventi, di nuovo, una dipendenza.
"""
from __future__ import annotations

import re
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]

#: Questo file contiene il pattern che cerca ("import legacy"): per vietare dei nomi bisogna
#: scriverli. E' l'unica esclusione non storica, ed e' dichiarata invece che implicita.
SE_STESSA = "test_quarantena_legacy.py"

CARTELLE = ("src", "scripts", "tests")

#: I bot che hanno bruciato capitale, o che non potevano accorgersi di perderlo. Devono essere
#: nominati nella quarantena: se un documento non dice *cosa* mette al bando, non e' un bando.
CRITICI = (
    "denaro_core.py", "momentum_scalper.py", "momentum_scalper_sol.py", "scalper_v2.py",
    "denaro_strategies.py", "correlation_guard.py", "risk_manager.py", "kill_switch.py",
    "orchestrator.py", "grid_bot_v3.py", "hermes_cron_report.py",
)


def file_da_controllare():
    fuori = []
    for cartella in CARTELLE:
        for p in (RADICE / cartella).rglob("*.py"):
            if p.name == SE_STESSA:
                continue
            fuori.append(p)
    return fuori


def test_nessun_modulo_del_progetto_importa_da_legacy():
    """Il codice in quarantena non deve rientrare per una modifica distratta."""
    schema = re.compile(r"^\s*(?:from|import)\s+legacy\b", re.MULTILINE)
    trovate = []
    for p in file_da_controllare():
        testo = p.read_text(encoding="utf-8", errors="replace")
        if schema.search(testo):
            trovate.append(str(p.relative_to(RADICE)))
    assert not trovate, "moduli che importano da legacy/:\n  " + "\n  ".join(trovate)


def test_il_controllo_guarda_qualcosa():
    """Un test che non controlla nessun file passerebbe sempre."""
    controllati = file_da_controllare()
    assert len(controllati) >= 20
    nomi = {p.name for p in controllati}
    assert "rischio.py" in nomi and "contabilita.py" in nomi


def test_la_quarantena_esiste_e_dichiara_le_regole():
    testo = (RADICE / "legacy" / "QUARANTENA.md").read_text(encoding="utf-8")
    assert "NON ESEGUIBILE" in testo
    assert "Vietato eseguire" in testo
    assert "Vietato importare" in testo
    assert "Vietato riparare per riuso" in testo


def test_i_bot_pericolosi_sono_nominati_nella_quarantena():
    testo = (RADICE / "legacy" / "QUARANTENA.md").read_text(encoding="utf-8")
    mancanti = [n for n in CRITICI if n not in testo]
    assert not mancanti, f"bot pericolosi non nominati in QUARANTENA.md: {mancanti}"


def test_la_quarantena_mappa_i_sostituti():
    """Una quarantena senza alternative e' solo un divieto: deve dire cosa prende il posto."""
    testo = (RADICE / "legacy" / "QUARANTENA.md").read_text(encoding="utf-8")
    for modulo in ("money/contabilita.py", "money/rischio.py", "money/statistica.py",
                   "money/costi.py", "money/cancello.py"):
        assert modulo in testo, f"{modulo} non e' indicato come sostituto"
