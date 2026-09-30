"""Test del job-store della Fabbrica (consegna J1 via A0-MC2, 30/09/2026).

`fabbrica/jobs.py` vive fuori dal package `money`: si carica per percorso con importlib.
Tempi sempre iniettati (`now_ms`): nessun `sleep` nella suite.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_RADICE = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("fabbrica_jobs", _RADICE / "fabbrica" / "jobs.py")
assert _SPEC is not None and _SPEC.loader is not None
_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_mod)
JobStore = _mod.JobStore


@pytest.fixture
def store(cartella):
    """Uno store isolato per ogni test (cartella del conftest, niente tempfile)."""
    s = JobStore(str(cartella / "jobs_test.db"))
    yield s
    s.close()


def test_enqueue_get(store):
    """1. test_enqueue_get — job creato: state 'queued', attempt 0."""
    now = 1_000_000_000_000
    job_id = store.enqueue('test_kind', {'foo': 'bar'}, 'idem-key-1', now_ms=now)
    
    assert job_id is not None
    assert len(job_id) == 32  # uuid4().hex
    
    # Verify job state by checking pending
    pending = store.pending(now_ms=now)
    assert len(pending) == 1
    job = pending[0]
    assert job['job_id'] == job_id
    assert job['kind'] == 'test_kind'
    assert job['payload'] == {'foo': 'bar'}
    assert job['idempotency_key'] == 'idem-key-1'
    assert job['state'] == 'queued'
    assert job['attempt'] == 0
    assert job['max_attempts'] == 3
    assert job['lease_until'] is None
    assert job['created_at'] == now
    assert job['updated_at'] == now
    assert job['last_error'] is None


def test_dedup(store):
    """2. test_dedup — stesso idempotency_key due volte -> stesso job_id; COUNT(*) == 1."""
    now = 1_000_000_000_000
    job_id1 = store.enqueue('kind1', {'a': 1}, 'same-key', now_ms=now)
    job_id2 = store.enqueue('kind2', {'b': 2}, 'same-key', now_ms=now + 1000)
    
    assert job_id1 == job_id2
    
    # Verify only one row in database
    cursor = store.conn.execute("SELECT COUNT(*) FROM jobs")
    count = cursor.fetchone()[0]
    assert count == 1


def test_claim(store):
    """3. test_claim — prende il 'queued' piu' vecchio -> 'running', attempt 1, lease_until = now+lease_ms."""
    now = 1_000_000_000_000
    
    # Enqueue two jobs, first one older
    job_id1 = store.enqueue('kind1', {'x': 1}, 'key1', now_ms=now)
    job_id2 = store.enqueue('kind2', {'x': 2}, 'key2', now_ms=now + 1000)
    
    # Claim should get the oldest (job_id1)
    claimed = store.claim(now_ms=now, lease_ms=300_000)
    
    assert claimed is not None
    assert claimed['job_id'] == job_id1
    assert claimed['state'] == 'running'
    assert claimed['attempt'] == 1
    assert claimed['lease_until'] == now + 300_000
    assert claimed['updated_at'] == now
    assert claimed['payload'] == {'x': 1}
    
    # Second job should still be queued, first is running
    pending = store.pending(now_ms=now)
    assert len(pending) == 2  # 1 running + 1 queued
    # Find the queued one
    queued_jobs = [j for j in pending if j['state'] == 'queued']
    running_jobs = [j for j in pending if j['state'] == 'running']
    assert len(queued_jobs) == 1
    assert queued_jobs[0]['job_id'] == job_id2
    assert queued_jobs[0]['state'] == 'queued'
    assert len(running_jobs) == 1
    assert running_jobs[0]['job_id'] == job_id1
    assert running_jobs[0]['state'] == 'running'


def test_claim_vuoto(store):
    """4. test_claim_vuoto — dopo aver claimato tutto, claim() -> None."""
    now = 1_000_000_000_000
    
    job_id = store.enqueue('kind', {'x': 1}, 'key1', now_ms=now)
    claimed = store.claim(now_ms=now, lease_ms=300_000)
    
    assert claimed is not None
    assert claimed['job_id'] == job_id
    
    # Now claim again - should return None since only one job and it's running with valid lease
    claimed2 = store.claim(now_ms=now, lease_ms=300_000)
    assert claimed2 is None


