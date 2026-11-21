"""Run one queued background UI probe when foreground work permits."""

from collections.abc import Callable
from hashlib import sha256
from time import time_ns

from qabro.browser import BrowserCalls
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
) -> bool:
    """Use a stable attempt and dedicated tab for a host-configured probe."""
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
    )
    if journal.actions_to_reconcile(attempt):
        return False
    result = execute(job, browser)
    if journal.actions_to_reconcile(attempt):
        return False
    if not queue.complete(job, result, now_ns=clock()):
        return False
    journal.release_resources(attempt)
    journal.release_tab(context, tab, attempt)
    return True
