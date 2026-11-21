"""Run a source scenario through the shared browser call boundary."""

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic_ns, sleep

from qabro.bindings import AttemptBindings, Option, Options, UnresolvedBinding
from qabro.budget import BudgetExhausted
from qabro.browser import BrowserCalls, Outcome
from qabro.contract import Attempt, Cause, Checkpoint, Observation, Scenario, Step
from qabro.evidence import CheckWindow, Evidence
from qabro.recovery import confirmed_completion


class AmbiguousTarget(Exception):
    """Several observed UI elements could satisfy the source action."""

    def __init__(self, artifact_id: str):
        super().__init__("The source action has multiple possible UI targets")
        if not artifact_id:
            raise ValueError("Ambiguous targets require an evidence reference")
        self.artifact_id = artifact_id


class EnvironmentBlocked(Exception):
    """The current environment prevents the next scenario operation."""

    def __init__(self, artifact_id: str):
        super().__init__("The environment prevents scenario execution")
        if not artifact_id:
            raise ValueError("A blocked environment requires an evidence reference")
        self.artifact_id = artifact_id


@dataclass(frozen=True)
class Action:
    tool: str
    arguments: dict


@dataclass(frozen=True)
class Parameter:
    name: str


@dataclass(frozen=True)
class ArgumentBranch:
    probe: str
    when_true: tuple[tuple[str, str | Parameter], ...]
    when_false: tuple[tuple[str, str | Parameter], ...]


@dataclass(frozen=True)
class RecipeStep:
    source: Step
    tool: str
    arguments: tuple[tuple[str, str | Parameter], ...]
    branch: ArgumentBranch | None = None

    def resolve(
        self, bindings: AttemptBindings, read_options: Callable[[str], Options] | None = None,
        *, branch_value: bool | None = None,
    ) -> Action:
        arguments = {}
        expressions = self.arguments
        if self.branch is not None:
            if branch_value is None:
                raise ValueError("Recipe branch requires an observation")
            expressions += self.branch.when_true if branch_value else self.branch.when_false
        for key, expression in expressions:
            value = bindings.resolve(expression.name, read_options) if isinstance(expression, Parameter) else expression
            arguments[key] = value.id if isinstance(value, Option) else value
        return Action(self.tool, arguments)


@dataclass(frozen=True)
class RecipeCall:
    id: str
    revision: str


@dataclass(frozen=True)
class Recipe:
    id: str
    revision: str
    steps: tuple[RecipeStep | RecipeCall, ...]

    def __post_init__(self):
        if not self.steps:
            raise ValueError("A recipe must implement at least one source step")



def expand_recipe(
    recipe: Recipe,
    load: Callable[[str, str], Recipe | None] | None,
    limit: int,
) -> tuple[RecipeStep, ...]:
    """Resolve immutable nested revisions with a bounded, acyclic expansion."""
    steps = []

    def visit(current: Recipe, parents: frozenset[tuple[str, str]]) -> None:
        identity = (current.id, current.revision)
        if identity in parents or len(parents) >= 32:
            raise ValueError("Cyclic or excessively nested recipe")
        for node in current.steps:
            if isinstance(node, RecipeStep):
                if len(steps) >= limit:
                    raise ValueError("Recipe exceeds the remaining source steps")
                steps.append(node)
                continue
            nested = load(node.id, node.revision) if load else None
            if nested is None or (nested.id, nested.revision) != (node.id, node.revision):
                raise ValueError("Pinned nested recipe revision is unavailable")
            visit(nested, parents | {identity})

    visit(recipe, frozenset())
    return tuple(steps)


