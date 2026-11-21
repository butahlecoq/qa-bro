"""Report one scenario's persisted attempts without merging their proofs."""

from qabro.browser import Outcome
from qabro.contract import Observation, Verdict, overall_verdict
from qabro.journal import Journal
from qabro.recovery import Effect, effect_from_events


def _recipe_progress(events: list[tuple]) -> list[dict]:
    indexed = {event: (sequence, kind, payload) for sequence, event, kind, payload in events}
    decisions = {payload["action"]: payload for _, _, kind, payload in events if kind == "recipe_action"}
    failed_checks = {payload["step"] for _, _, kind, payload in events
                     if kind == "checkpoint" and payload.get("outcome") == Observation.MISMATCH}
    recipes = []
    for _, event, kind, plan in events:
        if kind != "recipe_selected":
            continue
        start = int(event.removeprefix("recipe:"))
        operations = []
        for index, step in enumerate(plan["steps"], start):
            action = f"step-{index}"
            decision = decisions.get(action, {})
            dispatched = f"{action}:start" in indexed and bool(decision) and not decision.get("fallback")
            if not dispatched:
                state = "fallback" if decision.get("fallback") else "not_dispatched"
                operations.append({"step": step, "state": state})
                continue
            resolved = f"{action}:retry" if f"{action}:retry:start" in indexed else action
            request = indexed[f"{resolved}:start"][2]
            finish = indexed.get(f"{resolved}:finish", (None, None, {}))[2]
            effect = (Effect.COMPLETED if finish.get("outcome") == Outcome.RETURNED
                      else effect_from_events(indexed, resolved))
            operations.append({"step": step, "state": effect, "tool": request["tool"],
                               "arguments": request["arguments"], "artifact_id": finish.get("artifact_id")})
        states = [operation["state"] for operation in operations]
        completed = states.count(Effect.COMPLETED)
        effect = (
            "unknown" if Effect.UNKNOWN in states else
            "completed" if completed == len(states) else
            "known_partial" if completed else "none"
        )
        recipes.append({
            "id": plan["id"], "revision": plan["revision"], "effect_status": effect,
            "stopped_at": next((
                op["step"] for op in operations
                if op["state"] != Effect.COMPLETED or op["step"] in failed_checks
            ), None),
            "operations": operations,
        })
    return recipes


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
            "recipes": _recipe_progress(events),
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
