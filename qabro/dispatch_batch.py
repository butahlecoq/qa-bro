"""Pack explicitly chosen serial actions around an authorized guarded dispatcher."""

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType


_ARGUMENTS = frozenset({"label", "parameter", "state", "role", "direction", "filter", "semantic", "text"})
_CONTINUATION_STATUSES = frozenset({"ok", "dispatched", "complete"})


@dataclass(frozen=True)
class DraftField:
    """Canonical host binding for a field in one non-committing draft form."""

    form: str
    field: str

    def __post_init__(self):
        if not all(isinstance(value, str) and value for value in (self.form, self.field)):
            raise ValueError("Expected a named draft form and canonical field")


@dataclass(frozen=True)
class BatchAction:
    """Host rule for exact semantic arguments and acceptable continuation evidence."""

    arguments: frozenset[str]
    may_continue: Callable[[dict], bool]
    mutates: bool = False
    # Keys are exact argument values in alphabetical argument-name order.
    draft_grants: Mapping[tuple[str, ...], DraftField] | None = None

    def __post_init__(self):
        if (
            not isinstance(self.arguments, frozenset) or not self.arguments <= _ARGUMENTS
            or not callable(self.may_continue) or type(self.mutates) is not bool
        ):
            raise ValueError("Expected immutable semantic arguments and a host continuation policy")
        if self.draft_grants is not None:
            if not self.mutates or not isinstance(self.draft_grants, Mapping) or not self.draft_grants or any(
                not isinstance(key, tuple) or len(key) != len(self.arguments)
                or not all(isinstance(value, str) for value in key)
                or not isinstance(field, DraftField)
                for key, field in self.draft_grants.items()
            ):
                raise ValueError("Expected exact host grants for a non-committing draft mutation")
            object.__setattr__(self, "draft_grants", MappingProxyType(dict(self.draft_grants)))


def _accepts(value: object, schema: dict) -> bool:
    return (
        isinstance(value, str) and schema.get("type", "string") == "string"
        and ("const" not in schema or value == schema["const"])
        and ("enum" not in schema or value in schema["enum"])
    )


def make_batched_tool(
    guarded_dispatch: Callable[[dict], dict],
    tool: dict,
    policies: Mapping[str, BatchAction],
    *,
    max_steps: int = 4,
) -> tuple[dict, Callable[[object], dict]]:
    """Add bounded batching without changing a child call or assigning a scenario verdict."""

    if type(max_steps) is not int or not 1 <= max_steps <= 8 or not policies:
        raise ValueError("Expected one to eight batch steps and explicit action policies")

    variant = deepcopy(tool)
    base = variant["inputSchema"]
    properties = base["properties"]
    required = frozenset(base.get("required", ()))
    if (
        base["type"] != "object" or base.get("additionalProperties") is not False
        or "action" not in required or not required <= properties.keys()
        or properties.keys() - ({"action"} | _ARGUMENTS)
        or any(schema.get("type", "string") != "string" for schema in properties.values())
        or _accepts("batch", properties["action"])
    ):
        raise ValueError("Batching requires a closed guarded schema with scalar semantic arguments")

    rules = dict(policies)
    alternatives = []
    for action, rule in rules.items():
        if not _accepts(action, properties["action"]) or not rule.arguments <= (properties.keys() - {"action"}):
            raise ValueError("Batch policy must use a declared action and its semantic arguments")
        alternatives.append({
            "type": "object",
            "properties": {"action": {"const": action}, **{
                key: deepcopy(properties[key]) for key in sorted(rule.arguments)
            }},
            "required": ["action", *sorted(rule.arguments)],
            "additionalProperties": False,
        })

    variant["description"] += (
        " Optionally execute a bounded batch of explicitly selected guarded actions in order. "
        "Outer completion is an execution receipt. Check individual results for evidence."
    )
    if any(rule.draft_grants is not None for rule in rules.values()):
        variant["description"] += (
            " Approved draft edits must target distinct fields in one form. "
            "Use a separate call for submitting or other mutating actions."
        )
    variant["inputSchema"] = {"type": "object", "oneOf": [
        deepcopy(base),
        {
            "type": "object",
            "properties": {
                "action": {"const": "batch"},
                "steps": {"type": "array", "minItems": 1, "maxItems": max_steps,
                          "items": {"oneOf": alternatives}},
            },
            "required": ["action", "steps"],
            "additionalProperties": False,
        },
    ]}

    def is_guarded_request(request):
        return (
            isinstance(request, dict) and required <= request.keys() <= properties.keys()
            and all(_accepts(value, properties[key]) for key, value in request.items())
        )

    def dispatch(request):
        if not isinstance(request, dict) or request.get("action") != "batch":
            return guarded_dispatch(dict(request)) if is_guarded_request(request) else {"status": "out_of_scope"}

        if request.keys() != {"action", "steps"}:
            return {"status": "out_of_scope"}
        steps = request["steps"]
        if not isinstance(steps, list) or not 1 <= len(steps) <= max_steps:
            return {"status": "out_of_scope"}

        plan = []
        draft_fields = set()
        ordinary_mutations = 0
        for step in steps:
            if not is_guarded_request(step):
                return {"status": "out_of_scope"}
            rule = rules.get(step["action"])
            if rule is None or step.keys() != {"action"} | rule.arguments:
                return {"status": "out_of_scope"}
            if rule.draft_grants is not None:
                field = rule.draft_grants.get(tuple(step[key] for key in sorted(rule.arguments)))
                if field is None or field in draft_fields:
                    return {"status": "out_of_scope"}
                draft_fields.add(field)
            else:
                ordinary_mutations += rule.mutates
            plan.append((dict(step), rule))
        if (
            ordinary_mutations > 1 or (ordinary_mutations and draft_fields)
            or len({field.form for field in draft_fields}) > 1
        ):
            return {"status": "out_of_scope"}

        trace = []
        for step, rule in plan:
            try:
                result = guarded_dispatch(dict(step))
            except (OSError, RuntimeError, ValueError):
                result = None
            if not isinstance(result, dict) or not isinstance(result.get("status"), str):
                result = {"status": "unknown_effect" if rule.mutates else "unavailable"}

            trace.append({"request": step, "result": deepcopy(result)})
            try:
                eligible = result["status"] in _CONTINUATION_STATUSES
                if rule.draft_grants is not None:
                    eligible = result["status"] == "ok" and result.get("matches") is True
                allowed = eligible and rule.may_continue(result) is True
            except (LookupError, TypeError, ValueError):
                allowed = False
            if not allowed:
                return {"status": "stopped", "trace": trace}

        return {"status": "complete", "trace": trace}

    return variant, dispatch
