"""Serialize the executable portion of a versioned skill."""

import json
from dataclasses import asdict

from qabro.contract import Checkpoint, Step
from qabro.runner import Parameter, Recipe, RecipeStep


def encode_recipe(recipe: Recipe) -> str:
    return json.dumps(asdict(recipe), sort_keys=True, allow_nan=False)


def decode_recipe(encoded: str) -> Recipe:
    data = json.loads(encoded)
    steps = []
    for entry in data["steps"]:
        source = entry["source"]
        checkpoints = tuple(Checkpoint(**check) for check in source["checkpoints"])
        arguments = tuple(
            (key, Parameter(**value) if isinstance(value, dict) else value)
            for key, value in entry["arguments"]
        )
        if any(not isinstance(value, (str, Parameter)) for _, value in arguments):
            raise ValueError("Unsupported recipe argument")
        steps.append(RecipeStep(Step(source["id"], source["action"], checkpoints), entry["tool"], arguments))
    return Recipe(data["id"], data["revision"], tuple(steps))
