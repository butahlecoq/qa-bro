"""Serialize the executable portion of a versioned skill."""

import json
from dataclasses import asdict

from qabro.contract import Checkpoint, Step
from qabro.runner import ArgumentBranch, Parameter, Recipe, RecipeCall, RecipeStep


def encode_recipe(recipe: Recipe) -> str:
    return json.dumps(asdict(recipe), sort_keys=True, allow_nan=False)


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
            branch.get("max_samples", 1),
        ) if branch is not None else None
        steps.append(RecipeStep(
            Step(source["id"], source["action"], checkpoints), entry["tool"],
            _arguments(entry["arguments"]), condition,
        ))
    return Recipe(data["id"], data["revision"], tuple(steps))


def _arguments(entries: list) -> tuple[tuple[str, str | Parameter], ...]:
    arguments = tuple(
        (key, Parameter(**value) if isinstance(value, dict) else value) for key, value in entries
    )
    if any(not isinstance(value, (str, Parameter)) for _, value in arguments):
        raise ValueError("Unsupported recipe argument")
    return arguments
