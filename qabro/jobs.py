"""Durable, leased jobs for exploration and validation."""

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class Job:
    id: str
    kind: str
    payload: dict
    lease: str


class JobQueue:
    def __init__(self, path: Path):
        self.path = path
        with closing(sqlite3.connect(path)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    lease TEXT,
                    expires_ns INTEGER,
                    result TEXT
                )
            """)

    def enqueue(self, job_id: str, kind: str, payload: dict, *, priority: int = 0) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            self.enqueue_in(db, job_id, kind, payload, priority=priority)

    @staticmethod
    def enqueue_in(
        db: sqlite3.Connection, job_id: str, kind: str, payload: dict, *, priority: int = 0,
    ) -> None:
        encoded = json.dumps(payload, sort_keys=True, allow_nan=False)
        db.execute(
            "INSERT INTO jobs(id, kind, payload, priority) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO NOTHING",
            (job_id, kind, encoded, priority),
        )
        stored = db.execute("SELECT kind, payload, priority FROM jobs WHERE id=?", (job_id,))
        if stored.fetchone() != (kind, encoded, priority):
            raise ValueError("Job ID already refers to different work")


    def claim(self, kind: str, *, now_ns: int, lease_ns: int) -> Job | None:
        if lease_ns <= 0:
            raise ValueError("Job lease must be positive")
        lease = uuid4().hex
        with closing(sqlite3.connect(self.path)) as db, db:
            row = db.execute(
                """
                UPDATE jobs SET lease=?, expires_ns=?
                WHERE rowid=(
                    SELECT rowid FROM jobs WHERE kind=? AND result IS NULL
                    AND (expires_ns IS NULL OR expires_ns<=?)
                    ORDER BY priority DESC, rowid LIMIT 1
                )
                RETURNING id, kind, payload
                """,
                (lease, now_ns + lease_ns, kind, now_ns),
            ).fetchone()
            if row is None:
                return None
            job_id, job_kind, payload = row
            return Job(job_id, job_kind, json.loads(payload), lease)

    def complete(self, job: Job, result: dict, *, now_ns: int) -> bool:
        encoded = json.dumps(result, sort_keys=True, allow_nan=False)
        with closing(sqlite3.connect(self.path)) as db, db:
            return db.execute(
                """
                UPDATE jobs SET result=?
                WHERE id=? AND lease=? AND (
                    (result IS NULL AND expires_ns>?) OR result=?
                )
                """,
                (encoded, job.id, job.lease, now_ns, encoded),
            ).rowcount == 1
