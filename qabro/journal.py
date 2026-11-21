"""Persistent ordered events and browser tab ownership."""

import json
import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path


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

    def start(self, attempt: str, run: str, worker: str) -> None:
        with closing(self._connect()) as db, db:
            db.execute(
                "INSERT INTO attempts VALUES (?, ?, ?) ON CONFLICT(id) DO NOTHING",
                (attempt, run, worker),
            )
            owner = db.execute(
                "SELECT run_id, worker_id FROM attempts WHERE id=?", (attempt,)
            ).fetchone()
            if owner != (run, worker):
                raise ValueError("Attempt already belongs to a different run or worker")

    def append(
        self, attempt: str, event: str, kind: str, payload: dict, *,
        reserve: bool = False, tab: tuple[str, str] | None = None,
        resources: tuple[str, ...] = (),
        authorize: Callable[[sqlite3.Connection], None] | None = None,
    ) -> int:
        encoded = json.dumps(payload, sort_keys=True, allow_nan=False)
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
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
            return db.execute(
                """
                INSERT INTO events
                SELECT ?, COALESCE(MAX(sequence), 0) + 1, ?, ?, ?
                FROM events WHERE attempt_id=?
                RETURNING sequence
                """,
                (attempt, event, kind, encoded, attempt),
            ).fetchone()[0]

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

    def claim_tab(self, context: str, tab: str, attempt: str) -> bool:
        with closing(self._connect()) as db, db:
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
            for _, payload in self._actions_to_reconcile(self._events(db, attempt)):
                if (payload.get("context"), payload.get("tab")) == (context, tab):
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
