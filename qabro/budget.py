"""Shared limits for one scenario and its synchronous work."""

from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from math import isfinite
from threading import Lock
from time import monotonic_ns
from typing import Literal


CallKind = Literal["browser", "model"]


class BudgetExhausted(Exception):
    """The attempt reached a configured limit."""


class Budget:
    def __init__(self, *, browser_calls: int, model_calls: int, seconds: float):
        if min(browser_calls, model_calls) < 0 or not isfinite(seconds) or seconds <= 0:
            raise ValueError("Invalid attempt limits")
        self._limits = {"browser": browser_calls, "model": model_calls}
        self._counts = {"browser": 0, "model": 0}
        self._deadline = monotonic_ns() + int(seconds * 1_000_000_000)
        self._lock = Lock()
        self._operation_deadline = ContextVar("operation_deadline", default=self._deadline)

    def remaining_seconds(self) -> float:
        remaining = (self._operation_deadline.get() - monotonic_ns()) / 1_000_000_000
        if remaining <= 0:
            raise BudgetExhausted("Attempt time limit reached")
        return remaining

    @contextmanager
    def until(self, deadline_ns: int):
        token = self._operation_deadline.set(min(self._operation_deadline.get(), deadline_ns))
        try:
            yield
        finally:
            self._operation_deadline.reset(token)

    def consume(self, kind: CallKind) -> float:
        """Reserve a call and return the time available to its transport."""
        with self._lock:
            remaining = self.remaining_seconds()
            if self._counts[kind] >= self._limits[kind]:
                raise BudgetExhausted(f"Attempt {kind} call limit reached")
            self._counts[kind] += 1
            return remaining

    def counts(self) -> dict[str, int]:
        with self._lock:
            return self._counts.copy()

    def call_model[Result](self, call: Callable[[float], Result]) -> Result:
        """Invoke a model adapter with the remaining wall-clock allowance."""
        return call(self.consume("model"))
