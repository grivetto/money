"""Race reali sul JobStore: enqueue concorrente e claim concorrente.

Ogni thread apre la SUA connessione (come farebbero due processi): il test
verifica che dedup e claim siano atomici anche sotto interleaving, cosa che i
test sequenziali non coprono (revisione Manus 06/10, finding P1).
Niente sleep: un barrier fa partire i thread insieme.
"""
from __future__ import annotations

import importlib.util
import sqlite3
import threading
from pathlib import Path

_RADICE = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("fabbrica_jobs_race", _RADICE / "fabbrica" / "jobs.py")
assert _SPEC is not None and _SPEC.loader is not None
_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_mod)
JobStore = _mod.JobStore


def test_enqueue_concorrente_stessa_key_un_solo_job(tmp_path):
    """8 scrittori in gara sulla stessa idempotency_key: tutti ricevono lo STESSO
    job_id e sul disco esiste UNA sola riga. Niente IntegrityError."""
    db = str(tmp_path / "jobs.db")
    s0 = JobStore(db)
    s0.close()
    n = 8
    barrier = threading.Barrier(n)
    risultati: list = []
    errori: list = []

    def worker():
        try:
            s = JobStore(db)
            barrier.wait()
            risultati.append(s.enqueue("k", {"x": 1}, "chiave-unica"))
            s.close()
        except Exception as exc:  # noqa: BLE001
            errori.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errori, errori
    assert len(risultati) == n
    assert len(set(risultati)) == 1

    conn = sqlite3.connect(db)
    (count,) = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()
    conn.close()
    assert count == 1


def test_claim_concorrente_un_solo_vincitore(tmp_path):
    """8 worker in gara su UN job: esattamente uno lo prende; nessun errore."""
    db = str(tmp_path / "jobs.db")
    s0 = JobStore(db)
    s0.enqueue("k", {}, "k1", now_ms=0)
    s0.close()

    n = 8
    barrier = threading.Barrier(n)
    vincitori: list = []
    errori: list = []

    def worker():
        try:
            s = JobStore(db)
            barrier.wait()
            for _ in range(30):
                j = s.claim(now_ms=10_000, lease_ms=60_000)
                if j is not None:
                    vincitori.append(j["job_id"])
            s.close()
        except Exception as exc:  # noqa: BLE001
            errori.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errori, errori
    assert len(vincitori) == 1


def test_claim_su_lease_scaduta_riprende_il_job(tmp_path):
    db = str(tmp_path / "jobs.db")
    s = JobStore(db)
    s.enqueue("k", {}, "k1", now_ms=0)
    j1 = s.claim(now_ms=0, lease_ms=1000)
    assert j1 is not None and j1["attempt"] == 1
    assert s.claim(now_ms=500) is None          # lease fresca: nessuno
    j2 = s.claim(now_ms=2000, lease_ms=1000)    # lease scaduta: ri-claim
    assert j2 is not None and j2["job_id"] == j1["job_id"] and j2["attempt"] == 2
    s.close()
