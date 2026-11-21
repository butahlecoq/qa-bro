"""Run a source scenario through the shared browser call boundary."""

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic_ns, sleep

from qabro.browser import BrowserCalls, Outcome
from qabro.contract import Attempt, Checkpoint, Observation, Scenario, Step
from qabro.evidence import CheckWindow, Evidence


@dataclass(frozen=True)
class Action:
    tool: str
    arguments: dict


def run_scenario(
    scenario: Scenario,
    browser: BrowserCalls,
    resolve: Callable[[Step], Action],
    observe: Callable[[Checkpoint], Evidence | None],
) -> Attempt:
    """Execute each source step and stop on a failed or unverified required check."""
    journal = browser.journal
    attempt_id = browser.attempt
    journal.append(attempt_id, "scenario:start", "scenario_start", {
        "source_hash": scenario.source_hash,
        "step_ids": [step.id for step in scenario.steps],
    }, reserve=True)
    completed = []
    observations = {}
    for index, step in enumerate(scenario.steps):
        action = resolve(step)
        opened = monotonic_ns()
        try:
            result = browser.invoke(f"step-{index}", step.id, action.tool, action.arguments)
        except TimeoutError:
            break
        if result.outcome is not Outcome.RETURNED:
            break
        completed.append(step.id)
        for checkpoint in step.checkpoints:
            window = CheckWindow(checkpoint, opened)
            evidence, outcome = _observe(window, observe)
            observations[checkpoint.id] = outcome
            journal.append(attempt_id, f"check:{checkpoint.id}", "checkpoint", {
                "step": step.id,
                "outcome": outcome,
                "artifact_id": evidence.artifact_id if evidence else None,
            })
        if any(
            checkpoint.required and observations[checkpoint.id] is not Observation.MATCH
            or observations[checkpoint.id] is Observation.MISMATCH
            for checkpoint in step.checkpoints
        ):
            break

    attempt = Attempt(scenario, tuple(completed), observations)
    journal.append(attempt_id, "scenario:finish", "scenario_finish", {"verdict": attempt.verdict})
    return attempt


def _observe(
    window: CheckWindow, observe: Callable[[Checkpoint], Evidence | None]
) -> tuple[Evidence | None, Observation]:
    last_evidence = None
    deadline = window.opened_ns + window.checkpoint.wait_ns
    while True:
        evidence = observe(window.checkpoint)
        if evidence is not None and (window.checkpoint.wait_ns == 0 or evidence.observed_ns <= deadline):
            last_evidence = evidence
        now = monotonic_ns()
        outcome = window.evaluate(last_evidence, now_ns=now)
        if outcome is not Observation.PENDING:
            return last_evidence, outcome
        sleep(min(0.01, max(0, deadline - monotonic_ns()) / 1_000_000_000))
