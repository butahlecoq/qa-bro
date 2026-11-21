"""Content-addressed local evidence with transactional retention."""

import sqlite3
from contextlib import closing
from hashlib import sha256
from pathlib import Path


class ArtifactStore:
    def __init__(self, path: Path):
        self.path = path
        with closing(self._connect()) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS artifacts (
                    id TEXT PRIMARY KEY, content BLOB NOT NULL, used_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS artifact_pins (
                    owner TEXT NOT NULL,
                    artifact_id TEXT NOT NULL REFERENCES artifacts(id),
                    PRIMARY KEY (owner, artifact_id)
                );
            """)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.execute("PRAGMA foreign_keys=ON")
        return db

    def put(self, content: bytes, *, now: int, owner: str | None = None) -> str:
        artifact_id = sha256(content).hexdigest()
        with closing(self._connect()) as db, db:
            db.execute(
                "INSERT INTO artifacts VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE "
                "SET used_at=MAX(artifacts.used_at, excluded.used_at)",
                (artifact_id, content, now),
            )
            if owner is not None:
                db.execute("INSERT OR IGNORE INTO artifact_pins VALUES (?, ?)", (owner, artifact_id))
        return artifact_id

    def get(self, artifact_id: str) -> bytes | None:
        with closing(self._connect()) as db:
            row = db.execute("SELECT content FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
            return row[0] if row else None

    def unpin(self, owner: str) -> None:
        with closing(self._connect()) as db, db:
            db.execute("DELETE FROM artifact_pins WHERE owner=?", (owner,))

    def prune(self, *, before: int, max_bytes: int) -> int:
        """Delete expired or excess unpinned evidence and return remaining payload bytes."""
        if max_bytes < 0:
            raise ValueError("Artifact size limit must be nonnegative")
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            protected = "SELECT artifact_id FROM artifact_pins"
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='events' AND type='table'").fetchone():
                protected += """
                    UNION SELECT json_extract(payload, '$.artifact_id') FROM events
                    UNION SELECT json_extract(payload, '$.evidence_id') FROM events
                """
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='attempt_restarts' AND type='table'").fetchone():
                protected += """
                    UNION SELECT r.setup_artifact_id FROM attempt_restarts r
                    LEFT JOIN finished_attempts f ON f.attempt_id=r.attempt_id
                    WHERE COALESCE(f.pruned, 0)=0
                """
            db.execute(f"CREATE TEMP TABLE retained_artifacts AS {protected}")
            db.execute("CREATE INDEX retained_artifact_id ON retained_artifacts(artifact_id)")
            removable = "NOT EXISTS (SELECT 1 FROM retained_artifacts WHERE artifact_id=artifacts.id)"
            db.execute(f"DELETE FROM artifacts WHERE used_at<? AND {removable}", (before,))
            total = db.execute("SELECT COALESCE(SUM(length(content)), 0) FROM artifacts").fetchone()[0]
            if total <= max_bytes:
                return total
            rows = db.execute(f"""
                SELECT id, length(content) FROM artifacts WHERE {removable}
                ORDER BY used_at, id
            """).fetchall()
            for artifact_id, size in rows:
                db.execute("DELETE FROM artifacts WHERE id=?", (artifact_id,))
                total -= size
                if total <= max_bytes:
                    break
            return total
