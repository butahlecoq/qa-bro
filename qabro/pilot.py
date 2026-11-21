"""Compare matched held-out QA runs against known verdicts."""

from dataclasses import dataclass
from enum import StrEnum
from math import ceil
from statistics import median

from qabro.contract import Verdict


class Mode(StrEnum):
    BASELINE = "baseline"
    INSTRUCTIONS = "instructions"
    RECIPES = "recipes"
    HYBRID = "hybrid"


@dataclass(frozen=True)
class Case:
    id: str
    workflow: str
    expected: Verdict

    def __post_init__(self):
        if self.expected not in (Verdict.PASS, Verdict.FAIL):
            raise ValueError("Pilot cases need a known PASS or FAIL")


@dataclass(frozen=True)
class Trial:
    case: Case
    mode: Mode
    setup: str
    verdict: Verdict
    elapsed_ns: int
    worker_tokens: int


@dataclass(frozen=True)
class LearningCost:
    explorer_tokens: int = 0
    validation_tokens: int = 0


def frozen_catalog_report(
    trials: list[Trial], training_workflows: frozenset[str], learning: dict[Mode, LearningCost],
) -> dict[Mode, dict]:
    """Require the same cases and environment configuration in every mode."""
    groups = {mode: {} for mode in Mode}
    for trial in trials:
        if trial.case.workflow in training_workflows:
            raise ValueError(f"Training workflow leaked into evaluation: {trial.case.workflow}")
        group = groups[trial.mode]
        if trial.case.id in group:
            raise ValueError(f"Duplicate trial for {trial.mode}: {trial.case.id}")
        group[trial.case.id] = trial
    baseline = groups[Mode.BASELINE]
    if not baseline:
        raise ValueError("No baseline cases")
    report = {}
    for mode, group in groups.items():
        if group.keys() != baseline.keys() or any(
            (trial.case, trial.setup) != (baseline[key].case, baseline[key].setup)
            for key, trial in group.items()
        ):
            raise ValueError(f"Unmatched cases or setup for {mode}")
        samples = list(group.values())
        latency = sorted(trial.elapsed_ns for trial in samples)
        cost = learning.get(mode, LearningCost())
        worker = sum(trial.worker_tokens for trial in samples)
        defects = [trial for trial in samples if trial.case.expected is Verdict.FAIL]
        report[mode] = {
            "trials": len(samples),
            "false_pass": sum(trial.verdict is Verdict.PASS for trial in defects),
            "false_fail": sum(
                trial.verdict is Verdict.FAIL and trial.case.expected is Verdict.PASS for trial in samples
            ),
            "inconclusive_rate": sum(trial.verdict is Verdict.INCONCLUSIVE for trial in samples) / len(samples),
            "blocked": sum(trial.verdict is Verdict.BLOCKED for trial in samples),
            "controlled_defects": len(defects),
            "detected_defects": sum(trial.verdict is Verdict.FAIL for trial in defects),
            "p50_ns": median(latency),
            "p95_ns": latency[ceil(.95 * len(latency)) - 1],
            "worker_tokens": worker,
            "explorer_tokens": cost.explorer_tokens,
            "validation_tokens": cost.validation_tokens,
            "total_tokens": worker + cost.explorer_tokens + cost.validation_tokens,
        }
    return report


@dataclass(frozen=True)
class SkillUse:
    ordinary: Trial
    reuse: Trial

    def __post_init__(self):
        if (self.ordinary.case, self.ordinary.setup) != (self.reuse.case, self.reuse.setup):
            raise ValueError("Skill use must compare the same scenario and setup")
        if self.ordinary.mode is not Mode.BASELINE or self.reuse.mode is Mode.BASELINE:
            raise ValueError("Skill use requires an ordinary baseline and a reuse trial")


def skill_break_even(
    uses: list[SkillUse], cost: LearningCost, *, maintenance_tokens: int = 0,
) -> dict:
    """Report cumulative token savings for ordered, matched uses of one skill."""
    investment = cost.explorer_tokens + cost.validation_tokens + maintenance_tokens
    net = -investment
    first_positive_use = None
    comparable = 0
    incorrect_reuses = 0
    for index, use in enumerate(uses, start=1):
        expected = use.reuse.case.expected
        if use.reuse.verdict is not expected:
            incorrect_reuses += 1
        if use.ordinary.verdict is expected and use.reuse.verdict is expected:
            comparable += 1
            net += use.ordinary.worker_tokens - use.reuse.worker_tokens
        else:
            net -= use.reuse.worker_tokens
        if net > 0 and first_positive_use is None:
            first_positive_use = index
    return {
        "uses": len(uses),
        "comparable_uses": comparable,
        "incorrect_reuses": incorrect_reuses,
        "investment_tokens": investment,
        "net_saved_tokens": net,
        "first_positive_use": first_positive_use,
    }


