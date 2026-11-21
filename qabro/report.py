"""Report one scenario's persisted attempts without merging their proofs."""

from qabro.contract import Observation, Verdict, overall_verdict
from qabro.journal import Journal


def report_run(journal: Journal, run: str) -> dict:
    attempts = []
    revisions = set()
    failed = False
    recovered = False
    for attempt_id in journal.attempts_for_run(run):
        events = journal.events(attempt_id)
        by_id = {event: payload for _, event, _, payload in events}
        start = by_id.get("scenario:start")
        if start is None:
            continue
        revisions.add(start["contract_revision"])
        finish = by_id.get("scenario:finish", {})
        checkpoints = [payload for _, _, kind, payload in events if kind == "checkpoint"]
        interrupted_mismatch = not finish and any(
            check.get("outcome") == Observation.MISMATCH for check in checkpoints
        )
        verdict = Verdict.FAIL if interrupted_mismatch else Verdict(finish.get("verdict", Verdict.INCONCLUSIVE))
        recovered |= failed and verdict is Verdict.PASS
        failed |= verdict is Verdict.FAIL
        attempts.append({
            "id": attempt_id,
            **journal.restart_metadata(attempt_id),
            "verdict": verdict,
            "cause": finish.get("cause", "product" if interrupted_mismatch else "unknown"),
            "checkpoints": checkpoints,
            "diagnostics": [
                {"kind": kind, **payload} for _, _, kind, payload in events
                if kind in {"ambiguous_target", "environment_blocked", "resume_document_check",
                            "unresolved_effect", "effect_absent", "reconciliation"}
            ],
        })

    if len(revisions) > 1:
        raise ValueError("Run attempts must share the same scenario revision")
    pruned = journal.pruned_attempts_for_run(run)
    verdict = overall_verdict(tuple(attempt["verdict"] for attempt in attempts))
    if journal.has_pruned_failure(run):
        verdict = Verdict.FAIL
    elif pruned and verdict is not Verdict.FAIL:
        verdict = Verdict.INCONCLUSIVE
    return {
        "run": run,
        "verdict": verdict,
        "pruned_attempt_ids": pruned,
        "flaky_or_recovered_after_failure": recovered,
        "attempts": attempts,
    }
