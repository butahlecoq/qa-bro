"""Gate skill capabilities when the browser tool contract changes."""

import json
from collections.abc import Callable, Mapping
from dataclasses import asdict
from hashlib import sha256

from qabro.browse_schema import snapshot_schema
from qabro.browse_transport import BrowseTransport
from qabro.browser import BrowserCalls
from qabro.catalog import Catalog, Scope, SkillRef
from qabro.jobs import JobQueue
from qabro.options import read_native_options


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


def check_browse_upgrade(
    browser: BrowserCalls,
    transport: BrowseTransport,
    previous: dict,
    smoke_checks: Mapping[str, Callable[[BrowserCalls], bool]],
    required: frozenset[str],
) -> frozenset[str]:
    """Record the live contract and check changed tools on a prepared fixture tab."""
    if browser.call is not transport:
        raise ValueError("Compatibility checks must use the inspected MCP session")
    current = snapshot_schema(transport)
    browser.journal.append(browser.attempt, "browse:schema", "browser_schema", current)

    def smoke(tool: str) -> bool:
        check = smoke_checks.get(tool)
        passed = check(browser) if check is not None else False
        browser.journal.append(browser.attempt, f"compatibility:{tool}", "compatibility_check", {
            "tool": tool, "passed": passed, "schema_sha256": current["schema_sha256"],
        })
        return passed

    return verified_capabilities(previous, current, required, smoke)


def observe_static_select(
    catalog: Catalog, scope: Scope, browser: BrowserCalls, *, probe: str, step: str, selector: str,
) -> list[SkillRef]:
    """Compare a static select's ordered option definitions in a verified UI scope."""
    options = read_native_options(browser, probe, step, selector)
    encoded = json.dumps([asdict(option) for option in options.items], sort_keys=True)
    return catalog.observe_component(scope, sha256(encoded.encode()).hexdigest())
