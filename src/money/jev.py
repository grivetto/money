"""Client TypeSafe JEV per gate di processo (advisory, fail-open, log-only).

Regole di progetto:
- TYPESAFE_API_KEY si legge SOLO dall'ambiente; mai stampata, mai loggata.
- Si contatta esclusivamente https://api.typesafe.ai (nessun altro dominio).
- Fail-open: chiave assente o qualunque errore => None; nessuna decisione
  autonoma su percorsi ordini o capitale. Questi giudizi sono advisory.

Uso previsto: gate di qualita' delle spec PRIMA del dispatch agli aiutanti
(A0/DSH) e secondo parere sulle misure. CLI: scripts/jev_gate.py.
"""
from __future__ import annotations

import json
import logging
import os
import ssl
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

API_URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
TIMEOUT_S = 10.0
MAX_STATE_CHARS = 16000


def _ssl_context() -> ssl.SSLContext | None:
    """Bundle CA di certifi se disponibile, altrimenti default di sistema."""
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return None


def ask_questions(state: str, questions: dict[str, dict[str, Any]]) -> dict | None:
    """POST a JEV. Ritorna {"model","answers","usage"} oppure None (fail-open)."""
    key = os.environ.get("TYPESAFE_API_KEY", "")
    if not key:
        logger.info("JEV: TYPESAFE_API_KEY assente, fail-open")
        return None
    payload = {"model": MODEL, "state": state[:MAX_STATE_CHARS], "questions": questions}
    try:
        req = urllib.request.Request(
            API_URL, data=json.dumps(payload).encode("utf-8"), method="POST"
        )
        req.add_header("Authorization", "Bearer " + key)
        req.add_header("Content-Type", "application/json")
        ctx = _ssl_context()
        if ctx is not None:
            resp = urllib.request.urlopen(req, timeout=TIMEOUT_S, context=ctx)
        else:
            resp = urllib.request.urlopen(req, timeout=TIMEOUT_S)
        with resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not isinstance(data, dict) or "answers" not in data:
            return None
        return {
            "model": data.get("model"),
            "answers": data.get("answers", {}),
            "usage": data.get("usage", {}),
        }
    except Exception as e:  # noqa: BLE001 — fail-open per progetto
        logger.info("JEV non disponibile: %s: %s", type(e).__name__, e)
        return None


# --- Gate qualita' spec (decomposizione atomica; confidenze basse = casi boundary) ---

SPEC_GATE_QUESTIONS: dict[str, dict[str, Any]] = {
    "self_contained": {
        "type": "noul",
        "instructions": (
            "The state is a task specification for an autonomous coding agent with no access "
            "to this project's history. Does the spec contain everything needed to implement "
            "it correctly (goal, deliverable, inputs/outputs, interfaces, constraints)? "
            "Answer yes only if genuinely complete."
        ),
    },
    "test_falsifiable": {
        "type": "noul",
        "instructions": (
            "Does the spec include an acceptance test or criterion that would FAIL if the "
            "implementation were missing or wrong (a concrete, executable check, not a vague "
            "statement)? If no explicit acceptance test is present, answer no."
        ),
    },
    "gap": {
        "type": "choice",
        "instructions": "Which part of the spec is the MOST underspecified or missing?",
        "criteria": {
            "goal": "goal or scope unclear",
            "io": "inputs, outputs or interfaces unspecified",
            "constraints": "constraints, environment or dependencies unspecified",
            "test": "acceptance test missing, vague or not executable",
            "none": "nothing significant missing",
        },
    },
    "non_trading": {
        "type": "noul",
        "instructions": (
            "Is the described work strictly non-trading (research or tooling: no real orders, "
            "no fund movement, no direct exchange write access)?"
        ),
    },
}


def spec_gate(spec_md: str) -> dict | None:
    """Valuta una spec prima del dispatch a un aiutante. Advisory, fail-open => None."""
    out = ask_questions(spec_md, SPEC_GATE_QUESTIONS)
    if out is None:
        return None
    ans = out["answers"]

    def _noul(q: str) -> float | None:
        v = ans.get(q, {}).get("noul")
        return float(v) if isinstance(v, (int, float)) else None

    gap = ans.get("gap", {}) if isinstance(ans.get("gap"), dict) else {}
    return {
        "self_contained": _noul("self_contained"),
        "test_falsifiable": _noul("test_falsifiable"),
        "non_trading": _noul("non_trading"),
        "gap": gap.get("choice"),
        "gap_confidence": gap.get("confidence"),
        "model": out.get("model"),
        "usage": out.get("usage"),
        "raw": ans,
    }
