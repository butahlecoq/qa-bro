"""Source scenario and attempt evidence shared by ordinary execution and replay."""

import json
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from hashlib import sha256
from types import MappingProxyType


class Observation(StrEnum):
    MATCH = "observed_match"
    MISMATCH = "observed_mismatch"
    PENDING = "pending"
    UNVERIFIED = "unverified"
    NOT_REACHED = "not_reached"


class Cause(StrEnum):
    PRODUCT = "product"
    AUTOMATION = "automation"
    ENVIRONMENT = "environment"
    UNKNOWN = "unknown"


class Verdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class Checkpoint:
    id: str
    expectation: str
    required: bool = True
    wait_ns: int = 0

    def __post_init__(self):
        if self.wait_ns < 0:
            raise ValueError("Checkpoint wait must be nonnegative")


@dataclass(frozen=True)
class Step:
    id: str
    action: str
    checkpoints: tuple[Checkpoint, ...] = ()


@dataclass(frozen=True)
class Scenario:
    source: str
    steps: tuple[Step, ...]

    def __post_init__(self):
        step_ids = [step.id for step in self.steps]
        checkpoint_ids = [checkpoint.id for checkpoint in self.checkpoints]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("Duplicate step ID")
        if len(checkpoint_ids) != len(set(checkpoint_ids)):
            raise ValueError("Duplicate checkpoint ID")

    @property
    def revision(self) -> str:
        return sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()

    @property
    def source_hash(self) -> str:
        return sha256(self.source.encode()).hexdigest()

    @property
    def checkpoints(self) -> tuple[Checkpoint, ...]:
        return tuple(checkpoint for step in self.steps for checkpoint in step.checkpoints)


@dataclass(frozen=True)
class Attempt:
    scenario: Scenario
    completed_steps: tuple[str, ...]
    observations: Mapping[str, Observation]
    blocked: bool = False
    invalid_evidence: bool = False
    cause: Cause = Cause.UNKNOWN

    def __post_init__(self):
        checkpoint_ids = {checkpoint.id for checkpoint in self.scenario.checkpoints}
        if self.observations.keys() - checkpoint_ids:
            raise ValueError("Evidence refers to a checkpoint outside the scenario")
        object.__setattr__(self, "observations", MappingProxyType(dict(self.observations)))

    @property
    def verdict(self) -> Verdict:
        if self.invalid_evidence:
            return Verdict.INCONCLUSIVE
        if Observation.MISMATCH in self.observations.values():
            return Verdict.FAIL
        if self.blocked:
            return Verdict.BLOCKED
        if self.completed_steps != tuple(step.id for step in self.scenario.steps):
            return Verdict.INCONCLUSIVE
        for checkpoint in self.scenario.checkpoints:
            if checkpoint.required and self.observations.get(checkpoint.id) != Observation.MATCH:
                return Verdict.INCONCLUSIVE
        return Verdict.PASS


def run_verdict(attempts: Iterable[Attempt]) -> Verdict:
    """Use whole attempts and preserve any verified mismatch."""
    attempts = tuple(attempts)
    if attempts and any(attempt.scenario != attempts[0].scenario for attempt in attempts):
        raise ValueError("Run attempts must share the same scenario revision")
    return overall_verdict(tuple(attempt.verdict for attempt in attempts))


def overall_verdict(verdicts: tuple[Verdict, ...]) -> Verdict:
    if Verdict.FAIL in verdicts:
        return Verdict.FAIL
    if Verdict.PASS in verdicts:
        return Verdict.PASS
    return verdicts[-1] if verdicts else Verdict.INCONCLUSIVE
