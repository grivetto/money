#!/usr/bin/env python3
"""Test del postino di squadra (ops/squadra/postino.py). Rete e ssh sempre mockati."""
from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "postino", Path(__file__).resolve().parents[1] / "ops" / "squadra" / "postino.py")
postino = importlib.util.module_from_spec(SPEC)
sys.modules["postino"] = postino
SPEC.loader.exec_module(postino)  # type: ignore[union-attr]


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """Bridge finto con un canale 'merlino'; ssh/lancio/TG registrati."""
    bridge = tmp_path / "hermes_bridge"
    (bridge / "merlino").mkdir(parents=True)
    monkeypatch.setattr(postino, "BRIDGE", bridge)
    monkeypatch.setattr(postino, "ARTU_INBOX", bridge / "artu" / "inbox.md")
    monkeypatch.setattr(postino, "STATO", tmp_path / "state.json")
    monkeypatch.setattr(postino, "DIR_LOG", tmp_path / "log")
    monkeypatch.setattr(postino, "NODI", {
        "merlino": {"nodo": "omarchy", "nome": "MERLINO", "wake": "/w/wake.txt"}})
    chiamate = {"wake": [], "tg": [], "reach": True, "lock": True}
    monkeypatch.setattr(postino, "lancia_wake", lambda c, dry: chiamate["wake"].append(c) or True)
    monkeypatch.setattr(postino, "_notifica_tg", lambda t, dry: chiamate["tg"].append(t) or True)
    monkeypatch.setattr(postino, "nodo_raggiungibile", lambda n: chiamate["reach"])
    monkeypatch.setattr(postino, "lock_libero", lambda n: chiamate["lock"])
    return bridge, chiamate


def _scrivi_requests(env, testi: list[str]):
    bridge, _ = env
    p = bridge / "merlino" / "requests.md"
    with p.open("w", encoding="utf-8") as f:
        for t in testi:
            f.write(t + "\n")


def _stato():
    return {"blocchi": {}, "lanci": {}}


def test_grace_e_wake(env):
    bridge, ch = env
    _scrivi_requests(env, ["## REQ-MERL-X | 2026-10-29 17:00 UTC | PENDING", "Fai la cosa.", ""])
    t0 = time.time()
    st = _stato()
    postino.processa_requests("merlino", st, t0, dry=False, seed=False)
    assert ch["wake"] == []  # primo giro: solo 'pending'
    postino.processa_requests("merlino", st, t0 + 60, dry=False, seed=False)
    assert ch["wake"] == []  # entro la grace: attesa
    out = postino.processa_requests("merlino", st, t0 + postino.GRACE_S + 5, dry=False, seed=False)
    assert ch["wake"] == ["merlino"]  # oltre la grace, lock libero: WAKE
    assert any("WAKE" in x for x in out)
    st2 = {k: v["status"] for k, v in st["blocchi"].items()}
    assert list(st2.values()) == ["dispatched"]
    # terzo giro: niente doppioni
    postino.processa_requests("merlino", st, t0 + postino.GRACE_S + 120, dry=False, seed=False)
    assert ch["wake"] == ["merlino"]


def test_lock_occupato_con_turno_coperto_noop(env):
    bridge, ch = env
    _scrivi_requests(env, ["## REQ-MERL-Y | 2026-10-29 17:00 UTC | PENDING", ""])
    t0 = time.time()
    st = _stato()
    postino.processa_requests("merlino", st, t0, dry=False, seed=False)
    ch["lock"] = False  # un turno e' in corso...
    # ...e il log di lancio prova che e' partito DOPO la vista del blocco (coperto)
    postino.DIR_LOG.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t0 + 5))
    (postino.DIR_LOG / "log_omarchy_x.txt").write_text(
        "START %s nodo=omarchy prompt=/x\n" % ts, encoding="utf-8")
    postino.processa_requests("merlino", st, t0 + postino.GRACE_S + 5, dry=False, seed=False)
    assert ch["wake"] == []
    assert list(v["status"] for v in st["blocchi"].values()) == ["noop"]


def test_busy_non_coperto_riprova(env):
    bridge, ch = env
    _scrivi_requests(env, ["## REQ-MERL-B | PENDING", ""])
    t0 = time.time()
    st = _stato()
    postino.processa_requests("merlino", st, t0, dry=False, seed=False)
    ch["lock"] = False  # occupato su un ALTRO lavoro: la coda non va persa
    postino.processa_requests("merlino", st, t0 + postino.GRACE_S + 5, dry=False, seed=False)
    assert list(v["status"] for v in st["blocchi"].values()) == ["pending"]
    ch["lock"] = True  # appena libero, il blocco parte da solo
    postino.processa_requests("merlino", st, t0 + postino.GRACE_S + 65, dry=False, seed=False)
    assert ch["wake"] == ["merlino"]


