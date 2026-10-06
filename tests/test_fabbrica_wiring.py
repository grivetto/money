"""Test del cablaggio job-store + lint nel tick della fabbrica (03/10/2026).

`fabbrica/fabbrica.py` vive fuori dal package `money`: si carica per percorso con
importlib (stesso pattern di test_fabbrica_jobs.py). Nessuna rete: i controlli
testati lavorano solo su file dentro una cartella temporanea.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_RADICE = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("fabbrica_mod", _RADICE / "fabbrica" / "fabbrica.py")
assert _SPEC is not None and _SPEC.loader is not None
_fab = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_fab)

JobStore = _fab._jobstore()


@pytest.fixture
def amb(cartella, monkeypatch):
    """Fabbrica in miniatura: BASE e REPO puntano in una cartella di test."""
    base = cartella / "fabbrica"
    base.mkdir()
    (base / "inbox").mkdir()
    (base / "log").mkdir()
    (base / "shards").mkdir()
    repo = cartella
    (repo / "coda_catena").mkdir()
    monkeypatch.setattr(_fab, "BASE", base)
    monkeypatch.setattr(_fab, "REPO", repo)
    monkeypatch.setattr(_fab, "LOG", base / "log" / "fabbrica.log")
    monkeypatch.setattr(_fab, "STATE", base / "state.json")
    monkeypatch.setattr(_fab, "STATEDOC", base / "STATO.md")
    monkeypatch.setattr(_fab, "METRICS", base / "metrics.prom")
    monkeypatch.setattr(_fab, "SHARDS", base / "shards")
    monkeypatch.setattr(_fab, "_JOBSTORE", JobStore)
    return base, repo


def _jobs(base):
    return JobStore(str(base / "jobs.db"))


def test_jobs_accoda_dedup_attraverso_i_tick(amb):
    base, _ = amb
    (base / "candidati.json").write_text(json.dumps([{"id": "P99", "spec": "coda_catena/P99.md"}]))
    st = {"kill_switch": False, "spec_next": "P99", "spec_next_desc": "test"}
    _fab.check_jobs(st)
    _fab.check_jobs(st)
    s = _jobs(base)
    try:
        pending = s.pending()
        assert len(pending) == 1
        assert pending[0]["kind"] == "spec_materialize"
        assert pending[0]["idempotency_key"] == "spec_materialize:P99"
    finally:
        s.close()
    assert st["jobs"]["queued"] == 1


def test_jobs_chiude_spec_materializzata(amb):
    base, repo = amb
    (base / "candidati.json").write_text(json.dumps([{"id": "P99", "spec": "coda_catena/P99.md"}]))
    st = {"kill_switch": False, "spec_next": "P99"}
    _fab.check_jobs(st)
    assert st["jobs"]["queued"] == 1
    (repo / "coda_catena" / "P99.md").write_text("# spec")
    _fab.check_jobs(st)
    assert st["jobs"]["queued"] == 0
    assert st["jobs"]["done"] >= 1


def test_jobs_killswitch_non_accoda(amb):
    _, _ = amb
    st = {"kill_switch": True, "spec_next": "P99"}
    _fab.check_jobs(st)
    assert st["jobs"]["queued"] == 0


def test_jobs_chiude_fix_su_spec_aggiornata(amb):
    base, _ = amb
    st = {"kill_switch": False,
          "jev_gate_results": {"P99.md": {"hash": "aaaaaaaaaaaaaaaa", "flags": ["x"]}}}
    _fab.check_jobs(st)
    assert st["jobs"]["queued"] == 1
    st["jev_gate_results"]["P99.md"] = {"hash": "bbbbbbbbbbbbbbbb", "flags": ["x"]}
    _fab.check_jobs(st)
    # il vecchio job (hash aaa) e' chiuso; il nuovo (hash bbb) accodato
    assert st["jobs"]["done"] >= 1
    s = _jobs(base)
    try:
        keys = {j["idempotency_key"] for j in s.pending()}
        assert keys == {"spec_fix:jev:P99.md:bbbbbbbbbbbbbbbb"}
    finally:
        s.close()


def test_jobs_chiude_inbox_rimosso(amb):
    base, _ = amb
    f = base / "inbox" / "nota.txt"
    f.write_text("ciao")
    st = {"kill_switch": False}
    _fab.check_jobs(st)
    assert st["jobs"]["queued"] == 1
    f.unlink()
    _fab.check_jobs(st)
    assert st["jobs"]["queued"] == 0
    assert st["jobs"]["done"] >= 1


def test_lint_rileva_e_ricalcola(amb):
    _, repo = amb
    spec = repo / "coda_catena" / "P99.md"
    spec.write_text("solo testo senza blocchi")
    st = {}
    _fab.check_lint(st)
    r1 = st["lint_results"]["P99.md"]
    assert r1["ok"] is False
    assert "obiettivo" in r1["missing"]
    spec.write_text(
        "## Obiettivo\nrepo abcdef1\ninput output\ntest atteso\n- [ ] a\n- [ ] b\n"
        "fuori scope\n```bash\nls\n```\n"
    )
    _fab.check_lint(st)
    r2 = st["lint_results"]["P99.md"]
    assert r2["hash"] != r1["hash"]
    assert "obiettivo" not in r2["missing"]


def test_stato_e_metriche_mostrano_jobs(amb):
    base, _ = amb
    st = {"jobs": {"queued": 2, "running": 0, "done": 1, "failed": 0, "oldest_queued_age_s": 61},
          "lint_results": {"P99.md": {"hash": "x", "missing": ["obiettivo"]}},
          "control_rev": "abc1234"}
    _fab.write_stato(st)
    _fab.write_metrics(st)
    stato = (base / "STATO.md").read_text()
    met = (base / "metrics.prom").read_text()
    assert "job-store: queued 2 (piu' vecchio 61s)" in stato
    assert "control-plane: money@abc1234" in stato
    assert "factory_jobs_queued 2" in met
    assert "factory_specs_lint_bad 1" in met


def test_concluse_chiudono_i_job_spec_fix(amb):
    """Una spec in CONCLUSE.md esce dal gate: i suoi job spec_fix si chiudono da soli."""
    base, repo = amb
    st = {"kill_switch": False,
          "jev_gate_results": {"P99.md": {"hash": "aaaaaaaaaaaaaaaa", "flags": ["x"]}}}
    _fab.check_jobs(st)
    assert st["jobs"]["queued"] == 1                      # senza concluse: accodato
    (repo / "coda_catena" / "CONCLUSE.md").write_text("- P99.md \u2014 archiviata (test)\n")
    _fab.check_jobs(st)
    assert st["jobs"]["queued"] == 0                      # conclusa: chiuso, non ri-accodato
    assert st["jobs"]["done"] >= 1


def test_concluse_non_accodano_nuovi_fix(amb):
    base, repo = amb
    (repo / "coda_catena" / "CONCLUSE.md").write_text("- P99.md \u2014 archiviata (test)\n")
    st = {"kill_switch": False,
          "jev_gate_results": {"P99.md": {"hash": "aaaaaaaaaaaaaaaa", "flags": ["x"]}},
          "lint_results": {"P99.md": {"hash": "aaaaaaaaaaaaaaaa", "missing": ["obiettivo"]}}}
    _fab.check_jobs(st)
    assert st["jobs"]["queued"] == 0


def test_lint_salta_e_pulisce_le_concluse(amb):
    _, repo = amb
    (repo / "coda_catena" / "P99.md").write_text("solo testo senza blocchi")
    st = {}
    _fab.check_lint(st)
    assert "P99.md" in st["lint_results"]
    (repo / "coda_catena" / "CONCLUSE.md").write_text("- P99.md \u2014 archiviata (test)\n")
    _fab.check_lint(st)
    assert "P99.md" not in st["lint_results"]


def test_concluse_file_assente_fail_open(amb):
    _, _ = amb
    assert _fab._spec_concluse() == set()


def test_lint_ignora_il_file_concluse_stesso(amb):
    _, repo = amb
    (repo / "coda_catena" / "CONCLUSE.md").write_text("- P99.md \u2014 archiviata (test)\n")
    st = {}
    _fab.check_lint(st)
    assert "CONCLUSE.md" not in (st.get("lint_results") or {})
