"""Verify and summarize a persisted baseline attempt without exporting raw UI evidence."""

import argparse
import json
from pathlib import Path

from qabro.artifacts import ArtifactStore
from qabro.browser import Outcome
from qabro.contract import Observation, Verdict
from qabro.journal import Journal


def baseline_evidence(database: Path, attempt: str) -> dict:
    if not database.is_file():
        raise ValueError("Expected an existing baseline database")
    journal, artifacts = Journal(database), ArtifactStore(database)
    events = journal.events(attempt)
    by_id = {event: payload for _, event, _, payload in events}
    scenario = by_id.get("scenario:start", {})
    schema = by_id.get("browse:schema", {})
    finish = by_id.get("scenario:finish", {})
    usage = by_id.get("baseline:usage", {})
    step_ids = scenario.get("step_ids", ())
    tools = {item["name"] for item in schema.get("tools", ())}
    if not step_ids or not tools or not schema.get("schema_sha256"):
        raise ValueError("Baseline is missing the source steps or browse schema")
    if finish.get("verdict") not in (Verdict.PASS, Verdict.FAIL):
        raise ValueError("Baseline must end with an observed PASS or FAIL")
    if any(kind == "recipe_selected" for _, _, kind, _ in events):
        raise ValueError("Baseline used a recipe")
    counters = ("model_calls", "input_tokens", "output_tokens", "elapsed_ns")
    if any(type(usage.get(key)) is not int or usage[key] < 0 for key in counters):
        raise ValueError("Baseline is missing measured usage")
    calls = []
    executed = []
    for _, event, kind, payload in events:
        if kind != "tool_start":
            continue
        result = by_id.get(event.removesuffix(":start") + ":finish", {})
        if result.get("outcome") != Outcome.RETURNED or not payload.get("tab") or payload.get("tool") not in tools:
            raise ValueError(f"Baseline call has no verified result or tool identity: {event}")
        if not result.get("artifact_id") or artifacts.get(result["artifact_id"]) is None:
            raise ValueError(f"Baseline call has no stored result artifact: {event}")
        calls.append({"step": payload["step"], "tool": payload["tool"], "tab": payload["tab"]})
        if not payload.get("read_only"):
            executed.append(payload["step"])
    if not executed or list(step_ids[:len(executed)]) != executed:
        raise ValueError("Baseline calls do not follow the source step order")
    if finish["verdict"] == Verdict.PASS and executed != list(step_ids):
        raise ValueError("Baseline passed with missing source actions")
    checks = [payload for _, _, kind, payload in events if kind == "checkpoint"]
    if finish["verdict"] == Verdict.FAIL and not any(
        check["outcome"] == Observation.MISMATCH for check in checks
    ):
        raise ValueError("Baseline failed without an observed mismatch")
    for check in checks:
        if check["outcome"] in (Observation.MATCH, Observation.MISMATCH) and (
            not check.get("artifact_id") or artifacts.get(check["artifact_id"]) is None
        ):
            raise ValueError("Baseline is missing observed checkpoint evidence")
    return {
        "attempt": attempt, "contract_revision": scenario["contract_revision"],
        "schema_sha256": schema["schema_sha256"], "verdict": finish["verdict"],
        "browser_calls": len(calls), "calls": calls, "checkpoints": checks,
        **{key: usage[key] for key in counters},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("attempt")
    args = parser.parse_args()
    try:
        print(json.dumps(baseline_evidence(args.database, args.attempt), indent=2))
    except (KeyError, TypeError, ValueError) as error:
        parser.error(str(error))
