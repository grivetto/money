"""Test della finestra di silenzio notturna (ops/alerts/notifica_tg.py)."""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "ops" / "alerts"))

import notifica_tg as nt  # noqa: E402


def test_finestra_confini():
    def s(hh, mm):
        return nt.in_silenzio(datetime.datetime(2026, 10, 30, hh, mm))

    assert not s(22, 29)
    assert s(22, 30)
    assert s(23, 59)
    assert s(0, 0)
    assert s(3, 15)
    assert s(7, 29)
    assert not s(7, 30)
    assert not s(12, 0)


def test_finestra_disattivabile_con_env(monkeypatch):
    monkeypatch.setenv("DENARO_TG_SILENZIO", "off")
    assert not nt.in_silenzio(datetime.datetime(2026, 10, 30, 3, 0))


def test_invia_soppresso_in_finestra(monkeypatch, tmp_path):
    monkeypatch.setattr(nt, "in_silenzio", lambda adesso=None: True)
    monkeypatch.setattr(nt, "_config", lambda: ("tok", "chat"))
    monkeypatch.setattr(nt, "LOG_SILENZIO", tmp_path / "tg_notte.log")
    chiamate = []
    monkeypatch.setattr(nt, "_call", lambda *a, **k: chiamate.append(a) or {})

    assert nt.invia("ciao") is False
    assert nt.invia_con_esito("ciao") == "suppressed"
    assert chiamate == []
    assert "ciao" in (tmp_path / "tg_notte.log").read_text(encoding="utf-8")


def test_invia_fuori_finestra(monkeypatch):
    monkeypatch.setattr(nt, "in_silenzio", lambda adesso=None: False)
    monkeypatch.setattr(nt, "_config", lambda: ("tok", "chat"))
    chiamate = []
    monkeypatch.setattr(nt, "_call", lambda tok, metodo, **p: chiamate.append((metodo, p)) or {})

    assert nt.invia("ciao") is True
    assert chiamate and chiamate[0][0] == "sendMessage"


def test_invia_fallito_su_errore(monkeypatch):
    monkeypatch.setattr(nt, "in_silenzio", lambda adesso=None: False)
    monkeypatch.setattr(nt, "_config", lambda: ("tok", "chat"))

    def boom(*a, **k):
        raise OSError("rete")

    monkeypatch.setattr(nt, "_call", boom)
    assert nt.invia_con_esito("ciao") == "failed"
    assert nt.invia("ciao") is False


def test_cli_sopprime_e_ritorna_5(monkeypatch, tmp_path):
    monkeypatch.setattr(nt, "_config", lambda: ("tok", "chat"))
    monkeypatch.setattr(nt, "in_silenzio", lambda adesso=None: True)
    monkeypatch.setattr(nt, "LOG_SILENZIO", tmp_path / "tg_notte.log")
    chiamate = []
    monkeypatch.setattr(nt, "_call", lambda *a, **k: chiamate.append(a) or {})

    assert nt.main(["ciao"]) == 5
    assert chiamate == []


def test_cli_urgente_forza_invio(monkeypatch):
    monkeypatch.setattr(nt, "_config", lambda: ("tok", "chat"))
    monkeypatch.setattr(nt, "in_silenzio", lambda adesso=None: True)
    chiamate = []
    monkeypatch.setattr(nt, "_call", lambda tok, metodo, **p: chiamate.append(metodo) or {})

    assert nt.main(["--urgente", "ciao"]) == 0
    assert chiamate == ["sendMessage"]
