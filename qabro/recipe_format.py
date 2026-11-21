"""Serialize the executable portion of a versioned skill."""

import json
from dataclasses import asdict

from qabro.contract import Checkpoint, Step
from qabro.recipe_checks import RecipeCheck
from qabro.runner import ArgumentBranch, Parameter, Recipe, RecipeCall, RecipeStep


def encode_recipe(recipe: Recipe) -> str:
    data = asdict(recipe)
    for node in data["steps"]:
        if node.get("guard") is None:
            node.pop("guard", None)
        branch = node.get("branch")
        if branch is not None:
            for key in ("max_wait_ns", "condition"):
                if branch[key] is None:
                    del branch[key]
    return json.dumps(data, sort_keys=True, allow_nan=False)


def decode_recipe(encoded: str) -> Recipe:
    data = json.loads(encoded)
    steps = []
    for entry in data["steps"]:
        if "source" not in entry:
            steps.append(RecipeCall(**entry))
            continue
        source = entry["source"]
        checkpoints = tuple(Checkpoint(**check) for check in source["checkpoints"])
        branch = entry.get("branch")
        condition = ArgumentBranch(
            branch["probe"], _arguments(branch["when_true"]), _arguments(branch["when_false"]),
            branch.get("max_samples", 1), branch.get("max_wait_ns"),
            RecipeCheck(**branch["condition"]) if branch.get("condition") is not None else None,
        ) if branch is not None else None
        guard = entry.get("guard")
        if isinstance(guard, dict):
            guard = RecipeCheck(**guard)
        steps.append(RecipeStep(
            Step(source["id"], source["action"], checkpoints), entry["tool"],
            _arguments(entry["arguments"]), condition, guard,
        ))
    return Recipe(data["id"], data["revision"], tuple(steps))


def _arguments(entries: list) -> tuple[tuple[str, str | Parameter], ...]:
    arguments = tuple(
        (key, Parameter(**value) if isinstance(value, dict) else value) for key, value in entries
    )
    if any(not isinstance(value, (str, Parameter)) for _, value in arguments):
        raise ValueError("Unsupported recipe argument")
    return arguments
