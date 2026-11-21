"""Evaluate observations against a fixed checkpoint window."""

from dataclasses import dataclass

from qabro.contract import Checkpoint, Observation


@dataclass(frozen=True)
class Evidence:
    observed_ns: int
    artifact_id: str
    matches: bool | None

    def __post_init__(self):
        if not self.artifact_id:
            raise ValueError("An observation requires an evidence reference")


@dataclass(frozen=True)
class CheckWindow:
    checkpoint: Checkpoint
    opened_ns: int

    def evaluate(self, evidence: Evidence | None, *, now_ns: int) -> Observation:
        if now_ns < self.opened_ns:
            raise ValueError("Cannot evaluate before opening the check window")
        if evidence is not None and not self.opened_ns <= evidence.observed_ns <= now_ns:
            raise ValueError("Evidence must be observed during this check")

        deadline = self.opened_ns + self.checkpoint.wait_ns
        if self.checkpoint.wait_ns == 0:
            return self._result(evidence)
        if evidence is not None and evidence.observed_ns <= deadline and evidence.matches is True:
            return Observation.MATCH
        if now_ns < deadline:
            return Observation.PENDING
        if evidence is not None and evidence.observed_ns <= deadline:
            return self._result(evidence)
        return Observation.UNVERIFIED

    @staticmethod
    def _result(evidence: Evidence | None) -> Observation:
        if evidence is None or evidence.matches is None:
            return Observation.UNVERIFIED
        return Observation.MATCH if evidence.matches else Observation.MISMATCH
