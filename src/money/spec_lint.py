"""Lint strutturale deterministico per spec/brief destinati ad agenti autonomi.

Verifica i blocchi minimi del formato-contratto adottato il 30/09 (cfr.
fabbrica/PIANO_HARDENING_2026-09-30.md): obiettivo, contesto repo/commit,
input/output, test falsificabile, criteri di accettazione, fuori-scope,
comando di verifica. Nessun modello, nessuna rete: solo regole testuali.
Advisory: chi chiama decide come usare gli esiti; il lint non blocca nulla.
"""
from __future__ import annotations

import re

SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b")
BASH_FENCE_RE = re.compile(r"```(?:bash|sh|shell|console)")


def lint_text(text: str) -> list[dict]:
    """Ritorna [{"check": str, "ok": bool, "hint": str}] per i 7 blocchi minimi."""
    t = text.lower()
    checks: list[dict] = []

    def add(name: str, ok: bool, hint: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "hint": hint})

    add("obiettivo", ("obiettivo" in t) or ("goal" in t),
        "sezione 'Obiettivo' verificabile")
    add("repo_commit",
        bool(re.search(r"\b(repo|repository|commit)\b", t)) and bool(SHA_RE.search(text)),
        "riferimento a repository + commit SHA")
    add("input_output", ("input" in t) and ("output" in t),
        "specifica di input e output")
    add("test_falsificabile",
        ("test" in t) and any(k in t for k in ("assert", "atteso", "expected", "fallire", "must fail")),
        "test che fallisce senza l'implementazione (assert/atteso)")
    add("criteri", ("criteri" in t and "accettazione" in t) or t.count("- [ ]") >= 2,
        "criteri di accettazione (checklist)")
    add("fuori_scope",
        any(k in t for k in ("fuori scope", "out of scope", "non modificare", "non toccare")),
        "confini espliciti (fuori scope)")
    add("verifica",
        bool(BASH_FENCE_RE.search(text)) or ("comando di verifica" in t) or ("procedura di verifica" in t),
        "comando/procedura di verifica riproducibile")
    return checks


def missing(checks: list[dict]) -> list[str]:
    """Nomi dei blocchi mancanti."""
    return [c["check"] for c in checks if not c["ok"]]
