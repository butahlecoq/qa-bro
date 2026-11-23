"""Dispatch one host-approved create action from a dedicated browser tab."""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from threading import Lock
from typing import Literal

from qabro.browser import Outcome, normalize

_DIALOG = ':is(dialog[open],[role~="dialog"],[role~="alertdialog"]):not(dialog:not([open]))'
_ACTION = (
    ':is(button,input[type="submit" i],input[type="button" i],[role~="button"])'
    ':visible:not(:disabled,[aria-disabled="true"],[aria-disabled="true"] *,'
    '[aria-hidden="true"],[aria-hidden="true"] *,[inert],[inert] *)'
)
MATCH_DECIMAL_MINOR_UNITS = r"""(value, cents) => {
    if (typeof value !== 'string' || value.length > 32) return false;
    const match = /^\$?(0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)(?:\.([0-9]{1,2}))?$/.exec(value);
    if (!match || match[0] !== value) return false;
    const [, major, fractional = ''] = match;
    const minor = BigInt(major.replace(/,/g, '')) * 100n + BigInt(fractional.padEnd(2, '0'));
    return minor === BigInt(cents);
}"""
_CHECK = """(subject, binding) => {
    const action = binding.read_only ? null : subject;
    const dialogs = 'dialog[open],[role~="dialog"]:not(dialog:not([open])),' +
        '[role~="alertdialog"]:not(dialog:not([open]))';
    const visible = el => !!el.getClientRects().length &&
        getComputedStyle(el).visibility === 'visible' &&
        !el.closest('[aria-hidden="true"],[inert]');
    if (!subject?.isConnected || subject.ownerDocument.location.origin !== binding.origin) return false;
    const doc = subject.ownerDocument;
    const uniqueId = id => {
        const matches = doc.querySelectorAll('#' + CSS.escape(id));
        return matches.length === 1 ? matches[0] : null;
    };
    const hasTitle = dialog => {
        const labels = (dialog.getAttribute('aria-labelledby') || '').trim().split(/\\s+/).filter(Boolean);
        const names = labels.length ? labels.map(uniqueId) :
            [...dialog.querySelectorAll('h1,h2,h3,h4,h5,h6,[role~="heading"]')];
        const exact = names.filter(el => el && el.closest(dialogs) === dialog &&
            visible(el) && el.innerText?.trim() === binding.title);
        return exact.length === 1;
    };
    const visibleDialogs = [...doc.querySelectorAll(dialogs)].filter(visible);
    const titled = visibleDialogs.filter(hasTitle);
    const scope = binding.dialog_id === null ? titled[0] : uniqueId(binding.dialog_id);
    if (!scope || titled.length !== 1 || titled[0] !== scope) return false;
    if (binding.read_only && scope !== subject) return false;
    const allowedBodyFocus = binding.allow_body_focus && binding.operation === 'create' &&
        doc.activeElement === doc.body && visibleDialogs.length === 1 && visibleDialogs[0] === scope;
    if (binding.require_active_dialog && !scope.contains(doc.activeElement) && !allowedBodyFocus) return false;
    if (!binding.read_only) {
        if (action.closest(dialogs) !== scope || !visible(action) || action.matches(':disabled') ||
            action.closest('[aria-disabled="true"]')) return false;
        const role = action.getAttribute('role')?.trim().split(/\\s+/)[0] ||
            (action.localName === 'button' || (action.localName === 'input' &&
                ['submit', 'button'].includes(action.type)) ? 'button' : null);
        const actionName = el => {
            if (el.hasAttribute('aria-labelledby')) {
                const ids = el.getAttribute('aria-labelledby').trim().split(/\\s+/);
                const labels = ids.map(uniqueId);
                if (labels.some(label => !label || label.closest(dialogs) !== scope || !visible(label))) return null;
                return labels.map(label => label.innerText.trim()).join(' ');
            }
            return (el.getAttribute('aria-label') ||
                (el.localName === 'input' ? el.value : el.innerText))?.trim();
        };
        if (role !== binding.role || actionName(action) !== binding.action) return false;
        if (binding.action_focused !== null && action.matches(':focus') !== binding.action_focused) return false;
        if (binding.action_default !== null && action.matches(':default') !== binding.action_default) return false;
    }
    const seen = new Set();
    return binding.fields.every(field => {
        const anchor = field.element_id === null ? null : uniqueId(field.element_id);
        const candidates = field.child_input_role ? [...(anchor?.children ?? [])].filter(el =>
            el.localName === 'input' && el.getAttribute('role') === field.child_input_role && visible(el)
        ) : field.element_id === null ?
            [...scope.querySelectorAll('input[name],textarea[name],select[name]')].filter(el =>
                el.name === field.html_name && el.closest(dialogs) === scope && visible(el)) :
            [anchor];
        const el = candidates.length === 1 ? candidates[0] : null;
        if (!el || seen.has(el) || el.closest(dialogs) !== scope || !visible(el)) return false;
        if (field.require_editable && (el.matches(':disabled,[readonly]') ||
            el.closest('[aria-disabled="true"],[aria-readonly="true"]'))) return false;
        seen.add(el);
        if (typeof field.expected === 'boolean')
            return el.localName === 'input' && ['checkbox', 'radio'].includes(el.type) &&
                el.checked === field.expected;
        if (field.child_input_role && typeof field.expected === 'number')
            return (""" + MATCH_DECIMAL_MINOR_UNITS + """)(el.value, field.expected);
        return (el.localName === 'textarea' || (el.localName === 'select' && !el.multiple) ||
            (el.localName === 'input' &&
             ['text','number','email','tel','search','url','date','time','datetime-local','month','week']
                .includes(el.type))) && el.value === field.expected;
    });
}"""