def test_nodo_giu_riprova(env):
    bridge, ch = env
    _scrivi_requests(env, ["## REQ-MERL-Z | 2026-10-29 17:00 UTC | PENDING", ""])
    t0 = time.time()
    st = _stato()
    postino.processa_requests("merlino", st, t0, dry=False, seed=False)
    ch["reach"] = False
    postino.processa_requests("merlino", st, t0 + postino.GRACE_S + 5, dry=False, seed=False)
    assert ch["wake"] == []
    assert list(v["status"] for v in st["blocchi"].values()) == ["pending"]  # riprova dopo
    ch["reach"] = True
    postino.processa_requests("merlino", st, t0 + postino.GRACE_S + 65, dry=False, seed=False)
    assert ch["wake"] == ["merlino"]


def test_fusibile(env):
    bridge, ch = env
    _scrivi_requests(env, ["## REQ-MERL-W | 2026-10-29 17:00 UTC | PENDING", ""])
    t0 = time.time()
    st = _stato()
    st["lanci"]["merlino"] = [t0 - 60, t0 - 120, t0 - 180]  # 3 in un'ora
    postino.processa_requests("merlino", st, t0, dry=False, seed=False)
    postino.processa_requests("merlino", st, t0 + postino.GRACE_S + 5, dry=False, seed=False)
    assert ch["wake"] == []
    assert "fuse" in [v["status"] for v in st["blocchi"].values()]


def test_storico(env):
    bridge, ch = env
    _scrivi_requests(env, ["## REQ-1 vecchio", "## REQ-2 vecchio", "## REQ-3 ultimo"])
    st = _stato()
    postino.processa_requests("merlino", st, time.time(), dry=False, seed=False)
    stati = [v["status"] for v in st["blocchi"].values()]
    assert sorted(stati) == ["pending", "storico", "storico"]


def test_results_inbox_dedup(env):
    bridge, ch = env
    p = bridge / "merlino" / "results.md"
    p.write_text("## DONE | REQ-1 | MERLINO\nfatto\n## ACK | REQ-2\n", encoding="utf-8")
    t0 = time.time()
    st = _stato()
    inbox, out = postino.processa_results("merlino", st, t0, dry=False, seed=False)
    assert len(inbox) == 2
    testo = postino.ARTU_INBOX.read_text(encoding="utf-8")
    assert testo.count("**merlino**") == 2
    inbox2, _ = postino.processa_results("merlino", st, t0 + 10, dry=False, seed=False)
    assert inbox2 == []  # dedup


def test_results_firma_artu_saltata(env):
    bridge, ch = env
    (bridge / "merlino" / "results.md").write_text(
        "## DONE | REQ-9 | MERLINO\nfatto\n-- MERLINO\n"
        "## REVIEW | REQ-8\nok\n-- [hermes] ARTÙ\n", encoding="utf-8")
    st = _stato()
    inbox, _ = postino.processa_results("merlino", st, time.time(), dry=False, seed=False)
    assert len(inbox) == 1  # il blocco firmato da Artu' non entra in inbox/TG


def test_seed_non_agisce(env):
    bridge, ch = env
    _scrivi_requests(env, ["## REQ-MERL-S | PENDING", ""])
    (bridge / "merlino" / "results.md").write_text("## DONE | REQ-S\n", encoding="utf-8")
    st = _stato()
    postino.processa_requests("merlino", st, time.time(), dry=False, seed=True)
    postino.processa_results("merlino", st, time.time(), dry=False, seed=True)
    assert ch["wake"] == []
    assert not postino.ARTU_INBOX.exists()
    assert all(v["status"] == "seed" for v in st["blocchi"].values())


def test_pota_stato(tmp_path, monkeypatch):
    monkeypatch.setattr(postino, "STATO", tmp_path / "state.json")
    st = _stato()
    ora = time.time()
    st["blocchi"]["a"] = {"first_seen": ora - postino.POTA_S - 100, "status": "inbox"}
    st["blocchi"]["b"] = {"first_seen": ora, "status": "inbox"}
    st["lanci"]["merlino"] = [ora - 7200, ora - 60]
    postino._stato_salva(st, dry=False)
    ric = postino._stato_carica()
    assert list(ric["blocchi"]) == ["b"]
    assert len(ric["lanci"]["merlino"]) == 1
