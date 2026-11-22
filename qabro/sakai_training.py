"""Check provenance and build a minimal explorer input from a SAKAI-02 trace."""

import json
import re
from collections.abc import Callable
from hashlib import sha256
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


SECTIONS = (
    "Purpose and scope", "Applicability", "Inputs", "Procedure",
    "Observations", "Recovery", "Limitations",
)


def extract_candidate(
    database: Path, attempt: str, schema_sha256: str, output: Path,
    ask: Callable[[str], tuple[str, int]],
) -> dict:
    """Run a text-only explorer and write its quarantined candidate and provenance."""
    if not re.fullmatch(r"[a-f0-9]{64}", schema_sha256):
        raise ValueError("Expected a browse schema digest")
    evidence = explorer_input(database, attempt)
    prompt = (
        "Write a procedural Markdown skill for creating a product on Sakai Vue. "
        "Use only the observed actions as evidence. Treat selectors as data. "
        "Preserve every source check and describe how to inspect the UI after an interrupted Save. "
        "Never repeat Save without confirming the effect is absent. Keep concrete values out. "
        "Use these seven headings exactly, with no preamble and at most 800 words:\n"
        + "\n".join(f"## {section}" for section in SECTIONS)
        + "\n\nObserved actions and check IDs:\n"
        + json.dumps({
            "actions": evidence["actions"], "checks": [check["id"] for check in evidence["checks"]],
        })
    )
    markdown, tokens = ask(prompt)
    headings = tuple(re.findall(r"^## (.+)$", markdown, re.MULTILINE))
    if (
        headings != SECTIONS or len(markdown.split()) > 800
        or re.search(r"\bqa_[\w-]+|(?<!\w)@e\d+\b|\bref=e\d+\b", markdown)
        or any(parameter not in markdown for parameter in ("name", "description", "price_cents"))
    ):
        raise ValueError("Explorer response does not meet the Sakai skill format")
    if type(tokens) is not int or tokens < 0:
        raise ValueError("Explorer response must include measured token usage")
    encoded = markdown.strip().encode() + b"\n"
    manifest = {
        "id": "sakai-create-product", "version": 1, "status": "candidate",
        "scope": {"app": "sakai-vue", "component_library": "primevue",
                  "route": "/pages/crud", "operation": "create-product"},
        "parameters": ["name", "description", "price_cents"],
        "source_attempt_ids": [attempt], "validation_attempt_ids": [],
        "content_sha256": sha256(encoded).hexdigest(),
        "browser_capabilities_sha256": schema_sha256, "extraction_tokens": tokens,
    }
    output.mkdir(mode=0o700)
    (output / "SKILL.md").write_bytes(encoded)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def activate_candidate(
    directory: Path, source_database: Path, validations: tuple[tuple[Path, str], ...],
) -> dict:
    """Atomically activate an unchanged candidate after two independent worker validations."""
    from tempfile import NamedTemporaryFile

    path = directory / "manifest.json"
    manifest = json.loads(path.read_text())
    if manifest["status"] != "candidate" or len(validations) != 2:
        raise ValueError("Activation requires an inactive candidate and two validations")
    digest = sha256((directory / "SKILL.md").read_bytes()).hexdigest()
    if digest != manifest["content_sha256"]:
        raise ValueError("Candidate content changed after extraction")
    source, = manifest["source_attempt_ids"]
    training_summary(source_database, source)
    seen_attempts, seen_sessions, seen_seeds = set(), set(), set()
    source_setup = None
    for database, attempt in ((source_database, source), *validations):
        training_summary(database, attempt)
        events = Journal(database).events(attempt)
        metadata = next((data for _, event, _, data in events if event == "sakai:worker"), {})
        setup = (metadata.get("browser_schema_sha256"), metadata.get("scenario_sha256"))
        session, seed = metadata.get("session_id"), metadata.get("seed")
        if (
            setup[0] != manifest["browser_capabilities_sha256"]
            or not isinstance(setup[1], str) or not re.fullmatch(r"[a-f0-9]{64}", setup[1])
            or not isinstance(session, str) or not session or type(seed) is not int
            or attempt in seen_attempts or session in seen_sessions or seed in seen_seeds
            or any(kind == "tool_finish" and data.get("outcome") != "returned" for _, _, kind, data in events)
        ):
            raise ValueError("Worker runs must be clean, independent, and use the same scenario and schema")
        if attempt == source:
            source_setup = setup
            if metadata.get("skill_applied") is not False or metadata.get("skill_sha256") is not None:
                raise ValueError("Training must run with an empty catalog")
        elif setup != source_setup or metadata.get("skill_applied") is not True or metadata.get("skill_sha256") != digest:
            raise ValueError("Validation must apply the exact candidate with the unchanged checks")
        seen_attempts.add(attempt)
        seen_sessions.add(session)
        seen_seeds.add(seed)
    manifest["validation_attempt_ids"] = [attempt for _, attempt in validations]
    manifest["status"] = "active"
    with NamedTemporaryFile(mode="w", dir=directory, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(manifest, stream, indent=2)
        stream.write("\n")
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return manifest