@dataclass(frozen=True)
class FormFieldBinding:
    element_id: str | None
    expected: str | bool | int
    html_name: str | None = None
    require_editable: bool = True
    child_input_role: Literal["spinbutton"] | None = None


@dataclass(frozen=True)
class ApprovedFormAction:
    """Trusted binding for one current dedicated tab and open form dialog.

    The host provides the exact observed dialog title, approved field IDs or HTML names,
    and synthetic data. The dialog ID can be omitted for a uniquely titled dialog.
    A create binding may opt in to body focus when that dialog is the sole visible dialog.
    These bindings must never be deserialized from the worker's request.
    """

    tab: str
    origin: str
    dialog_id: str | None
    title: str
    action: str
    fields: tuple[FormFieldBinding, ...]
    operation: Literal["create", "edit"] = "create"
    role: Literal["button"] = "button"
    require_active_dialog: bool = True
    action_focused: bool | None = None
    action_default: bool | None = None
    allow_body_focus: bool = False


@dataclass(frozen=True)
class FormActionReceipt:
    status: Literal[
        "unsupported_binding", "not_actionable", "already_attempted", "dispatched", "unknown_effect",
    ]


def _valid_field(field: object) -> bool:
    if not isinstance(field, FormFieldBinding) or (field.element_id is None) == (field.html_name is None):
        return False
    identifier = field.element_id if field.html_name is None else field.html_name
    return (
        type(field.require_editable) is bool
        and isinstance(identifier, str) and 0 < len(identifier) <= 256 and identifier.isprintable()
        and (type(field.expected) is bool or isinstance(field.expected, str) and len(field.expected) <= 4096
             or (field.child_input_role is not None and type(field.expected) is int
                 and 0 <= field.expected <= 9_007_199_254_740_991))
        and (field.child_input_role is None or (
            field.child_input_role == "spinbutton" and field.element_id is not None
            and type(field.expected) in (str, int)
        ))
    )


