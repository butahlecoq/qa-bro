"""Check provenance and build a minimal explorer input from a SAKAI-02 trace."""

import re
from pathlib import Path

from qabro.artifacts import ArtifactStore
from qabro.contract import Observation, Verdict
from qabro.journal import Journal
from qabro.sakai_cases import CREATE_CHECKS


def training_summary(database: Path, attempt: str) -> dict:
    if not database.is_file():
        raise ValueError("Expected an existing Sakai evidence database")
    events = Journal(database).events(attempt)
    store = ArtifactStore(database)
    finish = next((data for _, event, _, data in events if event == "scenario:finish"), {})
    if finish.get("case") != "SAKAI-02" or finish.get("verdict") != Verdict.PASS:
        raise ValueError("Extraction requires a passing SAKAI-02 attempt")
    required = set(CREATE_CHECKS)
    checkpoints = [
        data for _, _, kind, data in events if kind == "checkpoint" and data.get("step") in required
    ]
    if tuple(data["step"] for data in checkpoints) != CREATE_CHECKS:
        raise ValueError("Training checks are missing, repeated, or out of order")
    for data in checkpoints:
        ref = data.get("artifact_id")
        if data.get("outcome") != Observation.MATCH or not ref or store.get(ref) is None:
            raise ValueError(f"Training check has no verified artifact: {data['step']}")
    return {
        "case": "SAKAI-02",
        "attempt": attempt,
        "checks": [{"id": data["step"], "artifact_id": data["artifact_id"]} for data in checkpoints],
    }


def explorer_input(database: Path, attempt: str) -> dict:
    """Extract the observed creation actions without copying raw page content."""
    evidence = training_summary(database, attempt)
    events = Journal(database).events(attempt)
    results = {event: data for _, event, kind, data in events if kind == "tool_finish"}
    selectors = re.compile(r'^[A-Za-z0-9_# .\[\]=":()<>-]{1,160}$')
    fields = {"name": "name", "description": "description", "price": "price_cents"}
    expected = {"new": "click", **dict.fromkeys(fields, "fill"), "save": "click"}
    actions = []
    for _, event, kind, data in events:
        if kind != "tool_start" or data.get("step") not in expected:
            continue
        step = data["step"]
        result = results.get(event.removesuffix(":start") + ":finish", {})
        selector = data.get("arguments", {}).get("selector")
        if (
            data.get("tool") != expected[step]
            or result.get("outcome") != "returned"
            or not isinstance(selector, str) or not selectors.fullmatch(selector)
            or re.search(r"\b(?:ref=e|qa_)", selector)
        ):
            raise ValueError(f"Cannot derive a reusable observed action for {step}")
        action = {"step": step, "tool": data["tool"], "selector": selector}
        if step in fields:
            action["parameter"] = fields[step]
        actions.append(action)
    if tuple(action["step"] for action in actions) != tuple(expected):
        raise ValueError("Training trace does not contain the ordered creation actions")
    return {**evidence, "actions": actions}
