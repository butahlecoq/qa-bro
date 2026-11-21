"""Observe ordinary and replayed browser calls at the same boundary."""

import json
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from time import monotonic_ns, time_ns

from qabro.artifacts import ArtifactStore
from qabro.budget import Budget
from qabro.journal import Journal


class Outcome(StrEnum):
    RETURNED = "returned"
    TOOL_ERROR = "tool_error"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ToolResult:
    outcome: Outcome
    raw: object
    artifact_id: str | None = None


def normalize(raw: object) -> Outcome:
    if not isinstance(raw, Mapping):
        return Outcome.UNKNOWN
    is_error = raw.get("isError", False)
    if is_error is True:
        return Outcome.TOOL_ERROR
    if is_error is not False:
        return Outcome.UNKNOWN
    content = raw.get("content")
    if not isinstance(content, list) or not all(
        isinstance(item, Mapping) and isinstance(item.get("type"), str) for item in content
    ):
        return Outcome.UNKNOWN
    if not content and "structuredContent" not in raw:
        return Outcome.UNKNOWN
    return Outcome.RETURNED


class BrowserCalls:
    def __init__(
        self,
        journal: Journal,
        attempt: str,
        context: str,
        tab: str,
        call: Callable[[str, str, dict], object],
        redact: Callable[[object], object],
        *,
        budget: Budget | None = None,
        artifacts: ArtifactStore | None = None,
        resources: tuple[str, ...] = (),
        authorize: Callable[[sqlite3.Connection], None] | None = None,
        authorize_action: Callable[[str, dict], None] | None = None,
    ):
        self.journal = journal
        self.attempt = attempt
        self.context = context
        self.tab = tab
        self.call = call
        self.redact = redact
        self.budget = budget
        self.artifacts = artifacts
        self.resources = resources
        self.authorize = authorize
        self.authorize_action = authorize_action

    def invoke(
        self, action: str, step: str, tool: str, arguments: dict, *, read_only: bool = False,
    ) -> ToolResult:
        if self.authorize_action is not None:
            self.authorize_action(tool, arguments)
        if self.budget is not None:
            self.budget.consume("browser")
        self.journal.append(
            self.attempt, f"{action}:start", "tool_start",
            {"step": step, "context": self.context, "tab": self.tab, "tool": tool, "arguments": self.redact(arguments), "read_only": read_only},
            reserve=True, tab=(self.context, self.tab), resources=self.resources, authorize=self.authorize,
        )
        started = monotonic_ns()
        try:
            raw = self.call(self.tab, tool, arguments)
        except Exception as error:
            self._finish(action, Outcome.UNKNOWN, {"exception": type(error).__name__}, started)
            raise
        outcome = normalize(raw)
        artifact_id = self._finish(action, outcome, self.redact(raw), started)
        return ToolResult(outcome, raw, artifact_id)

    def _finish(self, action: str, outcome: Outcome, raw: object, started: int) -> str | None:
        artifact_id = None
        payload = {"outcome": outcome, "elapsed_ns": monotonic_ns() - started}
        if self.artifacts is None:
            payload["raw"] = raw
        else:
            encoded = json.dumps(raw, allow_nan=False, sort_keys=True).encode()
            artifact_id = self.artifacts.put(encoded, now=time_ns())
            payload["artifact_id"] = artifact_id
        self.journal.append(self.attempt, f"{action}:finish", "tool_finish", payload)
        return artifact_id


def claim_child_tabs(browser: BrowserCalls, probe: str, step: str) -> tuple[str, ...]:
    """Lease observed browse popups that directly belong to the current tab."""
    result = browser.invoke(probe, step, "tabs", {"action": "list"}, read_only=True)
    if result.outcome is not Outcome.RETURNED:
        return ()
    try:
        content = result.raw["content"]
        if len(content) != 1 or content[0]["type"] != "text":
            return ()
        tabs = json.loads(content[0]["text"])["tabs"]
        parent, = (
            entry for entry in tabs
            if str(entry["tab"]) == browser.tab or entry.get("id") == browser.tab
        )
        if type(parent["tab"]) is not int:
            return ()
        children = tuple(
            str(entry["tab"]) for entry in tabs
            if entry.get("opener") == parent["tab"] and type(entry["tab"]) is int
            and entry.get("lent") is False and entry.get("browser") == parent.get("browser")
        )
    except (KeyError, TypeError, ValueError):
        return ()
    return tuple(
        child for child in children
        if browser.journal.claim_tab(browser.context, child, browser.attempt, parent=browser.tab)
    )