def make_guarded_form_action(
    browser: Callable[[str, str, dict], object], binding: ApprovedFormAction,
) -> Callable[[], FormActionReceipt]:
    """Build a one-shot create dispatch. Callers verify effects independently.

    Native Browse cannot compare live control values as part of click. A fresh
    isolated preflight immediately precedes a strict scoped click on a dedicated
    tab. In-page changes between them are possible, so the caller must exclusively
    own this tab. Edit is unsupported without verified owned-row provenance.
    """
    return _guarded_form_operations(browser, binding, operation="create")[1]


def _guarded_form_operations(browser, binding, *, operation):
    """Internal exact form preflight and guarded click under a caller's authorization."""
    lock = Lock()
    attempted = False
    valid = (
        isinstance(binding, ApprovedFormAction)
        and binding.operation == operation and binding.role == "button"
        and all(isinstance(value, str) and 0 < len(value) <= 256 and value.isprintable()
                and value == value.strip()
                for value in (binding.tab, binding.origin, binding.title, binding.action))
        and (binding.dialog_id is None or (
            isinstance(binding.dialog_id, str) and 0 < len(binding.dialog_id) <= 256
            and binding.dialog_id.isprintable() and binding.dialog_id == binding.dialog_id.strip()
        ))
        and isinstance(binding.fields, tuple) and 1 <= len(binding.fields) <= 32
        and type(binding.require_active_dialog) is bool
        and type(binding.allow_body_focus) is bool
        and (operation == "create" or not binding.allow_body_focus)
        and all(value is None or type(value) is bool
                for value in (binding.action_focused, binding.action_default))
        and all(_valid_field(field) for field in binding.fields)
        and len({(field.element_id, field.html_name) for field in binding.fields}) == len(binding.fields)
    )
    if not valid:
        return (lambda: False), (lambda: FormActionReceipt("unsupported_binding"))

    title = f"internal:text={json.dumps(binding.title, ensure_ascii=False)}s"
    title += " >> internal:and=" + json.dumps("css=:visible")
    dialog_id = f"[id={json.dumps(binding.dialog_id, ensure_ascii=False)}]" if binding.dialog_id is not None else ""
    scope = f'css={_DIALOG}{dialog_id}:visible >> internal:has={json.dumps(title, ensure_ascii=False)}'
    if binding.dialog_id is None:
        duplicate = json.dumps(scope + " >> nth=1", ensure_ascii=False)
        scope = f"css:light=:root >> internal:has-not={duplicate} >> {scope}"
    label = json.dumps(binding.action, ensure_ascii=False)
    action_guard = _ACTION
    if binding.action_focused is not None:
        action_guard += ":focus" if binding.action_focused else ":not(:focus)"
    if binding.action_default is not None:
        action_guard += ":default" if binding.action_default else ":not(:default)"
    selector = f'{scope} >> role=button[name={label}s] >> internal:and={json.dumps("css=" + action_guard)}'
    arguments = asdict(binding)

    def read(tool, args):
        try:
            raw = browser(binding.tab, tool, args)
        except (RuntimeError, ValueError, OSError):
            return None
        if normalize(raw) is not Outcome.RETURNED or len(raw["content"]) != 1:
            return None
        item = raw["content"][0]
        text = item.get("text")
        if item.get("type") != "text" or not isinstance(text, str) or len(text) > 4096:
            return None
        try:
            return json.loads(text)
        except (ValueError, RecursionError):
            return None

    def check(*, action=False) -> bool:
        return read("eval", {
            "world": "isolated", "selector": selector if action else scope, "expression": _CHECK,
            "arg": {**arguments, "read_only": not action},
        }) is True

    def dispatch() -> FormActionReceipt:
        nonlocal attempted
        with lock:
            if attempted:
                return FormActionReceipt("already_attempted")
            if not check(action=True):
                return FormActionReceipt("not_actionable")
            attempted = True
            click = read("click", {"selector": selector, "timeout": 1000, "clickCount": 1})
            if isinstance(click, dict) and isinstance(click.get("clicked"), str) and click["clicked"]:
                return FormActionReceipt("dispatched")
            return FormActionReceipt("unknown_effect")

    return check, dispatch
