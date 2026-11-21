"""Run the local requirements fixture through an already paired browse relay."""

import argparse
import json
from pathlib import Path
from time import monotonic_ns
from uuid import uuid4

from qabro.artifacts import ArtifactStore
from qabro.browser import BrowserCalls, Outcome
from qabro.browse_transport import BrowseTransport
from qabro.budget import Budget
from qabro.contract import Checkpoint, Scenario, Step
from qabro.evidence import Evidence
from qabro.journal import Journal
from qabro.runner import Action, run_scenario


def run_fixture(executable: str, database: Path, *, tab: str, url: str) -> dict:
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
        "category": Action("select", {"selector": "select[name=category]", "values": ["operations"]}),
        "create": Action("click", {"selector": "button[type=submit]"}),
    }
    checkpoint = Checkpoint("saved", "The created row has the supplied name, date and category")
    scenario = Scenario("Open, fill name and due date, select category, and create.", tuple(
        Step(key, key, (checkpoint,) if key == "create" else ()) for key in commands
    ))
    budget = Budget(browser_calls=6, model_calls=0, seconds=30)
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
            expected = "Baseline sample | 2027-01-20 | operations"
            return Evidence(monotonic_ns(), result.artifact_id, expected in snapshot)

        started = monotonic_ns()
        result = run_scenario(scenario, browser, lambda step: commands[step.id], observe)
        elapsed = monotonic_ns() - started
        journal.release_tab("fixture", tab, attempt)
        events = journal.events(attempt)
        return {
            "attempt": attempt, "server": transport.server_info, "verdict": result.verdict,
            "browser_calls": sum(kind == "tool_start" for _, _, kind, _ in events),
            "model_calls": 0, "tokens": 0, "elapsed_ns": elapsed,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browse", default="browse")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--tab", required=True)
    args = parser.parse_args()
    print(json.dumps(run_fixture(args.browse, args.database, tab=args.tab, url=args.url), indent=2))
