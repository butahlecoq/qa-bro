"""Compare paired Sakai runs while charging skill acquisition and reuse costs."""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from math import ceil
from statistics import mean, median


from qabro.artifacts import ArtifactStore
from qabro.contract import Observation, Verdict
from qabro.journal import Journal
from qabro.sakai_cases import CREATE_CHECKS


@dataclass(frozen=True)
class SakaiRun:
    seed: int
    setup: str
    verdict: str
    checks: tuple[str, ...]
    tokens: int
    model_calls: int | None
    elapsed_ns: int
    skill_revision: str | None = None
    skill_applied: bool = False
    mcp_calls: int | None = None
    browser_actions: int | None = None
    worker_tool_calls: int | None = None
    browser_ns: int | None = None

    def __post_init__(self):
        if any(type(value) is not int or value < 0 for value in (
            self.tokens, self.elapsed_ns,
        )):
            raise ValueError("Sakai runs require measured nonnegative counters")
        if any(value is not None and (type(value) is not int or value < 0)
               for value in (self.model_calls, self.mcp_calls, self.browser_actions, self.worker_tool_calls)):
            raise ValueError("Call and action counters must be nonnegative integers")
        if self.browser_ns is not None and (
            type(self.browser_ns) is not int or not 0 <= self.browser_ns <= self.elapsed_ns
        ):
            raise ValueError("Browse time must be within the elapsed attempt time")
        if self.skill_applied and not self.skill_revision:
            raise ValueError("An applied skill must identify its frozen revision")


