"""Search a run's pinned view of the local skill catalog."""

import json
import re
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path

from qabro.jobs import JobQueue
from qabro.recipe_format import decode_recipe, encode_recipe
from qabro.runner import Recipe, RecipeCall, RecipeStep


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
        self.jobs = JobQueue(path)
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
                CREATE TABLE IF NOT EXISTS skill_recipes (
                    row_id INTEGER PRIMARY KEY REFERENCES skill_revisions(row_id), body TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS recipe_dependencies (
                    parent INTEGER NOT NULL, child INTEGER NOT NULL,
                    PRIMARY KEY (parent, child)
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS skill_search USING fts5(summary);
                CREATE TABLE IF NOT EXISTS active_skills (
                    id TEXT PRIMARY KEY, row_id INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS component_fingerprints (
                    scope TEXT PRIMARY KEY, fingerprint TEXT NOT NULL
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
        self, ref: SkillRef, scope: Scope, hint: str, *,
        capabilities: frozenset[str] = frozenset(), recipe: Recipe | None = None,
    ) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            self.publish_hint_in(db, ref, scope, hint, capabilities=capabilities, recipe=recipe)

    @staticmethod
    def publish_hint_in(
        db: sqlite3.Connection, ref: SkillRef, scope: Scope, hint: str, *,
        capabilities: frozenset[str], recipe: Recipe | None = None,
    ) -> None:
        if recipe is not None and (recipe.id, recipe.revision) != (ref.id, ref.revision):
            raise ValueError("Recipe and skill revision must match")
        if recipe is not None:
            tools = {step.tool for step in recipe.steps if isinstance(step, RecipeStep)}
            if not tools <= capabilities:
                raise ValueError("Recipe uses browser tools missing from its declared capabilities")
        dependencies = set()
        for node in recipe.steps if recipe is not None else ():
            if not isinstance(node, RecipeCall):
                continue
            dependency = db.execute(
                """
                SELECT r.row_id, r.capabilities FROM skill_revisions r
                JOIN skill_recipes recipe ON recipe.row_id=r.row_id
                WHERE r.id=? AND r.revision=? AND r.platform=? AND r.component=?
                  AND r.context=? AND r.role=?
                  AND NOT EXISTS (SELECT 1 FROM quarantined_skills q WHERE q.row_id=r.row_id)
                """,
                (node.id, node.revision, scope.platform, scope.component, scope.context, scope.role),
            ).fetchone()
            if dependency is None or not capabilities.issuperset(json.loads(dependency[1])):
                raise ValueError("Nested recipe revision or necessary capabilities are unavailable")
            dependencies.add(dependency[0])
        row_id = db.execute(
            """
            INSERT INTO skill_revisions (
                id, revision, summary, platform, component, context, role, capabilities, hint
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING row_id
            """,
            (ref.id, ref.revision, ref.summary, scope.platform, scope.component,
             scope.context, scope.role, json.dumps(sorted(capabilities)), hint),
        ).fetchone()[0]
        if recipe is not None:
            db.execute("INSERT INTO skill_recipes VALUES (?, ?)", (row_id, encode_recipe(recipe)))
            db.executemany("INSERT INTO recipe_dependencies VALUES (?, ?)",
                           ((row_id, child) for child in dependencies))
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

    def quarantine_scope(self, scope: Scope, reason: str) -> list[SkillRef]:
        """Invalidate all known revisions in a changed component context."""
        if not reason.strip():
            raise ValueError("Quarantine requires a reason")
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            return self._quarantine_scope(db, scope, reason)

    def observe_component(self, scope: Scope, fingerprint: str) -> list[SkillRef]:
        """Record the observed component contract and revalidate on drift."""
        if not fingerprint.strip():
            raise ValueError("Component fingerprint is empty")
        key = json.dumps(asdict(scope), sort_keys=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT fingerprint FROM component_fingerprints WHERE scope=?", (key,)
            ).fetchone()
            if previous == (fingerprint,):
                return []
            db.execute(
                "INSERT INTO component_fingerprints VALUES (?, ?) "
                "ON CONFLICT(scope) DO UPDATE SET fingerprint=excluded.fingerprint",
                (key, fingerprint),
            )
            if previous is None:
                return []
            return self._quarantine_scope(db, scope, "Component fingerprint changed")

    def _quarantine_scope(
        self, db: sqlite3.Connection, scope: Scope, reason: str,
    ) -> list[SkillRef]:
        rows = db.execute(
            """
            SELECT r.row_id, r.id, r.revision, r.summary
            FROM skill_revisions r
            LEFT JOIN quarantined_skills q ON q.row_id=r.row_id
            WHERE r.platform=? AND r.component=? AND r.context=? AND r.role=?
              AND q.row_id IS NULL
            ORDER BY r.row_id
            """,
            (scope.platform, scope.component, scope.context, scope.role),
        ).fetchall()
        db.executemany(
            "INSERT INTO quarantined_skills VALUES (?, ?)",
            ((row_id, reason) for row_id, *_ in rows),
        )
        db.executemany(
            "DELETE FROM active_skills WHERE row_id=?",
            ((row_id,) for row_id, *_ in rows),
        )
        refs = []
        for row_id, skill_id, revision, summary in rows:
            ref = SkillRef(skill_id, revision, summary)
            self.jobs.enqueue_in(db, f"revalidate:{row_id}", "revalidate", {
                "skill": asdict(ref), "scope": asdict(scope), "reason": reason,
            })
            refs.append(ref)
        return refs

    def pin(self, run: str) -> None:
        with closing(sqlite3.connect(self.path)) as db, db:
            if db.execute("INSERT OR IGNORE INTO catalog_runs VALUES (?)", (run,)).rowcount:
                db.execute("""
                    WITH RECURSIVE dependencies(root, child) AS (
                        SELECT parent, child FROM recipe_dependencies
                        UNION
                        SELECT d.root, r.child FROM dependencies d
                        JOIN recipe_dependencies r ON r.parent=d.child
                    )
                    INSERT INTO pinned_skills
                    SELECT ?, a.row_id FROM active_skills a WHERE NOT EXISTS (
                        SELECT 1 FROM dependencies d JOIN quarantined_skills q ON q.row_id=d.child
                        WHERE d.root=a.row_id
                    )
                """, (run,))

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

    def confirmed_scope(self, run: str, ref: SkillRef) -> Scope | None:
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute(
                """
                SELECT r.platform, r.component, r.context, r.role
                FROM skill_revisions r JOIN pinned_skills p ON p.row_id=r.row_id
                WHERE p.run_id=? AND r.id=? AND r.revision=?
                """,
                (run, ref.id, ref.revision),
            ).fetchone()
            return Scope(*row) if row else None


    def load_recipe(self, run: str, ref: SkillRef) -> Recipe | None:
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute(
                """
                WITH RECURSIVE available(row_id) AS (
                    SELECT row_id FROM pinned_skills WHERE run_id=?
                    UNION
                    SELECT d.child FROM recipe_dependencies d JOIN available a ON a.row_id=d.parent
                )
                SELECT body FROM skill_recipes recipe
                JOIN skill_revisions r ON r.row_id=recipe.row_id
                JOIN available a ON a.row_id=r.row_id
                WHERE r.id=? AND r.revision=?
                """,
                (run, ref.id, ref.revision),
            ).fetchone()
            return decode_recipe(row[0]) if row else None
