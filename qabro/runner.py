"""Run a source scenario through the shared browser call boundary."""

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic_ns, sleep

from qabro.bindings import AttemptBindings, Option
from qabro.budget import BudgetExhausted
from qabro.browser import BrowserCalls, Outcome
from qabro.contract import Attempt, Checkpoint, Observation, Scenario, Step
from qabro.evidence import CheckWindow, Evidence


@dataclass(frozen=True)
class Action:
    tool: str
    arguments: dict


@dataclass(frozen=True)
class Parameter:
    name: str


@dataclass(frozen=True)
class RecipeStep:
    source: Step
    tool: str
    arguments: tuple[tuple[str, str | Parameter], ...]

    def resolve(self, bindings: AttemptBindings) -> Action:
        arguments = {}
        for key, expression in self.arguments:
            value = bindings.use(expression.name) if isinstance(expression, Parameter) else expression
            arguments[key] = value.id if isinstance(value, Option) else value
        return Action(self.tool, arguments)


@dataclass(frozen=True)
class Recipe:
    id: str
    revision: str
    steps: tuple[RecipeStep, ...]

    def __post_init__(self):
        if not self.steps:
            raise ValueError("A recipe must implement at least one source step")



def run_scenario(
    scenario: Scenario,
    browser: BrowserCalls,
    resolve: Callable[[Step], Action],
    observe: Callable[[Checkpoint], Evidence | None],
    *,
    choose: Callable[[Step], Recipe | None] | None = None,
    applicable: Callable[[Recipe], bool] | None = None,
    bindings: AttemptBindings | None = None,
    max_actions: int | None = None,
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
    planned: dict[int, RecipeStep] = {}
    for index, step in enumerate(scenario.steps):
        if max_actions is not None and index >= max_actions:
            break
        if index not in planned and choose is not None and applicable is not None and bindings is not None:
            recipe = choose(step)
            if recipe is not None:
                covered = tuple(item.source for item in recipe.steps)
                if covered == scenario.steps[index:index + len(covered)] and applicable(recipe):
                    planned.update(enumerate(recipe.steps, start=index))
                    journal.append(attempt_id, f"recipe:{index}", "recipe_selected", {
                        "id": recipe.id, "revision": recipe.revision,
                        "steps": [item.id for item in covered],
                    })
        action = planned[index].resolve(bindings) if index in planned and bindings is not None else resolve(step)
        opened = monotonic_ns()
        try:
            result = browser.invoke(f"step-{index}", step.id, action.tool, action.arguments)
        except BudgetExhausted as error:
            journal.append(attempt_id, "scenario:budget", "budget_exhausted", {"reason": str(error)})
            break
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
