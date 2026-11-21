"""Reconcile interrupted browser actions using fresh UI evidence."""

from collections.abc import Callable
from enum import StrEnum

from qabro.browser import BrowserCalls, Outcome


class Effect(StrEnum):
    COMPLETED = "completed"
    ABSENT = "absent"
    UNKNOWN = "unknown"


def reconcile(
    browser: BrowserCalls,
    action: str,
    probe_id: str,
    tool: str,
    arguments: dict,
    evaluate: Callable[[object], Effect],
) -> Effect:
    """Inspect an unresolved action using a caller-supplied read-only probe."""
    pending = dict(browser.journal.actions_to_reconcile(browser.attempt))
    original = pending.get(action)
    if original is None:
        raise ValueError("Action does not require reconciliation")
    if (original["context"], original["tab"]) != (browser.context, browser.tab):
        raise ValueError("Probe must use the original browser context and tab")

    result = browser.invoke(probe_id, original["step"], tool, arguments, read_only=True)
    effect = evaluate(result.raw) if result.outcome is Outcome.RETURNED else Effect.UNKNOWN
    if effect is not Effect.UNKNOWN:
        browser.journal.append(browser.attempt, f"{action}:reconciled", "reconciliation", {
            "effect": effect, "probe_event_id": f"{probe_id}:finish",
        })
    return effect
