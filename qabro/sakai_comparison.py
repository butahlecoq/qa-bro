"""Compare paired Sakai runs while charging skill acquisition and reuse costs."""

from dataclasses import dataclass
from math import ceil
from statistics import mean


@dataclass(frozen=True)
class SakaiRun:
    seed: int
    setup: str
    verdict: str
    checks: tuple[str, ...]
    tokens: int
    model_calls: int
    elapsed_ns: int
    skill_revision: str | None = None
    skill_applied: bool = False

    def __post_init__(self):
        if any(type(value) is not int or value < 0 for value in (
            self.tokens, self.model_calls, self.elapsed_ns,
        )):
            raise ValueError("Sakai runs require measured nonnegative counters")
        if self.skill_applied and not self.skill_revision:
            raise ValueError("An applied skill must identify its frozen revision")


def compare_sakai(
    pairs: list[tuple[SakaiRun, SakaiRun]], required_checks: frozenset[str], *,
    training_tokens: int, extraction_tokens: int, validation_tokens: int,
) -> dict:
    """Return observed savings and a break-even estimate for successful reuses."""
    learning = {
        "training": training_tokens, "extraction": extraction_tokens, "validation": validation_tokens,
    }
    if not pairs or not required_checks:
        raise ValueError("The comparison requires paired runs and explicit checks")
    if any(type(value) is not int or value < 0 for value in learning.values()):
        raise ValueError("Learning costs must be measured nonnegative integers")
    if len({baseline.seed for baseline, _ in pairs}) != len(pairs):
        raise ValueError("Each pair requires a distinct measurement seed")
    revisions = {assisted.skill_revision for _, assisted in pairs}
    if None in revisions or len(revisions) != 1:
        raise ValueError("Assisted runs must share a frozen skill revision")

    rows = []
    for baseline, assisted in pairs:
        if (baseline.seed, baseline.setup) != (assisted.seed, assisted.setup):
            raise ValueError("Baseline and assisted runs must use matched data and setup")
        if baseline.skill_revision is not None:
            raise ValueError("Baseline must run without a skill")
        both_pass = all(
            run.verdict == "PASS" and required_checks <= set(run.checks)
            for run in (baseline, assisted)
        )
        rows.append({
            "seed": baseline.seed, "baseline_verdict": baseline.verdict,
            "assisted_verdict": assisted.verdict, "both_pass": both_pass,
            "skill_applied": assisted.skill_applied,
            "tokens_saved": baseline.tokens - assisted.tokens,
            "model_calls_saved": baseline.model_calls - assisted.model_calls,
            "elapsed_ns_saved": baseline.elapsed_ns - assisted.elapsed_ns,
        })
    reuses = [row for row in rows if row["both_pass"] and row["skill_applied"]]
    saved_per_reuse = mean(row["tokens_saved"] for row in reuses) if reuses else None
    investment = sum(learning.values())
    return {
        "pairs": rows, "both_pass": sum(row["both_pass"] for row in rows),
        "verified_reuses": len(reuses), "learning_tokens": learning,
        "mean_tokens_saved_per_reuse": saved_per_reuse,
        "estimated_reuses_to_break_even": (
            ceil(investment / saved_per_reuse) if saved_per_reuse and saved_per_reuse > 0 else None
        ),
        "observed_net_tokens_saved": sum(row["tokens_saved"] for row in rows) - investment,
    }
