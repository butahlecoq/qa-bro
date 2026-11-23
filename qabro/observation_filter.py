"""Project structured browser observations into a model-facing schema."""

from collections.abc import Set
from dataclasses import dataclass
from typing import Literal, NotRequired, TypedDict


_ROLES = frozenset({
    "alert", "button", "checkbox", "combobox", "dialog", "group", "heading",
    "link", "listbox", "option", "radio", "searchbox", "spinbutton", "status",
    "switch", "tab", "table", "textbox",
})
_STATES = frozenset({
    "checked", "disabled", "expanded", "focused", "in_dialog", "invalid", "pressed",
    "readonly", "required", "selected", "visible",
})
_FIELDS = frozenset({"role", "label", "state", "field_semantics"})


class Control(TypedDict):
    role: str
    label: str | None
    state: dict[str, bool]
    field_semantics: NotRequired[tuple[str, ...]]


@dataclass(frozen=True)
class FilteredObservation:
    status: Literal["ok", "malformed", "out_of_scope"]
    controls: tuple[Control, ...] = ()


def filter_observations(
    payload: object, *, allowed_labels: Set[str], allowed_field_semantics: Set[str] = frozenset(),
) -> FilteredObservation:
    """Release only approved structure and exact labels from a trusted vocabulary."""
    if not isinstance(payload, list):
        return FilteredObservation("malformed")
    if len(payload) > 128:
        return FilteredObservation("out_of_scope")

    controls = []
    for item in payload:
        if not isinstance(item, dict):
            return FilteredObservation("malformed")
        role = item.get("role")
        label = item.get("label")
        state = item.get("state", {})
        semantics = item.get("field_semantics", [])
        if (
            not isinstance(role, str)
            or (label is not None and not isinstance(label, str))
            or not isinstance(state, dict)
            or any(not isinstance(key, str) or type(value) is not bool for key, value in state.items())
            or not isinstance(semantics, list)
            or any(not isinstance(token, str) for token in semantics)
        ):
            return FilteredObservation("malformed")
        if role not in _ROLES or item.keys() - _FIELDS or state.keys() - _STATES:
            return FilteredObservation("out_of_scope")
        control: Control = {
            "role": role,
            "label": label if label in allowed_labels else None,
            "state": dict(state),
        }
        if role in {"textbox", "searchbox", "combobox"} and state.get("visible") is True:
            approved = tuple(sorted(token for token in set(semantics) if token in allowed_field_semantics))
            if approved:
                control["field_semantics"] = approved
        controls.append(control)
    return FilteredObservation("ok", tuple(controls))
