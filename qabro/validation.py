"""Apply validation evidence requirements before publishing a skill hint."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from sqlite3 import Connection
from time import time_ns

from qabro.artifacts import ArtifactStore
from qabro.catalog import Catalog, Scope, SkillRef
from qabro.contract import Attempt, Observation, Verdict
from qabro.jobs import Job
from qabro.journal import Journal
from qabro.recipe_format import decode_recipe
from qabro.runner import Recipe


@dataclass(frozen=True)
class HintCandidate:
    ref: SkillRef
    scope: Scope
    hint: str
    variants: frozenset[str]
    variable_inputs: bool
    capabilities: frozenset[str] = frozenset()
    recipe: Recipe | None = None

    def __post_init__(self):
        if not self.variants or not self.hint.strip():
            raise ValueError("A hint requires text and at least one claimed variant")


@dataclass(frozen=True)
class ValidationRun:
    candidate: SkillRef
    scope: Scope
    session_id: str
    setup_id: str
    dataset_id: str
    variant: str
    result: Attempt
    evidence: tuple[tuple[str, str], ...] = ()
    attempt_id: str | None = None


@dataclass(frozen=True)
class DefectTrial:
    plain_attempt: str
    recipe_attempt: str


def eligible(candidate: HintCandidate, runs: tuple[ValidationRun, ...]) -> bool:
    if len(runs) < 3:
        return False
    if any(
        run.candidate != candidate.ref
        or run.scope != candidate.scope
        or not all((run.session_id, run.setup_id, run.dataset_id))
        or run.result.verdict is not Verdict.PASS
        or not any(check.required for check in run.result.scenario.checkpoints)
        for run in runs
    ):
        return False
    if len({run.session_id for run in runs}) != len(runs):
        return False
    if len({run.setup_id for run in runs}) != len(runs):
        return False
    if {run.variant for run in runs} != candidate.variants:
        return False
    if candidate.variable_inputs and len({run.dataset_id for run in runs}) < 2:
        return False
    return True


def publish_hint(
    catalog: Catalog, candidate: HintCandidate, runs: tuple[ValidationRun, ...]
) -> bool:
    if not eligible(candidate, runs):
        return False
    if candidate.recipe is not None:
        raise ValueError("Recipe publication requires persisted validation evidence")
    catalog.seed_verified_hint(
        candidate.ref, candidate.scope, candidate.hint, capabilities=candidate.capabilities
    )
    return True


def validate_next_hint(
    catalog: Catalog,
    validate: Callable[[HintCandidate], tuple[ValidationRun, ...]],
    *,
    clock: Callable[[], int] = time_ns,
    defect_trials: Callable[[HintCandidate], tuple[DefectTrial, ...]] | None = None,
) -> bool:
    """Validate a queued draft and commit publication with the job result."""
    queue = catalog.jobs
    job = queue.claim("validate_hint", now_ns=clock(), lease_ns=300_000_000_000)
    if job is None:
        return False
    draft = job.payload
    ref = SkillRef(f"hint:{job.id}", "1", draft["summary"])
    recipe = decode_recipe(draft["recipe"]) if "recipe" in draft else None
    if recipe is not None:
        recipe = replace(recipe, id=ref.id, revision=ref.revision)
    candidate = HintCandidate(
        ref, Scope(**draft["scope"]), draft["hint"], frozenset(draft["variants"]),
        draft["variable_inputs"], frozenset(draft.get("capabilities", ())), recipe,
    )
    trials = defect_trials(candidate) if defect_trials else ()
    return _validate_job(
        catalog, job, candidate, validate, clock, trials,
        require_defect_trial=defect_trials is not None,
    )


def revalidate_next_hint(
    catalog: Catalog,
    prepare: Callable[[SkillRef, Scope], HintCandidate | None],
    validate: Callable[[HintCandidate], tuple[ValidationRun, ...]],
    *,
    clock: Callable[[], int] = time_ns,
) -> bool:
    queue = catalog.jobs
    job = queue.claim("revalidate", now_ns=clock(), lease_ns=300_000_000_000)
    if job is None:
        return False
    source = SkillRef(**job.payload["skill"])
    scope = Scope(**job.payload["scope"])
    candidate = prepare(source, scope)
    if candidate is None:
        return queue.complete(job, {"published": False}, now_ns=clock())
    if candidate.scope != scope or candidate.ref.id != source.id or candidate.ref.revision == source.revision:
        raise ValueError("Revalidation requires a new revision in the quarantined scope")
    return _validate_job(catalog, job, candidate, validate, clock)


def validate_next_transfer(
    catalog: Catalog,
    prepare: Callable[[SkillRef, Scope, Scope], HintCandidate | None],
    validate: Callable[[HintCandidate], tuple[ValidationRun, ...]],
    *,
    clock: Callable[[], int] = time_ns,
) -> bool:
    """Validate a target scope while retaining the original skill's availability."""
    queue = catalog.jobs
    job = queue.claim("validate_transfer", now_ns=clock(), lease_ns=300_000_000_000)
    if job is None:
        return False
    source = SkillRef(**job.payload["skill"])
    source_scope = Scope(**job.payload["source"])
    target = Scope(**job.payload["target"])
    candidate = prepare(source, source_scope, target)
    if candidate is None:
        return queue.complete(job, {"published": False}, now_ns=clock())
    # Each scope has its own active pointer, so publish under a distinct ID.
    if candidate.scope != target or candidate.ref.id == source.id:
        raise ValueError("Transfer requires a distinct skill ID in the target scope")
    return _validate_job(catalog, job, candidate, validate, clock)


