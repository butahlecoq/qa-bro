"""Compare browser backends before enabling compiled execution for a recipe."""

from dataclasses import dataclass
from enum import StrEnum
from statistics import median

from qabro.contract import Verdict


class TrialCase(StrEnum):
    SUCCESS = "success"
    CHECKPOINT_FAILURE = "checkpoint_failure"
    PARTIAL_EFFECT = "partial_effect"


@dataclass(frozen=True)
class TraceEvent:
    step: str
    kind: str
    outcome: str
    evidence: str | None
    deadline_ns: int | None = None


@dataclass(frozen=True)
class BackendRun:
    recipe_fingerprint: str
    events: tuple[TraceEvent, ...]
    verdict: Verdict
    elapsed_ns: int
    complete_trace: bool


@dataclass(frozen=True)
class BackendPair:
    case: TrialCase
    plain: BackendRun
    compiled: BackendRun


def evaluate_backend(pairs: list[BackendPair], *, minimum_saved_ns: int) -> dict:
    """Require every test case to preserve behavior before considering latency savings."""
    if minimum_saved_ns <= 0:
        raise ValueError("The measurable improvement threshold must be positive")
    missing_cases = set(TrialCase) - {pair.case for pair in pairs}
    fingerprints = {
        run.recipe_fingerprint for pair in pairs for run in (pair.plain, pair.compiled)
    }
    mismatches = [
        pair.case for pair in pairs
        if not (pair.plain.complete_trace and pair.compiled.complete_trace)
        or pair.plain.verdict != pair.compiled.verdict
        or pair.plain.events != pair.compiled.events
    ]
    savings = [
        pair.plain.elapsed_ns - pair.compiled.elapsed_ns
        for pair in pairs if pair.case is TrialCase.SUCCESS
    ]
    saved = median(savings) if savings else None
    equivalent = not missing_cases and not mismatches and len(fingerprints) == 1
    return {
        "missing_cases": sorted(missing_cases),
        "mismatches": mismatches,
        "equivalent": equivalent,
        "median_success_ns_saved": saved,
        "decision": "compiled" if equivalent and saved is not None and saved >= minimum_saved_ns else "plain",
    }