def run_scenario(
    scenario: Scenario,
    browser: BrowserCalls,
    resolve: Callable[[Step], Action],
    observe: Callable[[Checkpoint, int], Evidence | None],
    *,
    choose: Callable[[Step], Recipe | None] | None = None,
    applicable: Callable[[Recipe], bool] | None = None,
    bindings: AttemptBindings | None = None,
    max_actions: int | None = None,
    read_options: Callable[[str], Options] | None = None,
    probe_branch: Callable[[Step, str], bool | None] | None = None,
    recover: Callable[[str, Step], None] | None = None,
    resume: bool = False,
    load_recipe: Callable[[str, str], Recipe | None] | None = None,
) -> Attempt:
    """Execute each source step and stop on a failed or unverified required check."""
    journal = browser.journal
    attempt_id = browser.attempt
    saved = {event: payload for _, event, _, payload in journal.events(attempt_id)} if resume else {}
    if resume and ("scenario:start" not in saved or "scenario:finish" in saved):
        raise ValueError("Resume requires an unfinished scenario")
    journal.append(attempt_id, "scenario:start", "scenario_start", {
        "source_hash": scenario.source_hash,
        "contract_revision": scenario.revision,
        "binding_revision": bindings.revision if bindings else None,
        "step_ids": [step.id for step in scenario.steps],
    }, reserve=not resume)
    completed = []
    observations = {}
    artifacts = {}
    planned: dict[int, RecipeStep] = {}
    for event, payload in saved.items():
        if not event.startswith("recipe:"):
            continue
        index = int(event.removeprefix("recipe:"))
        recipe = load_recipe(payload["id"], payload["revision"]) if load_recipe else None
        if recipe is None or (recipe.id, recipe.revision) != (payload["id"], payload["revision"]):
            raise ValueError("The pinned recipe is unavailable for resume")
        expanded = expand_recipe(recipe, load_recipe, len(scenario.steps) - index)
        covered = tuple(item.source for item in expanded)
        if covered != scenario.steps[index:index + len(covered)] or bindings is None:
            raise ValueError("The pinned recipe cannot resume this scenario")
        planned.update(enumerate(expanded, start=index))
    cause = Cause.UNKNOWN
    blocked = False
    try:
        for index, step in enumerate(scenario.steps):
            if max_actions is not None and index >= max_actions:
                break
            action_id = f"step-{index}"
            replayed = f"{action_id}:start" in saved
            if replayed:
                opened = saved[f"{action_id}:window"]["opened_ns"]
                succeeded = (
                    saved.get(f"{action_id}:finish", {}).get("outcome") == Outcome.RETURNED
                )
            else:
                if index not in planned and choose is not None and applicable is not None and bindings is not None:
                    recipe = choose(step)
                    if recipe is not None:
                        expanded = expand_recipe(recipe, load_recipe, len(scenario.steps) - index)
                        covered = tuple(item.source for item in expanded)
                        if covered == scenario.steps[index:index + len(covered)] and applicable(recipe):
                            planned.update(enumerate(expanded, start=index))
                            journal.append(attempt_id, f"recipe:{index}", "recipe_selected", {
                                "id": recipe.id, "revision": recipe.revision,
                                "steps": [item.id for item in covered],
                            })
                if index in planned and bindings is not None:
                    item = planned[index]
                    branch_value = None
                    if item.branch is not None and probe_branch is not None:
                        branch_value = probe_branch(step, item.branch.probe)
                    if item.branch is not None and branch_value is None:
                        action = resolve(step)
                    else:
                        action = item.resolve(bindings, read_options, branch_value=branch_value)
                else:
                    action = resolve(step)
                opened = saved.get(f"{action_id}:window", {}).get("opened_ns", monotonic_ns())
                journal.append(attempt_id, f"{action_id}:window", "step_window", {
                    "opened_ns": opened,
                })
                try:
                    result = browser.invoke(action_id, step.id, action.tool, action.arguments)
                except TimeoutError:
                    if recover is None:
                        raise
                    result = None
                succeeded = result is not None and result.outcome is Outcome.RETURNED
            if not succeeded:
                if recover is not None and saved.get(f"{action_id}:reconciled", {}).get("effect") != "completed":
                    recover(action_id, step)
                if not confirmed_completion(browser, action_id):
                    journal.append(attempt_id, f"{action_id}:uncertain", "unresolved_effect", {
                        "step": step.id, "action_event_id": f"{action_id}:start",
                    })
                    break
            completed.append(step.id)
            for checkpoint in step.checkpoints:
                window = CheckWindow(checkpoint, opened)
                previous = saved.get(f"check:{checkpoint.id}")
                if previous is not None:
                    observations[checkpoint.id] = Observation(previous["outcome"])
                    artifacts[checkpoint.id] = previous.get("artifact_id")
                    continue
                if replayed and checkpoint.wait_ns == 0:
                    observations[checkpoint.id] = Observation.UNVERIFIED
                    continue
                try:
                    evidence, outcome = _observe(window, observe, start=monotonic_ns() if replayed else 0)
                except (TimeoutError, BudgetExhausted):
                    observations[checkpoint.id] = Observation.UNVERIFIED
                    raise
                observations[checkpoint.id] = outcome
                if evidence:
                    artifacts[checkpoint.id] = evidence.artifact_id
                journal.append(attempt_id, f"check:{checkpoint.id}", "checkpoint", {
                    "step": step.id,
                    "outcome": outcome,
                    "artifact_id": artifacts.get(checkpoint.id),
                })
            if any(
                checkpoint.required and observations[checkpoint.id] is not Observation.MATCH
                or observations[checkpoint.id] is Observation.MISMATCH
                for checkpoint in step.checkpoints
            ):
                break
    except EnvironmentBlocked as error:
        blocked = True
        cause = Cause.ENVIRONMENT
        journal.append(attempt_id, f"{action_id}:blocked", "environment_blocked", {
            "step": step.id, "artifact_id": error.artifact_id,
        })
    except AmbiguousTarget as error:
        cause = Cause.AUTOMATION
        journal.append(attempt_id, f"{action_id}:ambiguous", "ambiguous_target", {
            "step": step.id, "artifact_id": error.artifact_id,
        })
    except UnresolvedBinding:
        cause = Cause.AUTOMATION
        journal.append(attempt_id, f"{action_id}:binding", "unresolved_binding", {"step": step.id})
    except BudgetExhausted as error:
        cause = Cause.AUTOMATION
        journal.append(attempt_id, "scenario:budget", "budget_exhausted", {"reason": str(error)})
    except TimeoutError:
        journal.append(attempt_id, "scenario:timeout", "attempt_timeout", {})

    for step in scenario.steps:
        for checkpoint in step.checkpoints:
            if checkpoint.id not in observations:
                observations[checkpoint.id] = Observation.NOT_REACHED
            journal.append(attempt_id, f"check:{checkpoint.id}", "checkpoint", {
                "step": step.id,
                "outcome": observations[checkpoint.id],
                "artifact_id": artifacts.get(checkpoint.id),
            })

    if Observation.MISMATCH in observations.values():
        cause = Cause.PRODUCT
    attempt = Attempt(scenario, tuple(completed), observations, blocked=blocked, cause=cause)
    journal.append(attempt_id, "scenario:finish", "scenario_finish", {
        "verdict": attempt.verdict, "cause": attempt.cause,
    })
    return attempt


def _observe(
    window: CheckWindow, observe: Callable[[Checkpoint, int], Evidence | None], *, start: int = 0,
) -> tuple[Evidence | None, Observation]:
    last_evidence = None
    deadline = window.opened_ns + window.checkpoint.wait_ns
    sample = start
    while True:
        evidence = observe(window.checkpoint, sample)
        sample += 1
        if evidence is not None and (window.checkpoint.wait_ns == 0 or evidence.observed_ns <= deadline):
            last_evidence = evidence
        now = monotonic_ns()
        outcome = window.evaluate(last_evidence, now_ns=now)
        if outcome is not Observation.PENDING:
            return last_evidence, outcome
        sleep(min(0.01, max(0, deadline - monotonic_ns()) / 1_000_000_000))