def _recipe_step_evidence(selection: str, payload: dict, entries: dict) -> set[str] | None:
    index = int(selection.removeprefix("recipe:"))
    references = set()
    schemas = {
        item["name"]: item["inputSchema"]
        for item in entries.get("browse:schema", {}).get("tools", ())
    }
    for offset, step in enumerate(payload["steps"]):
        action_id = f"step-{index + offset}"
        recorded = entries.get(f"{action_id}:recipe", {})
        if recorded.get("step") != step or recorded.get("action") != action_id or recorded.get("fallback"):
            return None
        dispatched = entries.get(f"{action_id}:start", {})
        schema = schemas.get(dispatched.get("tool"))
        arguments = dispatched.get("arguments")
        if dispatched.get("step") != step or schema is None or not isinstance(arguments, dict):
            return None
        sent = arguments.keys() | {"tab"}
        if not set(schema.get("required", ())) <= sent:
            return None
        if schema.get("additionalProperties") is False and not sent <= schema.get("properties", {}).keys():
            return None
        if entries.get(f"{action_id}:finish", {}).get("outcome") != "returned":
            return None
        probe = payload.get("guard_steps", {}).get(str(offset))
        if probe is not None:
            guard = entries.get(recorded.get("guard_event"), {})
            reference = guard.get("artifact_id")
            if (guard.get("step"), guard.get("probe"), guard.get("passed")) != (step, probe, True):
                return None
            if not isinstance(reference, str) or not reference:
                return None
            references.add(reference)
    return references if payload["steps"] else None


def _recipe_branch_outcomes(selection: str, payload: dict, entries: dict) -> dict[int, bool | None]:
    index = int(selection.removeprefix("recipe:"))
    outcomes = {}
    for offset in payload.get("branch_steps", ()):
        action = f"step-{index + offset}"
        branch = entries.get(f"{action}:recipe", {}).get("branch_event", f"{action}:branch")
        outcomes[offset] = entries.get(branch, {}).get("outcome")
    return outcomes


def _defect_evidence(
    journal: Journal, trial: DefectTrial, recipe: Recipe | None,
) -> set[str] | None:
    if trial.plain_attempt == trial.recipe_attempt or recipe is None:
        return None
    traces = [journal.events(attempt) for attempt in (trial.plain_attempt, trial.recipe_attempt)]
    entries = [{event: payload for _, event, _, payload in trace} for trace in traces]
    plain, replay = entries
    revision = plain.get("scenario:start", {}).get("contract_revision")
    if not revision or replay.get("scenario:start", {}).get("contract_revision") != revision:
        return None
    if any(events.get("scenario:finish", {}).get("verdict") != Verdict.FAIL for events in entries):
        return None
    if any(kind == "recipe_selected" for _, _, kind, _ in traces[0]):
        return None
    if not any(
        kind == "recipe_selected" and payload.get("fingerprint") == recipe.fingerprint
        for _, _, kind, payload in traces[1]
    ) or not any(
        kind == "recipe_action" and not payload.get("fallback")
        and replay.get(f"{payload.get('action')}:finish", {}).get("outcome") == "returned"
        for _, _, kind, payload in traces[1]
    ):
        return None
    mismatches = [
        {event: payload.get("artifact_id") for _, event, kind, payload in trace
         if kind == "checkpoint" and payload.get("outcome") == Observation.MISMATCH}
        for trace in traces
    ]
    if not mismatches[0] or mismatches[0].keys() != mismatches[1].keys():
        return None
    references = set(mismatches[0].values()) | set(mismatches[1].values())
    return references if all(isinstance(ref, str) and ref for ref in references) else None


