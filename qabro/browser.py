"""Observe ordinary and replayed browser calls at the same boundary."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from time import monotonic_ns

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
    ):
        self.journal = journal
        self.attempt = attempt
        self.context = context
        self.tab = tab
        self.call = call
        self.redact = redact
        self.budget = budget

    def invoke(self, action: str, step: str, tool: str, arguments: dict) -> ToolResult:
        if self.budget is not None:
            self.budget.consume("browser")
        self.journal.append(
            self.attempt, f"{action}:start", "tool_start",
            {"step": step, "context": self.context, "tab": self.tab, "tool": tool, "arguments": self.redact(arguments)},
            reserve=True, tab=(self.context, self.tab),
        )
        started = monotonic_ns()
        try:
            raw = self.call(self.tab, tool, arguments)
        except Exception as error:
            self._finish(action, Outcome.UNKNOWN, {"exception": type(error).__name__}, started)
            raise
        outcome = normalize(raw)
        self._finish(action, outcome, self.redact(raw), started)
        return ToolResult(outcome, raw)

    def _finish(self, action: str, outcome: Outcome, raw: object, started: int) -> None:
        self.journal.append(
            self.attempt, f"{action}:finish", "tool_finish",
            {"outcome": outcome, "raw": raw, "elapsed_ns": monotonic_ns() - started},
        )
