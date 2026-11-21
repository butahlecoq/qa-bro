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
    if type(minimum_saved_ns) is not int or minimum_saved_ns <= 0:
        raise ValueError("The measurable improvement threshold must be positive")
    missing_cases = set(TrialCase) - {pair.case for pair in pairs}
    fingerprints = {
        run.recipe_fingerprint for pair in pairs for run in (pair.plain, pair.compiled)
    }
    expected_verdicts = {
        TrialCase.SUCCESS: Verdict.PASS, TrialCase.CHECKPOINT_FAILURE: Verdict.FAIL,
    }
    mismatches = [
        pair.case for pair in pairs
        if not (pair.plain.complete_trace and pair.compiled.complete_trace)
        or not pair.plain.events
        or pair.plain.verdict != pair.compiled.verdict
        or pair.plain.verdict != expected_verdicts.get(pair.case, pair.plain.verdict)
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


def _read_backend_run(row: dict) -> BackendRun:
    if type(row["complete_trace"]) is not bool or type(row["elapsed_ns"]) is not int or row["elapsed_ns"] < 0:
        raise ValueError("A backend run requires a boolean trace status and nonnegative measured latency")
    return BackendRun(
        row["recipe_fingerprint"], tuple(TraceEvent(**event) for event in row["events"]),
        Verdict(row["verdict"]), row["elapsed_ns"], row["complete_trace"],
    )


def evaluate_manifest(data: dict) -> dict:
    """Evaluate the paired runs for the exact recipe selected from the pilot."""
    selected = data["recipe_fingerprint"]
    if not isinstance(selected, str) or not selected:
        raise ValueError("The pilot must identify the selected recipe fingerprint")
    pairs = [
        BackendPair(TrialCase(row["case"]), _read_backend_run(row["plain"]), _read_backend_run(row["compiled"]))
        for row in data["pairs"]
    ]
    if any(run.recipe_fingerprint != selected for pair in pairs for run in (pair.plain, pair.compiled)):
        raise ValueError("Backend trials must use the recipe selected from the pilot")
    result = evaluate_backend(pairs, minimum_saved_ns=data["minimum_saved_ns"])
    fingerprints = data["validated_recipe_fingerprints"]
    if not isinstance(fingerprints, list) or not all(isinstance(item, str) for item in fingerprints):
        raise ValueError("Validated recipe fingerprints must be a list")
    validated = selected in fingerprints
    return {
        **result,
        "recipe_fingerprint": selected,
        "validated": validated,
        "decision": result["decision"] if validated else "plain",
    }


if __name__ == "__main__":
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        report = evaluate_manifest(json.loads(args.manifest.read_text()))
    except (OSError, KeyError, TypeError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2, allow_nan=False))
