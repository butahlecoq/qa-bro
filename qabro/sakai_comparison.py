"""Compare paired Sakai runs while charging skill acquisition and reuse costs."""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
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
    mcp_calls: int | None = None
    browser_actions: int | None = None

    def __post_init__(self):
        if any(type(value) is not int or value < 0 for value in (
            self.tokens, self.model_calls, self.elapsed_ns,
        )):
            raise ValueError("Sakai runs require measured nonnegative counters")
        if any(value is not None and (type(value) is not int or value < 0)
               for value in (self.mcp_calls, self.browser_actions)):
            raise ValueError("Browser activity counters must be nonnegative integers")
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
            "baseline": asdict(baseline), "assisted": asdict(assisted),
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
        "verified_net_tokens_saved": sum(
            row["tokens_saved"] if row["both_pass"] and row["skill_applied"] else -row["assisted"]["tokens"]
            for row in rows
        ) - investment,
    }

def measure_sakai(
    candidate_directory: Path, measurement_seeds: tuple[int, ...], learning_seeds: frozenset[int],
    run_worker: Callable[[int, Path | None], SakaiRun],
) -> list[tuple[SakaiRun, SakaiRun]]:
    """Run matched measurement pairs in alternating order against one validated skill."""
    if (
        not measurement_seeds or len(set(measurement_seeds)) != len(measurement_seeds)
        or set(measurement_seeds) & learning_seeds
    ):
        raise ValueError("Measurement seeds must be distinct from training and validation seeds")
    manifest = json.loads((candidate_directory / "manifest.json").read_text())
    if manifest.get("status") != "active":
        raise ValueError("Measurement requires an active candidate")
    skill = candidate_directory / "SKILL.md"
    digest = manifest["content_sha256"]

    def check_frozen_skill():
        if sha256(skill.read_bytes()).hexdigest() != digest:
            raise ValueError("The frozen measurement skill changed")

    pairs = []
    for index, seed in enumerate(measurement_seeds):
        pair = {}
        for assisted in ((False, True) if index % 2 == 0 else (True, False)):
            check_frozen_skill()
            run = run_worker(seed, skill if assisted else None)
            check_frozen_skill()
            if run.seed != seed or run.skill_revision != (digest if assisted else None):
                raise ValueError("Worker trace does not match the requested seed and skill")
            pair[assisted] = run
        if pair[False].setup != pair[True].setup:
            raise ValueError("Measurement modes used different configurations")
        pairs.append((pair[False], pair[True]))
    return pairs


def markdown_report(report: dict) -> str:
    estimate = report["estimated_reuses_to_break_even"]
    lines = [
        "# Sakai skill comparison", "",
        f"Verified skill reuses: {report['verified_reuses']} of {len(report['pairs'])} pairs.",
        f"Pairs with all checks passing in both modes: {report['both_pass']}.",
        f"Learning tokens: {sum(report['learning_tokens'].values())}.",
        f"Estimated reuses to break even: {estimate if estimate is not None else 'unavailable'}.", "",
        "Performance totals for pairs that passed all required checks and used the skill.", "",
        "| Metric | Without skill | With skill | Saved |",
        "| --- | ---: | ---: | ---: |",
    ]
    pairs = [row for row in report["pairs"] if row["both_pass"] and row["skill_applied"]]
    for label, key, scale in (
        ("Elapsed time (s)", "elapsed_ns", 1_000_000_000),
        ("LLM calls", "model_calls", 1),
        ("Tokens", "tokens", 1),
        ("MCP calls", "mcp_calls", 1),
        ("Browser actions", "browser_actions", 1),
    ):
        totals = []
        for mode in ("baseline", "assisted"):
            values = [row[mode][key] for row in pairs]
            totals.append(sum(values) if values and None not in values else None)
        baseline, assisted = totals
        saved = baseline - assisted if baseline is not None and assisted is not None else None
        cells = [
            "—" if value is None else str(value) if scale == 1 else f"{value / scale:.3f}"
            for value in (*totals, saved)
        ]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.extend([
        "", "All measurement pairs", "",
        "| Seed | Baseline | Assisted | Skill applied | Baseline tokens | Assisted tokens |",
        "| --- | --- | --- | --- | ---: | ---: |",
    ])
    for row in report["pairs"]:
        baseline, assisted = row["baseline"], row["assisted"]
        lines.append(
            f"| {row['seed']} | {baseline['verdict']} | {assisted['verdict']} | "
            f"{'yes' if row['skill_applied'] else 'no'} | {baseline['tokens']} | {assisted['tokens']} |"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path, help="New directory for the comparison artifacts")
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text())
        report = compare_sakai(
            [(SakaiRun(**pair["baseline"]), SakaiRun(**pair["assisted"])) for pair in manifest["pairs"]],
            frozenset(manifest["required_checks"]), **manifest["learning"],
        )
        args.output.mkdir(mode=0o700)
        (args.output / "comparison.json").write_text(json.dumps(report, indent=2) + "\n")
        (args.output / "report.md").write_text(markdown_report(report))
    except (OSError, KeyError, TypeError, ValueError) as error:
        parser.error(str(error))
