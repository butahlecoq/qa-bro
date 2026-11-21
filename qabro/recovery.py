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


def confirmed_effect(browser: BrowserCalls, action: str) -> Effect:
    """Verify that the effect claim links to a successful, later read-only probe."""
    events = {event: (sequence, kind, data) for sequence, event, kind, data
              in browser.journal.events(browser.attempt)}
    original = events.get(f"{action}:start")
    claim = events.get(f"{action}:reconciled")
    if original is None or claim is None or claim[1] != "reconciliation":
        return Effect.UNKNOWN
    probe_id = claim[2].get("probe_event_id")
    effect = claim[2].get("effect")
    if effect not in (Effect.COMPLETED, Effect.ABSENT) or not isinstance(probe_id, str):
        return Effect.UNKNOWN
    probe = events.get(f"{probe_id.removesuffix(':finish')}:start")
    finish = events.get(probe_id)
    if probe is None or finish is None:
        return Effect.UNKNOWN
    valid = (
        original[1] == probe[1] == "tool_start"
        and finish[1] == "tool_finish"
        and finish[2].get("outcome") == Outcome.RETURNED
        and original[0] < probe[0] < finish[0] < claim[0]
        and probe[2].get("read_only") is True
        and all(probe[2].get(key) == original[2].get(key) for key in ("step", "context", "tab"))
    )
    return Effect(effect) if valid else Effect.UNKNOWN


def confirmed_completion(browser: BrowserCalls, action: str) -> bool:
    return confirmed_effect(browser, action) is Effect.COMPLETED