def _validate_job(
    catalog: Catalog, job: Job, candidate: HintCandidate,
    validate: Callable[[HintCandidate], tuple[ValidationRun, ...]],
    clock: Callable[[], int],
    trials: tuple[DefectTrial, ...] = (),
    *,
    require_defect_trial: bool = False,
) -> bool:
    runs = validate(candidate)
    store = ArtifactStore(catalog.path)
    journal = Journal(catalog.path)
    references = set()
    branches = {}
    accepted = eligible(candidate, runs) and (bool(trials) or not require_defect_trial)
    for trial in trials:
        proof = _defect_evidence(journal, trial, candidate.recipe)
        if proof is None:
            accepted = False
        else:
            references.update(proof)
    if len({run.attempt_id for run in runs}) != len(runs):
        accepted = False
    for run in runs:
        events = journal.events(run.attempt_id) if run.attempt_id else []
        entries = {event: payload for _, event, _, payload in events}
        entries.update({
            f"{payload['action']}:recipe": payload
            for _, _, kind, payload in events if kind == "recipe_action"
        })
        if candidate.recipe is not None:
            selections = [
                (event, payload) for _, event, kind, payload in events
                if kind == "recipe_selected"
                and (payload["id"], payload["revision"]) == (candidate.ref.id, candidate.ref.revision)
                and payload.get("fingerprint") == candidate.recipe.fingerprint
            ]
            if not selections:
                accepted = False
            for event, payload in selections:
                step_evidence = _recipe_step_evidence(event, payload, entries)
                if step_evidence is None:
                    accepted = False
                else:
                    references.update(step_evidence)
                for offset, outcome in _recipe_branch_outcomes(event, payload, entries).items():
                    branches.setdefault(offset, set()).add(outcome)
        if entries.get("scenario:start", {}).get("contract_revision") != run.result.scenario.revision:
            accepted = False
        if entries.get("scenario:finish", {}).get("verdict") != Verdict.PASS:
            accepted = False
        required = {check.id for check in run.result.scenario.checkpoints if check.required}
        evidence = dict(run.evidence)
        if not required <= evidence.keys():
            accepted = False
        for check in required:
            recorded = entries.get(f"check:{check}", {})
            if recorded.get("outcome") != Observation.MATCH or recorded.get("artifact_id") != evidence.get(check):
                accepted = False
        references.update(evidence.values())
    accepted = accepted and all(outcomes == {True, False} for outcomes in branches.values())
    accepted = accepted and all(store.get(ref) is not None for ref in references)

    def finalize(db: Connection) -> None:
        owner = f"validate:{job.id}"
        if not accepted:
            db.execute("DELETE FROM artifact_pins WHERE owner=?", (owner,))
            return
        skill_owner = f"{candidate.ref.id}:{candidate.ref.revision}"
        db.execute("""
            INSERT OR IGNORE INTO artifact_pins
            SELECT ?, artifact_id FROM artifact_pins WHERE owner=?
        """, (skill_owner, owner))
        db.execute("DELETE FROM artifact_pins WHERE owner=?", (owner,))
        for reference in sorted(references):
            pinned = db.execute(
                """
                INSERT OR IGNORE INTO artifact_pins
                SELECT ?, id FROM artifacts WHERE id=?
                """,
                (skill_owner, reference),
            )
            if pinned.rowcount != 1 and db.execute(
                "SELECT 1 FROM artifact_pins WHERE owner=? AND artifact_id=?", (skill_owner, reference),
            ).fetchone() is None:
                raise ValueError("Validation evidence expired before publication")
        catalog.publish_hint_in(
            db, candidate.ref, candidate.scope, candidate.hint,
            capabilities=candidate.capabilities, recipe=candidate.recipe,
        )

    return catalog.jobs.complete(
        job, {"published": accepted, "sessions": [run.session_id for run in runs],
              "evidence": sorted(references)},
        now_ns=clock(), finalize=finalize,
    )
