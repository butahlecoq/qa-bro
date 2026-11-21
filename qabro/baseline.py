"""Run the local requirements fixture through an already paired browse relay."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic_ns
from uuid import uuid4

from qabro.artifacts import ArtifactStore
from qabro.bindings import AttemptBindings, Literal, Option, Select
from qabro.catalog import Catalog, Scope, SkillRef
from qabro.browser import BrowserCalls, Outcome
from qabro.browse_transport import BrowseTransport
from qabro.budget import Budget
from qabro.contract import Checkpoint, Scenario, Step
from qabro.evidence import Evidence
from qabro.journal import Journal
from qabro.options import read_native_options
from qabro.runner import Action, Parameter, Recipe, RecipeStep, run_scenario
from qabro.skills import RunSkills


def has_saved_row(snapshot: str, expected: str) -> bool:
    """Match the whole accessible name of exactly one fixture list item."""
    row = f"- listitem {json.dumps(expected, ensure_ascii=False)}"
    return sum(line.strip() == row for line in snapshot.splitlines()) == 1


def run_fixture(executable: str, database: Path, *, tab: str, url: str, replay: bool = False) -> dict:
    journal = Journal(database)
    artifacts = ArtifactStore(database)
    attempt = uuid4().hex
    journal.start(attempt, attempt, "fixture")
    if not journal.claim_tab("fixture", tab, attempt):
        raise RuntimeError("Fixture tab is already leased")
    commands = {
        "open": Action("navigate", {"url": url}),
        "name": Action("fill", {"selector": "input[name=name]", "value": "Baseline sample"}),
        "date": Action("fill", {"selector": "input[name=date]", "value": "2027-01-20"}),
        "category": Action("select", {"selector": "select[name=category]", "by": "value"}),
        "create": Action("click", {"selector": "button[type=submit]"}),
    }
    checkpoint = Checkpoint("saved", "The created row has the supplied name, date and category")
    scenario = Scenario("Open, fill name and due date, select the last category, and create.", tuple(
        Step(key, "Select the last category" if key == "category" else key, (checkpoint,) if key == "create" else ()) for key in commands
    ))
    bindings = AttemptBindings({
        "name": Literal(commands["name"].arguments["value"]),
        "date": Literal(commands["date"].arguments["value"]),
        "category": Select(last=True),
    }, seed=0, base_time=datetime.now(UTC))
    recipe_options = {}
    if replay:
        catalog = Catalog(database)
        scope = Scope("fixture", "form", "requirements", "editor")
        ref = SkillRef(f"fixture-fill:{attempt}", "1", "Name date")
        recipe = Recipe(ref.id, ref.revision, tuple(
            RecipeStep(step, "fill", (
                ("selector", f"input[name={step.id}]"), ("value", Parameter(step.id)),
            )) for step in scenario.steps[1:3]
        ) + (RecipeStep(scenario.steps[3], "select", (
            ("selector", "select[name=category]"), ("values", Parameter("category")), ("by", "value"),
        )),))
        catalog.seed_verified_hint(ref, scope, "Fill the name and due date.", recipe=recipe)
        skills = RunSkills(catalog, attempt, scope, frozenset())
        recipe_options = {
            "choose": lambda step: skills.select_recipe(step, lambda _, refs: refs[0]),
            "applicable": lambda _: True,
            "bindings": bindings,
        }
    budget = Budget(browser_calls=7, model_calls=0, seconds=30)
    with BrowseTransport(executable, budget=budget) as transport:
        # The fixture uses synthetic values in a dedicated browser context.
        browser = BrowserCalls(journal, attempt, "fixture", tab, transport, lambda value: value,
                               artifacts=artifacts, budget=budget)

        def observe(check: Checkpoint, sample: int) -> Evidence | None:
            result = browser.invoke(f"{check.id}:sample:{sample}", "create", "snapshot", {}, read_only=True)
            if result.outcome is not Outcome.RETURNED or result.artifact_id is None:
                return None
            snapshot = "\n".join(
                item.get("text", "") for item in result.raw["content"] if item["type"] == "text"
            )
            selected = bindings.use("category")
            if not isinstance(selected, Option):
                return None
            expected = f"Baseline sample | 2027-01-20 | {selected.id}"
            return Evidence(monotonic_ns(), result.artifact_id, has_saved_row(snapshot, expected))

        def read_options(key):
            return read_native_options(browser, "category-options", "category", "select[name=category]")

        def resolve(step: Step) -> Action:
            action = commands[step.id]
            if step.id != "category":
                return action
            selected = bindings.resolve("category", read_options)
            assert isinstance(selected, Option)
            return Action(action.tool, {**action.arguments, "values": selected.id})

        if replay:
            recipe_options["read_options"] = read_options
        started = monotonic_ns()
        result = run_scenario(scenario, browser, resolve, observe, **recipe_options)
        elapsed = monotonic_ns() - started
        journal.release_tab("fixture", tab, attempt)
        events = journal.events(attempt)
        return {
            "attempt": attempt, "server": transport.server_info, "verdict": result.verdict,
            "browser_calls": sum(kind == "tool_start" for _, _, kind, _ in events),
            "model_calls": 0, "tokens": 0, "elapsed_ns": elapsed,
            "recipes": sum(kind == "recipe_selected" for _, _, kind, _ in events),
            "checkpoints": [
                payload for _, _, kind, payload in events if kind == "checkpoint"
            ],
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browse", default="browse")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--tab", required=True)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run_fixture(args.browse, args.database, tab=args.tab, url=args.url, replay=args.replay), indent=2))
