"""Gate skill capabilities when the browser tool contract changes."""

from collections.abc import Callable


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
