"""Select recent experience worth examining for reusable UI knowledge."""

import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass
from hashlib import sha256
from time import time_ns

from qabro.catalog import Catalog, Scope
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


def scan_experience(journal: Journal, queue: JobQueue) -> list[str]:
    episodes = []
    for attempt, payload in journal.events_of_kind("experience_episode"):
        scope = Scope(**payload.pop("scope"))
        episodes.append(Episode(scope=scope, attempt_id=attempt, **payload))
    return queue_exploration(queue, episodes)


def queue_exploration(queue: JobQueue, episodes: list[Episode]) -> list[str]:
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
    draft = synthesize(job)
    if draft is None:
        return queue.complete(job, {"status": "no_candidate"}, now_ns=clock())
    if not draft.summary.strip() or not draft.hint.strip() or not draft.variants:
        raise ValueError("A candidate requires a summary, hint and claimed variants")
    if min(draft.model_tokens, draft.browser_ns) < 0:
        raise ValueError("Explorer usage must be nonnegative")
    if catalog is not None and draft.recipe is None and catalog.has_active_hint(
        Scope(**job.payload["scope"]), draft.hint, draft.capabilities,
    ):
        return queue.complete(job, {
            "status": "already_published", "model_tokens": draft.model_tokens, "browser_ns": draft.browser_ns,
        }, now_ns=clock())
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
    return queue.complete(
        job, {"candidate": candidate, "model_tokens": draft.model_tokens, "browser_ns": draft.browser_ns},
        now_ns=clock(),
        finalize=lambda db: queue.enqueue_in(db, candidate, "validate_hint", payload),
    )
