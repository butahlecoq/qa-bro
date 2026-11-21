"""Apply validation evidence requirements before publishing a skill hint."""

from collections.abc import Callable
from dataclasses import dataclass
from sqlite3 import Connection
from time import time_ns

from qabro.artifacts import ArtifactStore
from qabro.catalog import Catalog, Scope, SkillRef
from qabro.contract import Attempt, Verdict


@dataclass(frozen=True)
class HintCandidate:
    ref: SkillRef
    scope: Scope
    hint: str
    variants: frozenset[str]
    variable_inputs: bool
    capabilities: frozenset[str] = frozenset()

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
    catalog.seed_verified_hint(
        candidate.ref, candidate.scope, candidate.hint, capabilities=candidate.capabilities
    )
    return True


def validate_next_hint(
    catalog: Catalog,
    validate: Callable[[HintCandidate], tuple[ValidationRun, ...]],
    *,
    clock: Callable[[], int] = time_ns,
) -> bool:
    """Validate a queued draft and commit publication with the job result."""
    queue = catalog.jobs
    job = queue.claim("validate_hint", now_ns=clock(), lease_ns=300_000_000_000)
    if job is None:
        return False
    draft = job.payload
    candidate = HintCandidate(
        SkillRef(f"hint:{job.id}", "1", draft["summary"]), Scope(**draft["scope"]),
        draft["hint"], frozenset(draft["variants"]), draft["variable_inputs"],
    )
    runs = validate(candidate)
    store = ArtifactStore(catalog.path)
    references = set()
    accepted = eligible(candidate, runs)
    for run in runs:
        required = {check.id for check in run.result.scenario.checkpoints if check.required}
        evidence = dict(run.evidence)
        if not required <= evidence.keys():
            accepted = False
        references.update(evidence.values())
    accepted = accepted and all(store.get(ref) is not None for ref in references)

    def publish(db: Connection) -> None:
        for reference in sorted(references):
            pinned = db.execute(
                "INSERT INTO artifact_pins SELECT ?, id FROM artifacts WHERE id=?",
                (f"{candidate.ref.id}:{candidate.ref.revision}", reference),
            )
            if pinned.rowcount != 1:
                raise ValueError("Validation evidence expired before publication")
        catalog.publish_hint_in(
            db, candidate.ref, candidate.scope, candidate.hint, capabilities=candidate.capabilities,
        )

    return queue.complete(
        job, {"published": accepted, "sessions": [run.session_id for run in runs],
              "evidence": sorted(references)},
        now_ns=clock(), finalize=publish if accepted else None,
    )
