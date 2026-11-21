"""Gate skill capabilities when the browser tool contract changes."""

import json
from collections.abc import Callable
from dataclasses import asdict
from hashlib import sha256

from qabro.catalog import Catalog, Scope, SkillRef
from qabro.jobs import JobQueue


def verified_capabilities(
    previous: dict,
    current: dict,
    required: frozenset[str],
    smoke_test: Callable[[str], bool],
) -> frozenset[str]:
    """Return available tools that match the old contract or pass a live check."""
    old_tools = _tools_by_name(previous)
    new_tools = _tools_by_name(current)
    available = set()
    for name in sorted(required & new_tools.keys()):
        if old_tools.get(name) == new_tools[name] or smoke_test(name):
            available.add(name)
    return frozenset(available)


def _tools_by_name(schema: dict) -> dict[str, dict]:
    tools = {}
    for definition in schema["tools"]:
        name = definition["name"]
        if name in tools:
            raise ValueError(f"Duplicate browser tool definition: {name}")
        # Descriptions can change without affecting the executable interface.
        tools[name] = {
            key: definition.get(key) for key in ("inputSchema", "outputSchema")
        }
    return tools


def propose_transfer(
    catalog: Catalog, queue: JobQueue, run: str, skill: SkillRef, target: Scope,
) -> str:
    """Record a scope hypothesis for independent validation."""
    source = catalog.confirmed_scope(run, skill)
    if source is None:
        raise ValueError("Transfer requires a skill revision pinned to this run")
    if source == target:
        raise ValueError("Target scope is already confirmed for this revision")
    payload = {"skill": asdict(skill), "source": asdict(source), "target": asdict(target)}
    job_id = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    queue.enqueue(job_id, "validate_transfer", payload)
    return job_id
