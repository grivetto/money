"""Test del gate JEV — nessuna rete: urlopen iniettato (fail-open verificato)."""
from __future__ import annotations

import json

import pytest

from money import jev


class _FakeResp:
    def __init__(self, payload: dict) -> None:
        self._b = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._b

    def __enter__(self) -> "_FakeResp":
        return self

    def __exit__(self, *a: object) -> bool:
        return False


def _canned_ok() -> dict:
    return {
        "model": "jev-x",
        "answers": {
            "self_contained": {"type": "noul", "noul": 0.9},
            "test_falsifiable": {"type": "noul", "noul": 0.85},
            "gap": {"type": "choice", "choice": "none", "confidence": 0.7},
            "non_trading": {"type": "noul", "noul": 1.0},
        },
        "usage": {"input_tokens": 10, "output_tokens": 2},
    }


def test_fail_open_senza_chiave(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert jev.ask_questions("x", {"q": {"type": "noul", "instructions": "y"}}) is None
    assert jev.spec_gate("spec di prova") is None


def test_parsing_risposta_completa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "dummy")
    monkeypatch.setattr(jev.urllib.request, "urlopen", lambda *a, **k: _FakeResp(_canned_ok()))
    out = jev.spec_gate("spec di prova")
    assert out is not None
    assert out["self_contained"] == 0.9
    assert out["test_falsifiable"] == 0.85
    assert out["non_trading"] == 1.0
    assert out["gap"] == "none"
    assert out["model"] == "jev-x"


def test_errore_di_rete_fail_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "dummy")

    def boom(*a: object, **k: object) -> None:
        raise OSError("rete giu'")

    monkeypatch.setattr(jev.urllib.request, "urlopen", boom)
    assert jev.spec_gate("x") is None


def test_risposta_parziale_non_crasha(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "dummy")
    monkeypatch.setattr(
        jev.urllib.request,
        "urlopen",
        lambda *a, **k: _FakeResp({"model": "m", "answers": {}, "usage": {}}),
    )
    out = jev.spec_gate("x")
    assert out is not None
    assert out["self_contained"] is None
    assert out["gap"] is None


def test_troncamento_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TYPESAFE_API_KEY", "dummy")
    captured: dict = {}

    def fake_urlopen(req: object, *a: object, **k: object) -> _FakeResp:
        captured["payload"] = json.loads(req.data.decode())  # type: ignore[attr-defined]
        return _FakeResp({"model": "m", "answers": {"q": {}}, "usage": {}})

    monkeypatch.setattr(jev.urllib.request, "urlopen", fake_urlopen)
    long_state = "x" * (jev.MAX_STATE_CHARS + 500)
    jev.ask_questions(long_state, {"q": {"type": "noul", "instructions": "y"}})
    assert len(captured["payload"]["state"]) == jev.MAX_STATE_CHARS


def test_dominio_solo_typesafe() -> None:
    assert jev.API_URL.startswith("https://api.typesafe.ai/")
