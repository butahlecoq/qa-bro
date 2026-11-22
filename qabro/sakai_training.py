"""Check provenance and build a minimal explorer input from a SAKAI-02 trace."""

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
