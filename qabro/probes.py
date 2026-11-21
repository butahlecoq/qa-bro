"""Run one queued background UI probe when foreground work permits."""

from collections.abc import Callable
from enum import StrEnum
from hashlib import sha256
from time import time_ns

from qabro.browser import BrowserCalls, Outcome, ToolResult
from qabro.budget import Budget
from qabro.jobs import Job, JobQueue
from qabro.journal import Journal


def run_next_probe(
    queue: JobQueue,
    journal: Journal,
    *,
    foreground_busy: Callable[[], bool],
    context: str,
    transport: Callable[[str, str, dict], object],
    redact: Callable[[object], object],
    execute: Callable[[Job, BrowserCalls], dict],
    clock: Callable[[], int] = time_ns,
    recover: Callable[[Job, BrowserCalls], dict | None] | None = None,
) -> bool:
    """Use a stable attempt and dedicated tab for a host-configured probe."""
    if queue.path.resolve() != journal.path.resolve():
        raise ValueError("A probe needs its queue and journal in the same database")
    if foreground_busy():
        return False
    job = queue.claim("probe", now_ns=clock(), lease_ns=60_000_000_000)
    if job is None:
        return False
    resources = job.payload.get("resources")
    if not isinstance(resources, list) or not resources or not all(
        isinstance(resource, str) and resource for resource in resources
    ):
        return queue.complete(job, {"status": "invalid_resources"}, now_ns=clock())
    tab = "probe-" + sha256(job.id.encode()).hexdigest()[:24]
    attempt = f"probe:{job.id}"
    journal.start(attempt, attempt, "explorer")
    if not journal.claim_tab(context, tab, attempt):
        return False
    if not journal.claim_resources(attempt, tuple(resources)):
        journal.release_tab(context, tab, attempt)
        return False

    browser = BrowserCalls(
        journal, attempt, context, tab, transport, redact, resources=tuple(resources),
        budget=Budget(browser_calls=20, model_calls=2, seconds=30),
        authorize=lambda db: queue.require_lease(db, job, clock()),
    )
    previous = {event: payload for _, event, _, payload in journal.events(attempt)}
    result = previous.get("probe:result")
    if result is None:
        if "probe:started" in previous:
            if recover is None:
                return False
            result = recover(job, browser)
        else:
            journal.append(attempt, "probe:started", "probe_started", {}, reserve=True)
            result = execute(job, browser)
        if result is None or journal.actions_to_reconcile(attempt):
            return False
        journal.append(attempt, "probe:result", "probe_result", result, authorize=browser.authorize)
    return queue.complete(
        job, result, now_ns=clock(),
        finalize=lambda db: journal.finish_probe_in(db, attempt, context, tab),
    )


class Interruption(StrEnum):
    CONFIRM = "confirm"
    DENIED = "denied"
    EXPIRED_AUTH = "expired_auth"
    HANDOFF = "handoff"


def handle_interruption(
    browser: BrowserCalls,
    *,
    step: str,
    evidence_id: str,
    observed: Interruption,
    expected_denial: bool = False,
    confirm: Callable[[], ToolResult] | None = None,
) -> dict:
    """Handle an interruption identified by the host's UI observation policy."""
    if not evidence_id:
        raise ValueError("An interruption requires an evidence reference")
    browser.journal.append(browser.attempt, f"{step}:interruption", "probe_interruption", {
        "step": step, "observed": observed, "evidence_id": evidence_id,
    }, authorize=browser.authorize)
    if observed is Interruption.CONFIRM:
        if confirm is None:
            return {"status": "inconclusive", "reason": "confirmation_not_configured"}
        result = confirm()
        status = "confirmed" if result.outcome is Outcome.RETURNED else "inconclusive"
        return {"status": status, "reason": observed}
    if observed is Interruption.DENIED and expected_denial:
        return {"status": "expected_denial", "reason": observed}
    return {"status": "blocked", "reason": observed}
