"""Apply validation evidence requirements before publishing a skill hint."""

from dataclasses import dataclass

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


def publish_hint(
    catalog: Catalog, candidate: HintCandidate, runs: tuple[ValidationRun, ...]
) -> bool:
    """Publish once the supplied independent runs cover the candidate's claims."""
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
    catalog.seed_verified_hint(
        candidate.ref, candidate.scope, candidate.hint, capabilities=candidate.capabilities
    )
    return True