def test_lease_scaduta(store):
    """5. test_lease_scaduta — claim, poi claim(now_ms=primo_now+lease_ms+1) -> STESSO job, attempt 2."""
    now = 1_000_000_000_000
    lease_ms = 300_000
    
    job_id = store.enqueue('kind', {'x': 1}, 'key1', now_ms=now)
    claimed1 = store.claim(now_ms=now, lease_ms=lease_ms)
    
    assert claimed1 is not None
    assert claimed1['job_id'] == job_id
    assert claimed1['attempt'] == 1
    assert claimed1['lease_until'] == now + lease_ms
    
    # After lease expires (now + lease_ms + 1)
    expired_now = now + lease_ms + 1
    claimed2 = store.claim(now_ms=expired_now, lease_ms=lease_ms)
    
    assert claimed2 is not None
    assert claimed2['job_id'] == job_id  # Same job
    assert claimed2['attempt'] == 2  # Attempt incremented
    assert claimed2['lease_until'] == expired_now + lease_ms
    assert claimed2['updated_at'] == expired_now


def test_complete(store):
    """6. test_complete -> 'done'; claim() non lo riprende piu'."""
    now = 1_000_000_000_000
    
    job_id = store.enqueue('kind', {'x': 1}, 'key1', now_ms=now)
    claimed = store.claim(now_ms=now, lease_ms=300_000)
    assert claimed['job_id'] == job_id
    
    store.complete(job_id, now_ms=now + 1000)
    
    # Job should be done, not in pending
    pending = store.pending(now_ms=now + 1000)
    assert len(pending) == 0
    
    # Claim should not return it
    claimed2 = store.claim(now_ms=now + 1000, lease_ms=300_000)
    assert claimed2 is None
    
    # Stats should show done
    stats = store.stats(now_ms=now + 1000)
    assert stats['done'] == 1
    assert stats['queued'] == 0
    assert stats['running'] == 0


def test_fail_retry_e_finale(store):
    """7. test_fail_retry_e_finale — con tentativi residui -> 'queued'; oltre max -> 'failed'; last_error salvato."""
    now = 1_000_000_000_000
    
    # Job with max_attempts=3
    job_id = store.enqueue('kind', {'x': 1}, 'key1', max_attempts=3, now_ms=now)
    
    # First claim
    claimed = store.claim(now_ms=now, lease_ms=300_000)
    assert claimed['attempt'] == 1
    
    # Fail with attempt < max_attempts -> should go back to 'queued'
    new_state = store.fail(job_id, 'error 1', now_ms=now + 1000)
    assert new_state == 'queued'
    
    pending = store.pending(now_ms=now + 1000)
    assert len(pending) == 1
    assert pending[0]['state'] == 'queued'
    assert pending[0]['attempt'] == 1  # attempt stays at 1 until re-claimed
    assert pending[0]['last_error'] == 'error 1'
    
    # Second claim
    claimed2 = store.claim(now_ms=now + 2000, lease_ms=300_000)
    assert claimed2['attempt'] == 2
    
    # Fail again
    new_state2 = store.fail(job_id, 'error 2', now_ms=now + 3000)
    assert new_state2 == 'queued'
    
    # Third claim
    claimed3 = store.claim(now_ms=now + 4000, lease_ms=300_000)
    assert claimed3['attempt'] == 3
    
    # Fail third time - attempt == max_attempts -> should be 'failed'
    new_state3 = store.fail(job_id, 'error 3', now_ms=now + 5000)
    assert new_state3 == 'failed'
    
    # Should not be in pending
    pending = store.pending(now_ms=now + 5000)
    assert len(pending) == 0
    
    # Stats
    stats = store.stats(now_ms=now + 5000)
    assert stats['failed'] == 1
    
    # Test error truncation to 500 chars
    job_id2 = store.enqueue('kind', {'x': 2}, 'key2', max_attempts=1, now_ms=now + 10000)
    claimed4 = store.claim(now_ms=now + 10000, lease_ms=300_000)
    long_error = 'x' * 600
    store.fail(job_id2, long_error, now_ms=now + 11000)
    
    pending2 = store.pending(now_ms=now + 11000)
    assert len(pending2) == 0  # max_attempts=1, so should be failed
    
    # Check error was truncated
    cursor = store.conn.execute("SELECT last_error FROM jobs WHERE job_id = ?", (job_id2,))
    row = cursor.fetchone()
    assert row is not None
    assert len(row[0]) == 500
    assert row[0] == 'x' * 500


