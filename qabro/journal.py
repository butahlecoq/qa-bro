"""Persistent ordered events and browser tab ownership."""

import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from time import time_ns


class DuplicateEvent(Exception):
    """A caller attempted to reserve an event twice."""


class Journal:
    def __init__(self, path: Path):
        self.path = path
        with closing(self._connect()) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS attempts (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    worker_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attempt_restarts (
                    attempt_id TEXT PRIMARY KEY REFERENCES attempts(id),
                    previous_id TEXT NOT NULL REFERENCES attempts(id),
                    setup_artifact_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS finished_attempts (
                    attempt_id TEXT PRIMARY KEY REFERENCES attempts(id),
                    finished_ns INTEGER NOT NULL,
                    pruned INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS pruned_verdicts (
                    attempt_id TEXT PRIMARY KEY REFERENCES attempts(id),
                    verdict TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    attempt_id TEXT NOT NULL REFERENCES attempts(id),
                    sequence INTEGER NOT NULL,
                    event_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (attempt_id, sequence),
                    UNIQUE (attempt_id, event_id)
                );
                CREATE TABLE IF NOT EXISTS resource_leases (
                    resource TEXT PRIMARY KEY,
                    attempt_id TEXT NOT NULL REFERENCES attempts(id)
                );
                CREATE TABLE IF NOT EXISTS tab_leases (
                    context_id TEXT NOT NULL,
                    tab_id TEXT NOT NULL,
                    attempt_id TEXT NOT NULL REFERENCES attempts(id),
                    PRIMARY KEY (context_id, tab_id)
                );
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def start(
        self, attempt: str, run: str, worker: str, *,
        restart_of: str | None = None, setup_artifact_id: str | None = None,
    ) -> None:
        if restart_of == attempt or (restart_of is None) != (setup_artifact_id is None):
            raise ValueError("A restart requires a previous attempt and setup evidence")
        if setup_artifact_id == "":
            raise ValueError("Setup evidence must have a reference")
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if restart_of is not None and db.execute(
                "SELECT run_id FROM attempts WHERE id=?", (restart_of,),
            ).fetchone() != (run,):
                raise ValueError("Restart must refer to a previous attempt in the same run")
            inserted = db.execute(
                "INSERT INTO attempts VALUES (?, ?, ?) ON CONFLICT(id) DO NOTHING",
                (attempt, run, worker),
            )
            owner = db.execute(
                "SELECT run_id, worker_id FROM attempts WHERE id=?", (attempt,)
            ).fetchone()
            if owner != (run, worker):
                raise ValueError("Attempt already belongs to a different run or worker")

            if inserted.rowcount and restart_of is not None:
                db.execute("INSERT INTO attempt_restarts VALUES (?, ?, ?)",
                           (attempt, restart_of, setup_artifact_id))
            stored = db.execute(
                "SELECT previous_id, setup_artifact_id FROM attempt_restarts WHERE attempt_id=?", (attempt,),
            ).fetchone()
            expected = (restart_of, setup_artifact_id) if restart_of is not None else None
            if stored != expected:
                raise ValueError("Attempt already has different restart metadata")

    def restart_metadata(self, attempt: str) -> dict:
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT previous_id, setup_artifact_id FROM attempt_restarts WHERE attempt_id=?", (attempt,),
            ).fetchone()
        return {"restart_of": row[0], "setup_artifact_id": row[1]} if row else {}

    def append(
        self, attempt: str, event: str, kind: str, payload: dict, *,
        reserve: bool = False, tab: tuple[str, str] | None = None,
        resources: tuple[str, ...] = (),
        authorize: Callable[[sqlite3.Connection], None] | None = None,
    ) -> int:
        encoded = json.dumps(payload, sort_keys=True, allow_nan=False)
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute(
                "SELECT 1 FROM finished_attempts WHERE attempt_id=? AND pruned=1", (attempt,),
            ).fetchone():
                raise ValueError("Attempt evidence has been pruned")
            if authorize is not None:
                authorize(db)
            if tab is not None:
                owner = db.execute(
                    "SELECT attempt_id FROM tab_leases WHERE context_id=? AND tab_id=?", tab
                ).fetchone()
                if owner != (attempt,):
                    raise PermissionError("Attempt does not own this browser tab")
            for resource in resources:
                owner = db.execute(
                    "SELECT attempt_id FROM resource_leases WHERE resource=?", (resource,)
                ).fetchone()
                if owner != (attempt,):
                    raise PermissionError("Attempt does not own the required UI resource")
            existing = db.execute(
                "SELECT sequence, kind, payload FROM events WHERE attempt_id=? AND event_id=?",
                (attempt, event),
            ).fetchone()
            if existing is not None:
                sequence, old_kind, old_payload = existing
                if (old_kind, old_payload) != (kind, encoded):
                    raise ValueError("Event ID already records different evidence")
                if reserve:
                    raise DuplicateEvent(event)
                return sequence
            sequence = db.execute(
                """
                INSERT INTO events
                SELECT ?, COALESCE(MAX(sequence), 0) + 1, ?, ?, ?
                FROM events WHERE attempt_id=?
                RETURNING sequence
                """,
                (attempt, event, kind, encoded, attempt),
            ).fetchone()[0]

            if kind == "scenario_finish":
                db.execute("INSERT INTO finished_attempts VALUES (?, ?, 0)", (attempt, time_ns()))
            return sequence

    def prune(self, *, before_ns: int, max_payload_bytes: int) -> int:
        """Retain incomplete runs and evidence protected by live references."""
        if max_payload_bytes < 0:
            raise ValueError("Journal size limit must be nonnegative")
        from qabro.artifacts import ArtifactStore
        ArtifactStore(self.path)
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            total = db.execute("SELECT COALESCE(SUM(length(CAST(payload AS BLOB))), 0) FROM events").fetchone()[0]
            runs = db.execute("""
                SELECT a.run_id, MAX(f.finished_ns)
                FROM attempts a LEFT JOIN finished_attempts f ON f.attempt_id=a.id
                GROUP BY a.run_id
                HAVING COUNT(*)=COUNT(f.attempt_id) AND MIN(f.pruned)=0 AND MAX(f.pruned)=0
                ORDER BY MAX(f.finished_ns), a.run_id
            """).fetchall()
            for run, finished_ns in runs:
                if finished_ns >= before_ns and total <= max_payload_bytes:
                    continue
                ids = [row[0] for row in db.execute("SELECT id FROM attempts WHERE run_id=?", (run,))]
                if any(self._protected(db, attempt) for attempt in ids):
                    continue
                for attempt in ids:
                    size = db.execute(
                        "SELECT COALESCE(SUM(length(CAST(payload AS BLOB))), 0) FROM events WHERE attempt_id=?",
                        (attempt,),
                    ).fetchone()[0]
                    db.execute("""
                        INSERT INTO pruned_verdicts
                        SELECT attempt_id, json_extract(payload, '$.verdict') FROM events
                        WHERE attempt_id=? AND event_id='scenario:finish'
                          AND json_type(payload, '$.verdict')='text'
                    """, (attempt,))
                    db.execute("DELETE FROM events WHERE attempt_id=?", (attempt,))
                    db.execute("UPDATE finished_attempts SET pruned=1 WHERE attempt_id=?", (attempt,))
                    total -= size
            return total

    def _protected(self, db: sqlite3.Connection, attempt: str) -> bool:
        if db.execute("""
            SELECT 1 FROM tab_leases WHERE attempt_id=?
            UNION ALL SELECT 1 FROM resource_leases WHERE attempt_id=?
            UNION ALL SELECT 1 FROM events e JOIN artifact_pins p
                      ON p.artifact_id=COALESCE(json_extract(e.payload, '$.artifact_id'),
                                               json_extract(e.payload, '$.evidence_id'))
                      WHERE e.attempt_id=? LIMIT 1
        """, (attempt, attempt, attempt)).fetchone():
            return True
        return bool(self._actions_to_reconcile(self._events(db, attempt)))

    def events(self, attempt: str) -> list[tuple[int, str, str, dict]]:
        with closing(self._connect()) as db:
            return self._events(db, attempt)

    @staticmethod
    def _events(db: sqlite3.Connection, attempt: str) -> list[tuple[int, str, str, dict]]:
        rows = db.execute(
            "SELECT sequence, event_id, kind, payload FROM events "
            "WHERE attempt_id=? ORDER BY sequence",
            (attempt,),
        )
        return [(sequence, event, kind, json.loads(payload))
                for sequence, event, kind, payload in rows]

    def attempts_for_run(self, run: str) -> list[str]:
        with closing(self._connect()) as db:
            rows = db.execute("SELECT id FROM attempts WHERE run_id=? ORDER BY rowid", (run,))
            return [attempt for (attempt,) in rows]

    def pruned_attempts_for_run(self, run: str) -> list[str]:
        with closing(self._connect()) as db:
            rows = db.execute(
                """
                SELECT a.id FROM attempts a
                JOIN finished_attempts f ON f.attempt_id=a.id
                WHERE a.run_id=? AND f.pruned=1 ORDER BY a.rowid
                """,
                (run,),
            )
            return [attempt for (attempt,) in rows]

    def has_pruned_failure(self, run: str) -> bool:
        with closing(self._connect()) as db:
            return db.execute("""
                SELECT 1 FROM pruned_verdicts p JOIN attempts a ON a.id=p.attempt_id
                WHERE a.run_id=? AND p.verdict='FAIL' LIMIT 1
            """, (run,)).fetchone() is not None

    def events_of_kind(self, kind: str) -> list[tuple[str, dict]]:
        with closing(self._connect()) as db:
            rows = db.execute(
                "SELECT attempt_id, payload FROM events WHERE kind=? ORDER BY rowid", (kind,)
            )
            return [(attempt, json.loads(payload)) for attempt, payload in rows]

    def claim_resources(self, attempt: str, resources: tuple[str, ...]) -> bool:
        """Acquire the entire resource set atomically or leave ownership unchanged."""
        resources = tuple(sorted(set(resources)))
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            for resource in resources:
                owner = db.execute(
                    "SELECT attempt_id FROM resource_leases WHERE resource=?", (resource,)
                ).fetchone()
                if owner is not None and owner != (attempt,):
                    return False
            db.executemany(
                "INSERT INTO resource_leases VALUES (?, ?) ON CONFLICT(resource) DO NOTHING",
                ((resource, attempt) for resource in resources),
            )
        return True

    def release_resources(self, attempt: str) -> None:
        """Release resources after the caller verifies that its work has stopped."""
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if self._actions_to_reconcile(self._events(db, attempt)):
                raise RuntimeError("Cannot release resources while browser effects are unresolved")
            db.execute("DELETE FROM resource_leases WHERE attempt_id=?", (attempt,))

    def finish_probe_in(self, db: sqlite3.Connection, attempt: str, context: str, tab: str) -> None:
        if self._actions_to_reconcile(self._events(db, attempt)):
            raise RuntimeError("Cannot finish probe while browser effects are unresolved")
        db.execute("DELETE FROM resource_leases WHERE attempt_id=?", (attempt,))
        db.execute(
            "DELETE FROM tab_leases WHERE context_id=? AND tab_id=? AND attempt_id=?",
            (context, tab, attempt),
        )

    def claim_tab(
        self, context: str, tab: str, attempt: str, *, parent: str | None = None,
    ) -> bool:
        """Reserve an observed child only for the owner of its parent tab."""
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if parent is not None:
                owner = db.execute(
                    "SELECT attempt_id FROM tab_leases WHERE context_id=? AND tab_id=?",
                    (context, parent),
                ).fetchone()
                if owner != (attempt,):
                    return False
            db.execute(
                "INSERT INTO tab_leases VALUES (?, ?, ?) "
                "ON CONFLICT(context_id, tab_id) DO NOTHING",
                (context, tab, attempt),
            )
            return db.execute(
                "SELECT attempt_id FROM tab_leases WHERE context_id=? AND tab_id=?",
                (context, tab),
            ).fetchone() == (attempt,)

    def release_tab(self, context: str, tab: str, attempt: str) -> bool:
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            events = self._events(db, attempt)
            finishes = {event for _, event, kind, _ in events if kind == "tool_finish"}
            pending = list(self._actions_to_reconcile(events))
            pending.extend(
                (event, payload) for _, event, kind, payload in events
                if kind == "tool_start" and payload.get("read_only") is True
                and f"{event.removesuffix(':start')}:finish" not in finishes
            )
            if any((payload.get("context"), payload.get("tab")) == (context, tab)
                   for _, payload in pending):
                return False
            return db.execute(
                "DELETE FROM tab_leases WHERE context_id=? AND tab_id=? AND attempt_id=?",
                (context, tab, attempt),
            ).rowcount == 1

    def actions_to_reconcile(self, attempt: str) -> list[tuple[str, dict]]:
        """Return started actions without a known tool outcome or reconciliation."""
        return self._actions_to_reconcile(self.events(attempt))

    @staticmethod
    def _actions_to_reconcile(
        entries: list[tuple[int, str, str, dict]],
    ) -> list[tuple[str, dict]]:
        events = {event: (kind, payload) for _, event, kind, payload in entries}
        actions = []
        for event, (kind, payload) in events.items():
            if kind != "tool_start" or payload.get("read_only", False):
                continue
            action = event.removesuffix(":start")
            if f"{action}:reconciled" in events:
                continue
            finish = events.get(f"{action}:finish")
            if finish is None or finish[1]["outcome"] != "returned":
                actions.append((action, payload))
        return actions