@dataclass(frozen=True)
class ReleaseEvidence:
    mandatory_condition_ids: frozenset[str]
    reported_condition_ids: frozenset[str]
    duplicate_effects: int | None


def release_report(
    trials: list[Trial],
    training_workflows: frozenset[str],
    learning: dict[Mode, LearningCost],
    evidence: dict[str, ReleaseEvidence],
    *,
    minimum_tokens_saved: int,
) -> dict:
    """Evaluate the initial release against a preselected total token savings target."""
    if minimum_tokens_saved <= 0:
        raise ValueError("The minimum measurable improvement must be positive")
    metrics = frozen_catalog_report(trials, training_workflows, learning)
    baseline = {trial.case.id: trial for trial in trials if trial.mode is Mode.BASELINE}
    hybrid = [trial for trial in trials if trial.mode is Mode.HYBRID]
    new_false_passes = [
        trial.case.id for trial in hybrid
        if trial.case.expected is Verdict.FAIL and trial.verdict is Verdict.PASS
        and baseline[trial.case.id].verdict is not Verdict.PASS
    ]
    missing_checks = []
    duplicate_effects = []
    for trial in hybrid:
        case_id = trial.case.id
        proof = evidence.get(case_id)
        if proof is None or not proof.mandatory_condition_ids <= proof.reported_condition_ids:
            missing_checks.append(case_id)
        if proof is None or proof.duplicate_effects != 0:
            duplicate_effects.append(case_id)

    saved = metrics[Mode.BASELINE]["total_tokens"] - metrics[Mode.HYBRID]["total_tokens"]
    includes_controlled_defects = metrics[Mode.BASELINE]["controlled_defects"] > 0
    return {
        "new_false_pass_cases": new_false_passes,
        "missing_check_results": missing_checks,
        "duplicate_or_unverified_effect_cases": duplicate_effects,
        "includes_controlled_defects": includes_controlled_defects,
        "tokens_saved": saved,
        "minimum_tokens_saved": minimum_tokens_saved,
        "ready": includes_controlled_defects and saved >= minimum_tokens_saved
        and not (new_false_passes or missing_checks or duplicate_effects),
    }


@dataclass(frozen=True)
class OnlineAttempt:
    attempt_id: str
    trial: Trial
    available_revisions: tuple[tuple[str, str], ...]
    learning_since_previous: LearningCost


def online_learning_report(
    attempts: list[OnlineAttempt], *, final_learning: LearningCost = LearningCost(),
) -> dict:
    """Report online results in execution order, including work after the last attempt."""
    rows = []
    seen = set()
    explorer_tokens = validation_tokens = worker_tokens = 0
    for attempt in attempts:
        if attempt.attempt_id in seen:
            raise ValueError(f"Duplicate online attempt: {attempt.attempt_id}")
        seen.add(attempt.attempt_id)
        explorer_tokens += attempt.learning_since_previous.explorer_tokens
        validation_tokens += attempt.learning_since_previous.validation_tokens
        worker_tokens += attempt.trial.worker_tokens
        rows.append({
            "attempt_id": attempt.attempt_id,
            "case_id": attempt.trial.case.id,
            "available_revisions": [list(ref) for ref in attempt.available_revisions],
            "verdict": attempt.trial.verdict,
            "expected": attempt.trial.case.expected,
            "elapsed_ns": attempt.trial.elapsed_ns,
            "cumulative_tokens": worker_tokens + explorer_tokens + validation_tokens,
        })

    explorer_tokens += final_learning.explorer_tokens
    validation_tokens += final_learning.validation_tokens
    return {
        "attempts": rows,
        "worker_tokens": worker_tokens,
        "explorer_tokens": explorer_tokens,
        "validation_tokens": validation_tokens,
        "total_tokens": worker_tokens + explorer_tokens + validation_tokens,
    }
