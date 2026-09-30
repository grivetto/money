"""JobStore SQLite per la Fabbrica (lease, dedup, retry) — consegna J1 via A0-MC2.

Provenienza: implementato da Agent Zero (A0-MC2, contesto NTG4B2h5, 30/09/2026),
verificato da Hermes (10/10 test nella venv del repo) e integrato in `fabbrica/jobs.py`.
Solo stdlib; niente I/O di rete; tempi iniettabili via `now_ms` per i test.
"""
import sqlite3
import json
import uuid
import time
from typing import Optional, Dict, Any, List


class JobStore:
    def __init__(self, path: str):
        """Apre/crea SQLite; PRAGMA journal_mode=WAL; crea la tabella se manca:
        jobs(job_id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
             idempotency_key TEXT NOT NULL UNIQUE, state TEXT NOT NULL DEFAULT 'queued',
             attempt INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL DEFAULT 3,
             lease_until INTEGER, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
             last_error TEXT)"""
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                payload TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                state TEXT NOT NULL DEFAULT 'queued',
                attempt INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 3,
                lease_until INTEGER,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                last_error TEXT
            )
        """)
        self.conn.commit()

    def _now_ms(self, now_ms: Optional[int]) -> int:
        if now_ms is None:
            return int(time.time() * 1000)
        return now_ms

    def enqueue(self, kind, payload, idempotency_key, max_attempts=3, now_ms=None) -> str:
        """payload: dict -> salvato come JSON (sort_keys=True, separators compatti).
        DEDUP: se idempotency_key esiste gia' -> ritorna il job_id ESISTENTE, non crea nulla.
        Altrimenti: job_id = uuid4().hex, state='queued', attempt=0."""
        now = self._now_ms(now_ms)
        payload_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        
        # Check for existing idempotency_key
        cursor = self.conn.execute(
            "SELECT job_id FROM jobs WHERE idempotency_key = ?",
            (idempotency_key,)
        )
        row = cursor.fetchone()
        if row:
            return row[0]
        
        job_id = uuid.uuid4().hex
        self.conn.execute(
            """INSERT INTO jobs (job_id, kind, payload, idempotency_key, state, attempt, max_attempts,
                          lease_until, created_at, updated_at, last_error)
                       VALUES (?, ?, ?, ?, 'queued', 0, ?, NULL, ?, ?, NULL)""",
            (job_id, kind, payload_json, idempotency_key, max_attempts, now, now)
        )
        self.conn.commit()
        return job_id

    def claim(self, now_ms=None, lease_ms=300_000) -> Optional[Dict[str, Any]]:
        """Prende UN job: prima il 'queued' piu' vecchio per created_at; se non ce ne sono,
        il 'running' con lease_until <= now_ms (lease scaduta -> ri-claim). Porta il job a
        'running', attempt += 1, lease_until = now_ms + lease_ms, updated_at = now_ms.
        Ritorna {} con campi anche 'payload' (dict decodificato) e 'lease_until', o None."""
        now = self._now_ms(now_ms)
        
        # First try: oldest queued job
        cursor = self.conn.execute(
            """SELECT job_id, kind, payload, idempotency_key, state, attempt, max_attempts,
                          lease_until, created_at, updated_at, last_error
                   FROM jobs
                   WHERE state = 'queued'
                   ORDER BY created_at ASC, job_id ASC
                   LIMIT 1"""
        )
        row = cursor.fetchone()
        
        if not row:
            # Second try: running with expired lease
            cursor = self.conn.execute(
                """SELECT job_id, kind, payload, idempotency_key, state, attempt, max_attempts,
                              lease_until, created_at, updated_at, last_error
                       FROM jobs
                       WHERE state = 'running' AND lease_until <= ?
                       ORDER BY created_at ASC, job_id ASC
                       LIMIT 1""",
                (now,)
            )
            row = cursor.fetchone()
        
        if not row:
            return None
        
        job_id, kind, payload_json, idempotency_key, state, attempt, max_attempts, lease_until, created_at, updated_at, last_error = row
        
        new_attempt = attempt + 1
        new_lease_until = now + lease_ms
        
        self.conn.execute(
            """UPDATE jobs SET state = 'running', attempt = ?, lease_until = ?, updated_at = ?
                       WHERE job_id = ?""",
            (new_attempt, new_lease_until, now, job_id)
        )
        self.conn.commit()
        
        return {
            'job_id': job_id,
            'kind': kind,
            'payload': json.loads(payload_json),
            'idempotency_key': idempotency_key,
            'state': 'running',
            'attempt': new_attempt,
            'max_attempts': max_attempts,
            'lease_until': new_lease_until,
            'created_at': created_at,
            'updated_at': now,
            'last_error': last_error
        }

    def complete(self, job_id, now_ms=None) -> None:
        """state='done', lease_until=NULL, updated_at=now."""
        now = self._now_ms(now_ms)
        self.conn.execute(
            "UPDATE jobs SET state = 'done', lease_until = NULL, updated_at = ? WHERE job_id = ?",
            (now, job_id)
        )
        self.conn.commit()

    def fail(self, job_id, error, now_ms=None) -> str:
        """state: 'queued' se attempt < max_attempts (riprova), altrimenti 'failed'.
        last_error = str(error) troncato a 500 caratteri; lease_until=NULL.
        Ritorna il nuovo state."""
        now = self._now_ms(now_ms)
        
        cursor = self.conn.execute(
            "SELECT attempt, max_attempts FROM jobs WHERE job_id = ?",
            (job_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Job {job_id} not found")
        
        attempt, max_attempts = row
        error_str = str(error)[:500]
        
        if attempt < max_attempts:
            new_state = 'queued'
        else:
            new_state = 'failed'
        
        self.conn.execute(
            "UPDATE jobs SET state = ?, last_error = ?, lease_until = NULL, updated_at = ? WHERE job_id = ?",
            (new_state, error_str, now, job_id)
        )
        self.conn.commit()
        return new_state

    def pending(self, now_ms=None) -> List[Dict[str, Any]]:
        """Tutti i job 'queued' + 'running', ordinati per created_at (e job_id)."""
        now = self._now_ms(now_ms)
        cursor = self.conn.execute(
            """SELECT job_id, kind, payload, idempotency_key, state, attempt, max_attempts,
                          lease_until, created_at, updated_at, last_error
                   FROM jobs
                   WHERE state IN ('queued', 'running')
                   ORDER BY created_at ASC, job_id ASC"""
        )
        result = []
        for row in cursor.fetchall():
            job_id, kind, payload_json, idempotency_key, state, attempt, max_attempts, lease_until, created_at, updated_at, last_error = row
            result.append({
                'job_id': job_id,
                'kind': kind,
                'payload': json.loads(payload_json),
                'idempotency_key': idempotency_key,
                'state': state,
                'attempt': attempt,
                'max_attempts': max_attempts,
                'lease_until': lease_until,
                'created_at': created_at,
                'updated_at': updated_at,
                'last_error': last_error
            })
        return result

    def stats(self, now_ms=None) -> Dict[str, Any]:
        """{"queued": n, "running": n, "done": n, "failed": n,
            "oldest_queued_age_ms": int|None}"""
        now = self._now_ms(now_ms)
        
        cursor = self.conn.execute(
            "SELECT state, COUNT(*) FROM jobs GROUP BY state"
        )
        counts = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Get oldest queued age
        cursor = self.conn.execute(
            "SELECT MIN(created_at) FROM jobs WHERE state = 'queued'"
        )
        row = cursor.fetchone()
        oldest_queued_age_ms = None
        if row and row[0] is not None:
            oldest_queued_age_ms = now - row[0]
        
        return {
            'queued': counts.get('queued', 0),
            'running': counts.get('running', 0),
            'done': counts.get('done', 0),
            'failed': counts.get('failed', 0),
            'oldest_queued_age_ms': oldest_queued_age_ms
        }

    def close(self) -> None:
        self.conn.close()