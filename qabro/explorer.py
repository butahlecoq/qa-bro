"""Select recent experience worth examining for reusable UI knowledge."""

import json
from collections import defaultdict
from collections.abc import Callable
from contextlib import closing
from dataclasses import asdict, dataclass
from hashlib import sha256
from time import time_ns
import sqlite3

from qabro.artifacts import ArtifactStore
from qabro.catalog import Catalog, Scope
from qabro.contract import Step
from qabro.jobs import Job, JobQueue
from qabro.journal import Journal
from qabro.recipe_format import encode_recipe
from qabro.runner import Recipe


@dataclass(frozen=True)
class Episode:
    scope: Scope
    operation: str
    attempt_id: str
    evidence_id: str
    model_calls: int
    discovered_behavior: bool = False
    routine_action: bool = False


def record_episode(journal: Journal, episode: Episode) -> None:
    """Persist an agent-reported observation for a completed UI operation."""
    payload = asdict(episode)
    del payload["attempt_id"]
    event = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    journal.append(episode.attempt_id, f"episode:{event}", "experience_episode", payload)


def record_verified_steps(
    journal: Journal, scope: Scope, attempt: str,
    operation_for: Callable[[Step], str | None],
) -> Callable[[Step, str, int], None]:
    """Record approved operation labels from the scenario runner's verified steps."""
    def record(step: Step, evidence_id: str, model_calls: int) -> None:
        operation = operation_for(step)
        if operation is not None:
            record_episode(journal, Episode(scope, operation, attempt, evidence_id, model_calls))
    return record


def scan_experience(journal: Journal, queue: JobQueue) -> list[str]:
    episodes = []
    for attempt, payload in journal.events_of_kind("experience_episode"):
        scope = Scope(**payload.pop("scope"))
        episodes.append(Episode(scope=scope, attempt_id=attempt, **payload))
    return queue_exploration(queue, episodes, retain_evidence=True)


def queue_exploration(
    queue: JobQueue, episodes: list[Episode], *, retain_evidence: bool = False,
) -> list[str]:
    """Group trusted trace metadata without copying tool arguments or page contents."""
    groups: dict[tuple[Scope, str], dict[str, Episode]] = defaultdict(dict)
    for episode in episodes:
        if episode.routine_action or not (episode.model_calls > 1 or episode.discovered_behavior):
            continue
        group = groups[episode.scope, episode.operation]
        previous = group.get(episode.attempt_id)
        if previous is None or (episode.model_calls, episode.evidence_id) > (
            previous.model_calls, previous.evidence_id,
        ):
            group[episode.attempt_id] = episode

    if retain_evidence:
        ArtifactStore(queue.path)
    queued = []
    for (scope, operation), group in groups.items():
        if len(group) < 2:
            continue
        payload = {
            "scope": asdict(scope),
            "operation": operation,
            "sources": [
                {"attempt_id": attempt_id, "evidence_id": episode.evidence_id}
                for attempt_id, episode in sorted(group.items())
            ],
        }
        priority = sum(max(1, episode.model_calls - 1) for episode in group.values())
        identity = json.dumps([payload, priority], sort_keys=True)
        job_id = sha256(identity.encode()).hexdigest()
        if retain_evidence:
            with closing(sqlite3.connect(queue.path)) as db, db:
                queue.enqueue_in(db, job_id, "explore", payload, priority=priority)
                db.executemany("""
                    INSERT OR IGNORE INTO artifact_pins
                    SELECT ?, id FROM artifacts WHERE id=? AND EXISTS (
                        SELECT 1 FROM jobs WHERE id=? AND result IS NULL
                    )
                """, ((f"explore:{job_id}", episode.evidence_id, job_id) for episode in group.values()))
        else:
            queue.enqueue(job_id, "explore", payload, priority=priority)
        queued.append(job_id)
    return queued


@dataclass(frozen=True)
class HintDraft:
    summary: str
    hint: str
    variants: tuple[str, ...]
    variable_inputs: bool
    model_tokens: int
    browser_ns: int
    recipe: Recipe | None = None
    capabilities: frozenset[str] = frozenset()


def explore_next(
    queue: JobQueue,
    synthesize: Callable[[Job], HintDraft | None],
    *,
    clock: Callable[[], int] = time_ns,
    catalog: Catalog | None = None,
) -> bool:
    """Store a synthesis result and enqueue validation in the same transaction."""
    job = queue.claim("explore", now_ns=clock(), lease_ns=60_000_000_000)
    if job is None:
        return False
    ArtifactStore(queue.path)

    def release(db: sqlite3.Connection) -> None:
        db.execute("DELETE FROM artifact_pins WHERE owner=?", (f"explore:{job.id}",))

    draft = synthesize(job)
    if draft is None:
        return queue.complete(job, {"status": "no_candidate"}, now_ns=clock(), finalize=release)
    if not draft.summary.strip() or not draft.hint.strip() or not draft.variants:
        raise ValueError("A candidate requires a summary, hint and claimed variants")
    if min(draft.model_tokens, draft.browser_ns) < 0:
        raise ValueError("Explorer usage must be nonnegative")
    if catalog is not None and draft.recipe is None and catalog.has_active_hint(
        Scope(**job.payload["scope"]), draft.hint, draft.capabilities,
    ):
        return queue.complete(job, {
            "status": "already_published", "model_tokens": draft.model_tokens, "browser_ns": draft.browser_ns,
        }, now_ns=clock(), finalize=release)
    payload = {
        "scope": job.payload["scope"],
        "operation": job.payload["operation"],
        "sources": job.payload["sources"],
        "summary": draft.summary,
        "hint": draft.hint,
        "variants": sorted(set(draft.variants)),
        "variable_inputs": draft.variable_inputs,
    }
    if draft.recipe is not None:
        payload["recipe"] = encode_recipe(draft.recipe)
    payload["capabilities"] = sorted(draft.capabilities)
    candidate = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    def enqueue_validation(db: sqlite3.Connection) -> None:
        queue.enqueue_in(db, candidate, "validate_hint", payload)
        release(db)

    return queue.complete(
        job, {"candidate": candidate, "model_tokens": draft.model_tokens, "browser_ns": draft.browser_ns},
        now_ns=clock(),
        finalize=enqueue_validation,
    )


def explore_recorded(
    catalog: Catalog,
    synthesize: Callable[[Job, tuple[bytes, ...]], HintDraft | None],
    *,
    clock: Callable[[], int] = time_ns,
) -> bool:
    """Supply synthesis with redacted artifacts linked to their source attempts."""
    journal = Journal(catalog.path)
    store = ArtifactStore(catalog.path)

    def prepare(job: Job) -> HintDraft | None:
        evidence = []
        for source in job.payload["sources"]:
            artifact_id = source["evidence_id"]
            linked = any(
                kind in {"tool_finish", "checkpoint"} and payload.get("artifact_id") == artifact_id
                for _, _, kind, payload in journal.events(source["attempt_id"])
            )
            content = store.get(artifact_id) if linked else None
            if content is None:
                return None
            evidence.append(content)
        return synthesize(job, tuple(evidence))

    return explore_next(catalog.jobs, prepare, clock=clock, catalog=catalog)
