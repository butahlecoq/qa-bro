"""Select recent experience worth examining for reusable UI knowledge."""

import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from hashlib import sha256

from qabro.catalog import Scope
from qabro.jobs import JobQueue
from qabro.journal import Journal


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