def test_stats_e_pending(store):
    """8. test_stats_e_pending — conteggi esatti e oldest_queued_age_ms corretto su tempi iniettati."""
    now = 1_000_000_000_000
    
    # Initially empty
    stats = store.stats(now_ms=now)
    assert stats['queued'] == 0
    assert stats['running'] == 0
    assert stats['done'] == 0
    assert stats['failed'] == 0
    assert stats['oldest_queued_age_ms'] is None
    assert store.pending(now_ms=now) == []
    
    # Add 3 jobs at different times
    job_id1 = store.enqueue('kind1', {'a': 1}, 'key1', now_ms=now)
    job_id2 = store.enqueue('kind2', {'a': 2}, 'key2', now_ms=now + 1000)
    job_id3 = store.enqueue('kind3', {'a': 3}, 'key3', now_ms=now + 2000)
    
    stats = store.stats(now_ms=now + 5000)
    assert stats['queued'] == 3
    assert stats['oldest_queued_age_ms'] == 5000  # now+5000 - now
    
    pending = store.pending(now_ms=now + 5000)
    assert len(pending) == 3
    assert pending[0]['job_id'] == job_id1
    assert pending[1]['job_id'] == job_id2
    assert pending[2]['job_id'] == job_id3
    
    # Claim one
    claimed = store.claim(now_ms=now + 5000, lease_ms=300_000)
    assert claimed['job_id'] == job_id1
    
    stats = store.stats(now_ms=now + 5000)
    assert stats['queued'] == 2
    assert stats['running'] == 1
    assert stats['oldest_queued_age_ms'] == 4000  # now+5000 - (now+1000)
    
    pending = store.pending(now_ms=now + 5000)
    assert len(pending) == 3  # queued + running
    
    # Complete one
    store.complete(job_id1, now_ms=now + 6000)
    
    stats = store.stats(now_ms=now + 6000)
    assert stats['queued'] == 2
    assert stats['running'] == 0
    assert stats['done'] == 1
    assert stats['oldest_queued_age_ms'] == 5000  # now+6000 - (now+1000)
    
    # Fail one to failed state
    claimed2 = store.claim(now_ms=now + 7000, lease_ms=300_000)
    assert claimed2['job_id'] == job_id2
    store.fail(job_id2, 'error', now_ms=now + 8000)  # max_attempts=3, attempt=1 -> queued
    
    # Need to claim and fail 2 more times to reach failed
    claimed3 = store.claim(now_ms=now + 9000, lease_ms=300_000)
    store.fail(job_id2, 'error', now_ms=now + 10000)
    claimed4 = store.claim(now_ms=now + 11000, lease_ms=300_000)
    store.fail(job_id2, 'error', now_ms=now + 12000)
    
    stats = store.stats(now_ms=now + 12000)
    assert stats['queued'] == 1
    assert stats['running'] == 0
    assert stats['done'] == 1
    assert stats['failed'] == 1
    assert stats['oldest_queued_age_ms'] == 10000  # now+12000 - (now+2000)


def test_wal_attivo(store):
    """9. test_wal_attivo — PRAGMA journal_mode == 'wal'."""
    cursor = store.conn.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    assert mode.lower() == 'wal'


def test_persistenza(store):
    """10. test_persistenza — chiudi e riapri lo store: i dati restano."""
    now = 1_000_000_000_000
    
    # Create jobs in first store instance
    job_id1 = store.enqueue('kind1', {'a': 1}, 'key1', now_ms=now)
    job_id2 = store.enqueue('kind2', {'a': 2}, 'key2', now_ms=now + 1000)
    
    claimed = store.claim(now_ms=now, lease_ms=300_000)
    assert claimed['job_id'] == job_id1
    
    store.complete(job_id1, now_ms=now + 1000)
    
    # Close and reopen
    db_path = store.conn.execute("PRAGMA database_list").fetchone()[2]
    store.close()
    
    # Reopen
    store2 = JobStore(db_path)
    
    # Check data persisted
    stats = store2.stats(now_ms=now + 2000)
    assert stats['queued'] == 1
    assert stats['done'] == 1
    assert stats['running'] == 0
    assert stats['failed'] == 0
    
    pending = store2.pending(now_ms=now + 2000)
    assert len(pending) == 1
    assert pending[0]['job_id'] == job_id2
    assert pending[0]['state'] == 'queued'
    assert pending[0]['payload'] == {'a': 2}
    
    # Verify the done job is not in pending
    cursor = store2.conn.execute("SELECT state FROM jobs WHERE job_id = ?", (job_id1,))
    row = cursor.fetchone()
    assert row[0] == 'done'
    
    store2.close()