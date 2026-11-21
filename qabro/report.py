"""Report one scenario's persisted attempts without merging their proofs."""

from qabro.contract import Verdict, overall_verdict
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
        verdict = Verdict(finish.get("verdict", Verdict.INCONCLUSIVE))
        recovered |= failed and verdict is Verdict.PASS
        failed |= verdict is Verdict.FAIL
        attempts.append({
            "id": attempt_id,
            "verdict": verdict,
            "cause": finish.get("cause", "unknown"),
            "checkpoints": [payload for _, _, kind, payload in events if kind == "checkpoint"],
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
