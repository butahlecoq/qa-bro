"""Search a run's pinned view of the local skill catalog."""

import json
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Scope:
    platform: str
    component: str
    context: str
    role: str


@dataclass(frozen=True)
class SkillRef:
    id: str
    revision: str
    summary: str


class Catalog:
    def __init__(self, path: Path):
        self.path = path
        with closing(sqlite3.connect(path)) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS skill_revisions (
                    row_id INTEGER PRIMARY KEY,
                    id TEXT NOT NULL, revision TEXT NOT NULL, summary TEXT NOT NULL,
                    platform TEXT NOT NULL, component TEXT NOT NULL,
                    context TEXT NOT NULL, role TEXT NOT NULL,
                    capabilities TEXT NOT NULL, hint TEXT NOT NULL,
                    UNIQUE (id, revision)
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS skill_search USING fts5(summary);
                CREATE TABLE IF NOT EXISTS active_skills (
                    id TEXT PRIMARY KEY, row_id INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS quarantined_skills (
                    row_id INTEGER PRIMARY KEY REFERENCES skill_revisions(row_id),
                    reason TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS catalog_runs (id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS pinned_skills (
                    run_id TEXT NOT NULL, row_id INTEGER NOT NULL,
                    PRIMARY KEY (run_id, row_id)
                );
            """)

    def seed_verified_hint(
        self, ref: SkillRef, scope: Scope, hint: str, *, capabilities: frozenset[str] = frozenset()
    ) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            row_id = db.execute(
                """
                INSERT INTO skill_revisions (
                    id, revision, summary, platform, component, context, role, capabilities, hint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING row_id
                """,
                (ref.id, ref.revision, ref.summary, scope.platform, scope.component,
                 scope.context, scope.role, json.dumps(sorted(capabilities)), hint),
            ).fetchone()[0]
            db.execute("INSERT INTO skill_search(rowid, summary) VALUES (?, ?)", (row_id, ref.summary))
            db.execute(
                "INSERT INTO active_skills VALUES (?, ?) "
                "ON CONFLICT(id) DO UPDATE SET row_id=excluded.row_id",
                (ref.id, row_id),
            )

    def quarantine(self, ref: SkillRef, reason: str) -> None:
        """Exclude a revision from future runs and restore a compatible predecessor."""
        if not reason.strip():
            raise ValueError("Quarantine requires a reason")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT row_id FROM skill_revisions WHERE id=? AND revision=?",
                (ref.id, ref.revision),
            ).fetchone()
            if row is None:
                raise KeyError((ref.id, ref.revision))
            (row_id,) = row
            db.execute(
                "INSERT OR IGNORE INTO quarantined_skills VALUES (?, ?)", (row_id, reason)
            )
            affected = db.execute(
                "DELETE FROM active_skills WHERE id=? AND row_id=?", (ref.id, row_id)
            )
            if not affected.rowcount:
                return
            db.execute(
                """
                INSERT INTO active_skills
                SELECT previous.id, previous.row_id
                FROM skill_revisions previous
                JOIN skill_revisions current ON current.row_id=?
                WHERE previous.id=current.id AND previous.row_id<current.row_id
                  AND previous.platform=current.platform AND previous.component=current.component
                  AND previous.context=current.context AND previous.role=current.role
                  AND previous.capabilities=current.capabilities
                  AND NOT EXISTS (
                    SELECT 1 FROM quarantined_skills q WHERE q.row_id=previous.row_id
                  )
                ORDER BY previous.row_id DESC LIMIT 1
                """,
                (row_id,),
            )

    def pin(self, run: str) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            if db.execute("INSERT OR IGNORE INTO catalog_runs VALUES (?)", (run,)).rowcount:
                db.execute("INSERT INTO pinned_skills SELECT ?, row_id FROM active_skills", (run,))

    def search(
        self, run: str, query: str, scope: Scope, capabilities: frozenset[str], *, limit: int = 5
    ) -> list[SkillRef]:
        terms = re.findall(r"[^\W_]+", query)
        if not terms or limit <= 0:
            return []
        expression = " OR ".join(f'"{term}"' for term in terms)
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute(
                """
                SELECT r.id, r.revision, r.summary, r.capabilities
                FROM skill_search
                JOIN skill_revisions r ON r.row_id=skill_search.rowid
                JOIN pinned_skills p ON p.row_id=r.row_id
                WHERE skill_search MATCH ? AND p.run_id=?
                  AND r.platform=? AND r.component=? AND r.context=? AND r.role=?
                ORDER BY rank, r.id
                """,
                (expression, run, scope.platform, scope.component, scope.context, scope.role),
            )
            results = []
            for skill_id, revision, summary, required in rows:
                if capabilities.issuperset(json.loads(required)):
                    results.append(SkillRef(skill_id, revision, summary))
                    if len(results) == limit:
                        break
            return results

    def load_hint(self, run: str, ref: SkillRef) -> str | None:
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute(
                """
                SELECT r.hint FROM skill_revisions r JOIN pinned_skills p ON p.row_id=r.row_id
                WHERE p.run_id=? AND r.id=? AND r.revision=?
                """,
                (run, ref.id, ref.revision),
            ).fetchone()
            return row[0] if row else None