def measured_worker_run(database: Path, attempt: str) -> SakaiRun:
    """Read measured counters and independently verified checks from a worker journal."""
    if not database.is_file():
        raise ValueError("Expected an existing worker journal")
    events = Journal(database).events(attempt)
    entries = {event: payload for _, event, _, payload in events}
    finish = entries["scenario:finish"]
    metadata = entries["sakai:worker"]
    usage = entries["sakai:usage"]
    setup = {
        key: metadata[key]
        for key in ("model", "target_url", "budgets", "browser_schema_sha256", "scenario_sha256")
    }
    if finish.get("case") != "SAKAI-02":
        raise ValueError("Expected a SAKAI-02 worker attempt")
    verdict = Verdict(finish["verdict"])
    store = ArtifactStore(database)
    checks = tuple(
        payload["step"] for _, _, kind, payload in events
        if kind == "checkpoint" and payload.get("step") in CREATE_CHECKS
        and payload.get("outcome") == Observation.MATCH and payload.get("artifact_id")
        and store.get(payload["artifact_id"]) is not None
    )
    if verdict is Verdict.PASS and checks != CREATE_CHECKS:
        verdict = Verdict.INCONCLUSIVE
    durations = [
        entries.get(event.removesuffix(":start") + ":finish", {}).get("elapsed_ns")
        for _, event, kind, _ in events if kind == "tool_start"
    ]
    browser_ns = sum(durations) if durations and all(
        type(duration) is int and duration >= 0 for duration in durations
    ) else None
    return SakaiRun(
        metadata["seed"], sha256(json.dumps(setup, sort_keys=True).encode()).hexdigest(),
        verdict, checks, usage["tokens"], usage["model_calls"], usage["elapsed_ns"],
        metadata.get("skill_sha256"), metadata.get("skill_applied") is True,
        usage.get("mcp_calls"), usage.get("browser_actions"), usage.get("worker_tool_calls"), browser_ns,
    )


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
            "model_calls_saved": (baseline.model_calls - assisted.model_calls
                                  if baseline.model_calls is not None and assisted.model_calls is not None else None),
            "elapsed_ns_saved": baseline.elapsed_ns - assisted.elapsed_ns,
        })
    reuses = [row for row in rows if row["both_pass"] and row["skill_applied"]]
    saved_per_reuse = mean(row["tokens_saved"] for row in reuses) if reuses else None
    investment = sum(learning.values())
    return {
        "pairs": rows, "both_pass": sum(row["both_pass"] for row in rows),
        "verified_reuses": len(reuses),
        "assisted_pass_without_reuse": sum(
            pair[1].verdict == "PASS" and required_checks <= set(pair[1].checks) and not pair[1].skill_applied
            for pair in pairs
        ),
        "learning_tokens": learning,
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


def _performance_table(pairs: list[dict]) -> list[str]:
    lines = [
        "| Metric | Without skill | Skill available | Saved |",
        "| --- | ---: | ---: | ---: |",
    ]
    for label, key, scale in (
        ("Elapsed time (s)", "elapsed_ns", 1_000_000_000),
        ("Time inside browse calls (s)", "browser_ns", 1_000_000_000),
        ("LLM calls", "model_calls", 1),
        ("Tokens", "tokens", 1),
        ("Worker tool calls", "worker_tool_calls", 1),
        ("MCP calls", "mcp_calls", 1),
        ("Browser actions", "browser_actions", 1),
    ):
        totals = []
        for mode in ("baseline", "assisted"):
            values = [row[mode].get(key) for row in pairs]
            totals.append(sum(values) if values and None not in values else None)
        baseline, assisted = totals
        saved = baseline - assisted if baseline is not None and assisted is not None else None
        cells = [
            "—" if value is None else str(value) if scale == 1 else f"{value / scale:.3f}"
            for value in (*totals, saved)
        ]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return lines


def markdown_report(report: dict) -> str:
    estimate = report["estimated_reuses_to_break_even"]
    learning = report["learning_tokens"]
    lines = [
        "# Sakai skill comparison", "",
        f"Verified skill reuses: {report['verified_reuses']} of {len(report['pairs'])} pairs.",
        f"Pairs with all checks passing in both modes: {report['both_pass']}.",
        f"Assisted passes without using the skill: {report.get('assisted_pass_without_reuse', 0)}.",
        f"Learning tokens: {sum(learning.values())} "
        f"({learning['training']} training, {learning['extraction']} extraction, {learning['validation']} validation).",
        f"Net tokens saved across all pairs after learning: {report['observed_net_tokens_saved']}.",
        f"Estimated reuses to break even: {estimate if estimate is not None else 'unavailable'}.", "",
        "Elapsed time for matched pairs with all required checks passing.", "",
        "| Mode | Runs | Median (s) | Range (s) |",
        "| --- | ---: | ---: | --- |",
    ]
    matched = [row for row in report["pairs"] if row["both_pass"]]
    medians = {}
    for mode in ("baseline", "assisted"):
        seconds = [row[mode]["elapsed_ns"] / 1_000_000_000 for row in matched]
        if seconds:
            medians[mode] = median(seconds)
            lines.append(f"| {mode} | {len(seconds)} | {medians[mode]:.3f} | {min(seconds):.3f}–{max(seconds):.3f} |")
        else:
            lines.append(f"| {mode} | 0 | — | — |")
    if medians.get("assisted") and medians.get("baseline"):
        lines.extend(["", f"Observed median speed ratio (baseline / assisted): {medians['baseline'] / medians['assisted']:.2f}×."])
    lines.extend(["", "Performance totals for all measured attempts.", ""])
    lines.extend(_performance_table(report["pairs"]))
    lines.extend(["", "Performance totals for pairs that passed all required checks and used the skill.", ""])
    lines.extend(_performance_table([row for row in matched if row["skill_applied"]]))
    lines.extend([
        "", "All measurement pairs", "",
        "| Seed | Mode | Verdict | Checks passed | Skill used | Seconds | Tokens | LLM calls | Worker calls | MCP calls | Browser actions |",
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ])
    for row in report["pairs"]:
        for mode in ("baseline", "assisted"):
            run = row[mode]
            cells = [
                row["seed"], mode, run["verdict"], ", ".join(run["checks"]) or "—",
                "yes" if run["skill_applied"] else "no",
                f"{run['elapsed_ns'] / 1_000_000_000:.3f}", run["tokens"], run["model_calls"],
                run.get("worker_tool_calls"), run.get("mcp_calls"), run.get("browser_actions"),
            ]
            lines.append("| " + " | ".join("—" if cell is None else str(cell) for cell in cells) + " |")
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
