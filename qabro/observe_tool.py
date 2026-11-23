"""Expose bounded browser observations and host-approved controls."""

import json
from collections import Counter
from collections.abc import Callable, Mapping, Set
from dataclasses import asdict
from time import monotonic, sleep

from qabro.observation_filter import FilteredObservation, filter_observations


OBSERVE_TOOL = {
    "name": "browser_observe",
    "description": "Read approved visible control labels and states in the assigned tab.",
    "inputSchema": {
        "type": "object",
        "properties": {"action": {"const": "observe"}},
        "required": ["action"],
        "additionalProperties": False,
    },
}

OBSERVE_AND_CLICK_TOOL = {
    **OBSERVE_TOOL,
    "description": "Read approved controls or click an approved, visible non-submit button.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "action": {"enum": ["observe", "click"]},
            "label": {"type": "string", "description": "Exact approved button label for click."},
        },
        "required": ["action"],
        "additionalProperties": False,
    },
}

OBSERVE_CLICK_AND_ROWS_TOOL = {
    **OBSERVE_AND_CLICK_TOOL,
    "description": "Read approved controls, click an approved button, or count visible owned rows.",
    "inputSchema": {
        **OBSERVE_AND_CLICK_TOOL["inputSchema"],
        "properties": {
            **OBSERVE_AND_CLICK_TOOL["inputSchema"]["properties"],
            "action": {"enum": ["observe", "click", "observe_owned_rows"]},
        },
    },
}

OBSERVE_CLICK_ROWS_AND_WAIT_TOOL = {
    **OBSERVE_CLICK_AND_ROWS_TOOL,
    "description": "Read approved controls, click an approved button, count visible owned rows, or wait for a dialog state.",
    "inputSchema": {
        **OBSERVE_CLICK_AND_ROWS_TOOL["inputSchema"],
        "properties": {
            **OBSERVE_CLICK_AND_ROWS_TOOL["inputSchema"]["properties"],
            "action": {"enum": ["observe", "click", "observe_owned_rows", "wait_for_dialog_state"]},
            "state": {"enum": ["visible", "hidden"], "description": "Requested dialog state for wait_for_dialog_state."},
        },
    },
}

OBSERVE_DIALOG_FIELDS_TOOL = {
    **OBSERVE_CLICK_ROWS_AND_WAIT_TOOL,
    "description": "Observe approved controls and dialog states, click approved buttons, count owned rows, or use approved dialog field parameters.",
    "inputSchema": {
        **OBSERVE_CLICK_ROWS_AND_WAIT_TOOL["inputSchema"],
        "properties": {
            **OBSERVE_CLICK_ROWS_AND_WAIT_TOOL["inputSchema"]["properties"],
            "action": {"enum": [
                "observe", "click", "observe_owned_rows", "wait_for_dialog_state",
                "fill_dialog_field", "read_dialog_field", "blur_dialog_field",
                "observe_dialog_kinds", "observe_dialog_text", "observe_dialog_action", "click_dialog_action",
            ]},
            "label": {"type": "string", "description": "Exact approved label for a click, dialog action observation, or field action."},
            "semantic": {"type": "string", "description": "For field actions only, a field_semantics token returned by observe. Use instead of label."},
            "parameter": {"type": "string", "description": "Host-assigned value identifier for the field."},
            "text": {"type": "string", "description": "Exact host-approved dialog text for observe_dialog_text or click_dialog_action."},
        },
    },
}

_DIALOG_SELECTOR = ':is(dialog[open],[role~="dialog"],[role~="alertdialog"]):visible'
_TEXT_INPUTS = (
    'textarea,input:not([type]),input[type="text" i],input[type="email" i],'
    'input[type="tel" i],input[type="url" i],input[type="search" i]'
)
_DIALOG_TEXT_FIELD = (
    f'{_DIALOG_SELECTOR} :is({_TEXT_INPUTS}):visible'
    ':not(:disabled,[readonly],[aria-disabled="true"],[aria-disabled="true"] *,'
    '[aria-hidden="true"],[aria-hidden="true"] *,[inert],[inert] *)'
)
_SEMANTIC_FIELD_SELECTORS = {
    **{f"type:{name}": f'input[type="{name}" i]' for name in ("email", "tel", "url", "search")},
    **{f"autocomplete:{name}": f'[autocomplete="{name}" i]' for name in (
        "name", "given-name", "additional-name", "family-name", "nickname",
        "username", "email", "tel", "url", "organization", "organization-title",
    )},
}
_DIALOG_FIELD_CHECK = f"""(el, query) => {{
    const dialog = el.closest('dialog,[role~="dialog"],[role~="alertdialog"]');
    if (!dialog || (dialog.tagName === 'DIALOG' && !dialog.open) ||
        !dialog.getClientRects().length || getComputedStyle(dialog).visibility !== 'visible' ||
        !el.matches('{_TEXT_INPUTS}') || el.disabled || el.readOnly ||
        el.closest('[aria-disabled="true"],[aria-hidden="true"],[inert]') ||
        !el.getClientRects().length || getComputedStyle(el).visibility !== 'visible') return null;
    return query.check === 'focused' ? el.matches(':focus') : el.value === query.value;
}}"""

_DIALOG_TEXT_MATCHES = """expected => {
    const dialogs = 'dialog[open],[role~="dialog"],[role~="alertdialog"]';
    const visible = el => !!el.getClientRects().length &&
        getComputedStyle(el).visibility === 'visible' &&
        !el.closest('[aria-hidden="true"],[inert]');
    let visibleDialogs = 0;
    const matches = [];
    for (const dialog of document.querySelectorAll(dialogs)) {
        if (!visible(dialog)) continue;
        visibleDialogs++;
        for (const el of dialog.querySelectorAll('*')) {
            if (el.closest(dialogs) === dialog && visible(el) && el.innerText?.trim() === expected) {
                matches.push(dialog);
                if (matches.length === 2) return {visibleDialogs, matches};
                break;
            }
        }
    }
    return {visibleDialogs, matches};
}"""

_DIALOG_TEXT_EVIDENCE = """(_, expected) => {
    const {visibleDialogs, matches} = (""" + _DIALOG_TEXT_MATCHES + """)(expected);
    return visibleDialogs ? ['none', 'one', 'multiple'][matches.length] : 'no_dialog';
}"""

_DIALOG_ACTION_GUARD = (
    f'{_DIALOG_SELECTOR} :is(button,[role~="button"],input[type="button" i],'
    'input[type="submit" i],input[type="reset" i]):visible'
    ':not([aria-hidden="true"],[aria-hidden="true"] *,[inert],[inert] *)'
)
_DIALOG_ACTION_ENABLED = """el => {
    const dialog = el.closest('dialog,[role~="dialog"],[role~="alertdialog"]');
    if (!dialog || (dialog.tagName === 'DIALOG' && !dialog.open) ||
        !dialog.getClientRects().length || getComputedStyle(dialog).visibility !== 'visible' ||
        !el.getClientRects().length || getComputedStyle(el).visibility !== 'visible' ||
        el.closest('[aria-hidden="true"],[inert]')) return null;
    return !el.matches(':disabled') && !el.closest('[aria-disabled="true"]');
}"""

_BUTTON_GUARD = (
    'button:visible:not(:disabled,[form],[type="submit" i],[type="reset" i],'
    'form button:not([type="button" i]),tbody *,tr *,[role~="row"] *,[role~="rowgroup"] *,'
    '[aria-disabled="true"],[aria-disabled="true"] *,[aria-hidden="true"],[aria-hidden="true"] *,'
    '[inert],[inert] *)'
)

_BUTTON_CHECK = """el => el.tagName === 'BUTTON' && !el.matches(':disabled') &&
    (!el.form || el.type === 'button') && el.type !== 'reset' &&
    !el.closest('tbody,tr,[role~=row],[role~=rowgroup],[aria-disabled=true],[aria-hidden=true],[inert]') &&
    !!el.getClientRects().length && getComputedStyle(el).visibility === 'visible'"""

_DIALOG_CLICK_CHECK = """(el, expected) => {
    const {matches} = (""" + _DIALOG_TEXT_MATCHES + """)(expected);
    return matches.length === 1 &&
        el.closest('dialog[open],[role~="dialog"],[role~="alertdialog"]') === matches[0] &&
        (""" + _BUTTON_CHECK + """)(el);
}"""

_OWNED_ROWS = """(_, identity) => {
    const rowSelector = 'tr,[role~="row"]';
    const cellSelector = 'td,th,[role~="cell"],[role~="gridcell"],[role~="rowheader"]';
    const visible = el => !!el.getClientRects().length &&
        getComputedStyle(el).visibility === 'visible' &&
        !el.closest('[aria-hidden="true"],[inert]');
    function addImmediateText(element, texts) {
        let segment = '';
        for (const child of element.childNodes) {
            if (child.nodeType === 3) segment += child.nodeValue || '';
            else if (child.nodeType !== 8) {
                if (segment) texts.add(segment.trim());
                segment = '';
            }
        }
        if (segment) texts.add(segment.trim());
    }
    let matches = 0;
    for (const row of document.querySelectorAll(rowSelector)) {
        if (!visible(row) || row.closest('thead')) continue;
        const cells = [...row.querySelectorAll(cellSelector)].filter(cell =>
            cell.closest(rowSelector) === row && visible(cell) &&
            !cell.parentElement.closest(cellSelector));
        const candidates = identity.map(() => []);
        for (const [index, cell] of cells.entries()) {
            const texts = new Set([cell.innerText?.trim()]);
            addImmediateText(cell, texts);
            for (const element of cell.querySelectorAll('*')) {
                if (element.closest(rowSelector) !== row || !visible(element)) continue;
                if (!element.childElementCount) texts.add(element.innerText?.trim());
                else addImmediateText(element, texts);
            }
            identity.forEach((value, i) => {
                if (texts.has(value)) candidates[i].push(index);
            });
        }
        const allocated = new Map();
        function match(valueIndex, visited) {
            for (const cellIndex of candidates[valueIndex]) {
                if (visited.has(cellIndex)) continue;
                visited.add(cellIndex);
                if (!allocated.has(cellIndex) || match(allocated.get(cellIndex), visited)) {
                    allocated.set(cellIndex, valueIndex);
                    return true;
                }
            }
            return false;
        }
        if (identity.every((_, index) => match(index, new Set())) && ++matches === 2) return 'multiple';
    }
    return matches === 1 ? 'one' : 'none';
}"""

_EXPRESSION = r"""(_, configuration) => {
    const {vocabulary, semanticSelectors = {}, textInputs} =
        Array.isArray(configuration) ? {vocabulary: configuration} : configuration;
    const allowed = new Set(vocabulary);
    const controls = [];
    const selectors = [
        'button', 'input', 'textarea', 'select', 'a[href]', 'dialog', 'table',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', '[role]',
    ].join(',');
    const tags = {BUTTON: 'button', TEXTAREA: 'textbox', SELECT: 'combobox',
                  A: 'link', DIALOG: 'dialog', TABLE: 'table',
                  H1: 'heading', H2: 'heading', H3: 'heading',
                  H4: 'heading', H5: 'heading', H6: 'heading'};
    const inputRoles = {button: 'button', submit: 'button', reset: 'button',
                        checkbox: 'checkbox', radio: 'radio', search: 'searchbox',
                        number: 'spinbutton'};
    const roles = new Set(['alert', 'button', 'checkbox', 'combobox', 'dialog', 'heading',
        'link', 'listbox', 'option', 'radio', 'searchbox', 'spinbutton', 'status', 'table',
        'switch', 'tab', 'textbox']);
    const booleans = ['checked', 'disabled', 'expanded', 'invalid', 'pressed',
                      'readonly', 'required', 'selected'];
    for (const el of document.querySelectorAll(selectors)) {
        if (el.type === 'hidden' || el.closest('tbody,tr,[role=row],[aria-hidden=true],[inert]') ||
            !el.getClientRects().length || getComputedStyle(el).visibility !== 'visible') continue;
        const explicitRole = el.getAttribute('role')?.trim().split(/\s+/)[0];
        const role = explicitRole === 'alertdialog' ? 'dialog' : explicitRole ||
            (el.tagName === 'INPUT' ? (inputRoles[el.type] || 'textbox') : tags[el.tagName]);
        if (!roles.has(role)) continue;
        const labelReferences = (el.getAttribute('aria-labelledby') ?? '').trim().split(/\s+/)
            .filter(Boolean).map(id => el.getRootNode().getElementById(id)?.textContent);
        const label = [
            labelReferences.filter(Boolean).join(' '), ...labelReferences,
            el.getAttribute('aria-label'), ...[...(el.labels ?? [])].map(label => label.textContent),
            el.getAttribute('placeholder'),
            role === 'table' ? el.caption?.textContent : null,
            ['button', 'link', 'tab', 'option', 'alert', 'status', 'heading'].includes(role)
                ? el.textContent : null,
        ].map(text => text?.trim()).find(text => allowed.has(text)) ?? null;
        const state = {visible: true, focused: document.activeElement === el};
        const dialog = el.parentElement?.closest('dialog,[role~="dialog"],[role~="alertdialog"]');
        if (role === 'heading') {
            state.in_dialog = !!dialog;
        }
        for (const key of booleans) {
            const aria = el.getAttribute('aria-' + key);
            const native = el[key === 'readonly' ? 'readOnly' : key];
            if (aria === 'true' || aria === 'false') state[key] = aria === 'true';
            else if (typeof native === 'boolean') state[key] = native;
        }
        const control = {role, label, state};
        if (textInputs && dialog && (dialog.tagName !== 'DIALOG' || dialog.open) &&
            dialog.getClientRects().length && getComputedStyle(dialog).visibility === 'visible' &&
            el.matches(textInputs) && !el.matches(':disabled,[readonly]') &&
            !el.closest('[aria-disabled="true"]')) {
            const semantics = Object.entries(semanticSelectors)
                .filter(([, selector]) => el.matches(selector)).map(([token]) => token);
            if (semantics.length) control.field_semantics = semantics;
        }
        controls.push(control);
        // Preserve the overflow signal for the host filter.
        if (controls.length === 129) break;
    }
    return controls;
}"""

_WAIT_FOR_DIALOG = """async (_, {visible, milliseconds}) => {
    const observe = (""" + _EXPRESSION + """);
    const deadline = performance.now() + milliseconds;
    while (true) {
        const controls = observe(null, []);
        if (controls.length > 128) return 'out_of_scope';
        const remaining = deadline - performance.now();
        if (remaining <= 0) return 'timeout';
        if (controls.some(control => control.role === 'dialog') === visible) return 'matched';
        await new Promise(resolve => setTimeout(resolve, Math.min(100, remaining)));
    }
}"""


def _read_browser_json(browser, tab: str, tool: str, arguments: dict) -> tuple[str, object]:
    try:
        raw = browser(tab, tool, arguments)
    except (OSError, RuntimeError, ValueError):
        return "unavailable", None
    if not isinstance(raw, dict) or raw.get("isError"):
        return "unavailable", None
    content = raw.get("content")
    if not isinstance(content, list) or len(content) != 1 or not isinstance(content[0], dict):
        return "malformed", None
    text = content[0].get("text")
    if content[0].get("type") != "text" or not isinstance(text, str):
        return "malformed", None
    if len(text) > 65_536:
        return "out_of_scope", None
    try:
        return "ok", json.loads(text)
    except (ValueError, RecursionError):
        return "malformed", None


def make_observe_dispatch(
    browser: Callable[[str, str, dict], object], *, tab: str, allowed_labels: Set[str],
    clickable_labels: Set[str] = frozenset(),
    owned_identity: tuple[str, ...] = (),
    dialog_wait_seconds: float = 0,
    dialog_fields: Mapping[str, Mapping[str, str]] | None = None,
    dialog_field_semantics: Mapping[str, str] | None = None,
    native_dialog_wait: bool = False,
    dialog_texts: Set[str] = frozenset(),
    dialog_action_labels: Set[str] = frozenset(),
    dialog_click_actions: Mapping[str, Set[str]] | None = None,
) -> Callable[[object], dict]:
    """Bind observations and approved button clicks to a host-owned tab."""
    vocabulary = frozenset(allowed_labels)
    if not all(isinstance(label, str) for label in vocabulary):
        raise ValueError("Expected a trusted vocabulary of strings")
    clickable = frozenset(clickable_labels)
    if not clickable <= vocabulary or any(
        not label.strip() or ">>" in label or not label.isprintable() for label in clickable
    ):
        raise ValueError("Expected approved clickable labels from the trusted vocabulary")
    observable_actions = frozenset(dialog_action_labels)
    if not observable_actions <= vocabulary or any(
        not label.strip() or ">>" in label or not label.isprintable() for label in observable_actions
    ):
        raise ValueError("Expected approved dialog action labels from the trusted vocabulary")
    messages = frozenset(dialog_texts)
    if any(
        not isinstance(message, str) or not message.strip() or message != message.strip() or len(message) > 1024
        for message in messages
    ):
        raise ValueError("Expected bounded exact dialog text")
    dialog_clicks = {}
    for message, buttons in (dialog_click_actions or {}).items():
        if (message not in messages or not message.isprintable() or ">>" in message
                or not isinstance(buttons, Set) or not buttons <= vocabulary
                or any(not label.strip() or ">>" in label or not label.isprintable() for label in buttons)):
            raise ValueError("Expected approved dialog text and non-empty action labels")
        dialog_clicks[message] = frozenset(buttons)
    identity = tuple(owned_identity)
    if isinstance(owned_identity, str) or len(identity) > 4 or any(
        not isinstance(value, str) or not value.strip() for value in identity
    ):
        raise ValueError("Expected up to four trusted owned record identifiers")
    if not 0 <= dialog_wait_seconds <= 5:
        raise ValueError("Expected a dialog wait deadline of up to five seconds")
    fields = {label: dict(values) for label, values in (dialog_fields or {}).items()}
    if any(
        label not in vocabulary or not label.strip() or ">>" in label or not label.isprintable()
        or any(
            not isinstance(key, str) or not key.strip() or len(key) > 80
            or not isinstance(value, str) or len(value) > 1024
            for key, value in values.items()
        )
        for label, values in fields.items()
    ):
        raise ValueError("Expected approved labels and bounded host field parameters")
    semantics = dict(dialog_field_semantics or {})
    semantic_selectors = {}
    for token, label in semantics.items():
        if not isinstance(token, str) or not isinstance(label, str) or label not in fields:
            raise ValueError("Expected field semantics bound to approved field parameters")
        selector = _SEMANTIC_FIELD_SELECTORS.get(token)
        if selector is None:
            name = token.removeprefix("name:")
            if name == token or not name.strip() or not name.isprintable() or ">>" in name or len(name) > 128:
                raise ValueError("Expected a standard semantic token or a valid HTML name")
            selector = f"[name={json.dumps(name, ensure_ascii=False)}]"
        semantic_selectors[token] = selector
    observed_semantics: frozenset[str] = frozenset()

    def observe() -> dict:
        configuration = sorted(vocabulary)
        if semantic_selectors:
            configuration = {"vocabulary": configuration, "semanticSelectors": semantic_selectors, "textInputs": _TEXT_INPUTS}
        status, payload = _read_browser_json(browser, tab, "eval", {
            "world": "isolated", "expression": _EXPRESSION, "arg": configuration,
        })
        if status != "ok":
            return {"status": status, "controls": ()}
        return asdict(filter_observations(
            payload, allowed_labels=vocabulary, allowed_field_semantics=semantic_selectors.keys(),
        ))

    def count_dom_dialogs() -> tuple[str, int]:
        observation = observe()
        if observation["status"] != "ok":
            return observation["status"], 0
        controls = observation["controls"]
        if any(control["state"].get("visible") is not True for control in controls):
            return "malformed", 0
        return "ok", sum(control["role"] == "dialog" for control in controls)

    def dispatch(request: object) -> dict:
        nonlocal observed_semantics
        if request == {"action": "observe"}:
            observation = observe()
            counts = Counter(token for control in observation["controls"] for token in control.get("field_semantics", ()))
            observed_semantics = frozenset(token for token, count in counts.items() if count == 1)
            for control in observation["controls"]:
                tokens = tuple(token for token in control.pop("field_semantics", ()) if token in observed_semantics)
                if tokens:
                    control["field_semantics"] = tokens
            return observation
        if request == {"action": "observe_dialog_kinds"}:
            status, payload = _read_browser_json(browser, tab, "dialog", {"action": "status"})
            if status != "ok":
                return {"status": status}
            if not isinstance(payload, dict) or "dialog" not in payload:
                return {"status": "malformed"}
            native = payload["dialog"]
            if native is not None:
                if not isinstance(native, dict) or native.get("type") not in ("alert", "confirm", "prompt", "beforeunload"):
                    return {"status": "malformed"}
                return {"status": "ok", "native_pending": True, "visible_dom_dialogs": "unverified"}
            status, count = count_dom_dialogs()
            if status != "ok":
                return {"status": status, "native_pending": False}
            return {"status": "ok", "native_pending": False,
                    "visible_dom_dialogs": ("none", "one", "multiple")[min(count, 2)]}
        if isinstance(request, dict) and request.get("action") == "wait_for_dialog_state":
            if request.keys() != {"action", "state"} or request["state"] not in ("visible", "hidden") or not dialog_wait_seconds:
                return {"status": "out_of_scope"}
            deadline = monotonic() + dialog_wait_seconds
            visible = request["state"] == "visible"
            if native_dialog_wait and dialog_wait_seconds >= 0.5:
                # Keep time for an independent observation and for a condition changing near the deadline.
                milliseconds = int(dialog_wait_seconds * 1000) - 250
                status, signal = _read_browser_json(browser, tab, "eval", {
                    "world": "isolated", "expression": _WAIT_FOR_DIALOG,
                    "timeout": milliseconds + 100,
                    "arg": {"visible": visible, "milliseconds": milliseconds},
                })
                if status != "ok":
                    return {"status": status}
                if signal == "out_of_scope":
                    return {"status": "out_of_scope"}
                if signal not in ("matched", "timeout"):
                    return {"status": "malformed"}
            while monotonic() < deadline:
                status, count = count_dom_dialogs()
                if status != "ok":
                    return {"status": status}
                remaining = deadline - monotonic()
                if remaining <= 0:
                    break
                if bool(count) == visible:
                    return {"status": "ok", "state": request["state"]}
                sleep(min(0.1, remaining))
            return {"status": "timeout"}
        if request == {"action": "observe_owned_rows"}:
            if not identity:
                return {"status": "out_of_scope"}
            status, matches = _read_browser_json(browser, tab, "eval", {
                "world": "isolated", "expression": _OWNED_ROWS, "arg": list(identity),
            })
            if status != "ok":
                return {"status": status}
            if matches not in ("none", "one", "multiple"):
                return {"status": "malformed"}
            return {"status": "ok", "visible_matches": matches}
        if isinstance(request, dict) and request.get("action") == "observe_dialog_text":
            text = request.get("text")
            if request.keys() != {"action", "text"} or not isinstance(text, str) or text not in messages:
                return {"status": "out_of_scope"}
            status, matches = _read_browser_json(browser, tab, "eval", {
                "world": "isolated", "expression": _DIALOG_TEXT_EVIDENCE, "arg": text,
            })
            if status != "ok":
                return {"status": status}
            if matches == "no_dialog":
                return {"status": "not_actionable"}
            if matches not in ("none", "one", "multiple"):
                return {"status": "malformed"}
            return {"status": "ok", "visible_matches": matches}
        if isinstance(request, dict) and request.get("action") == "observe_dialog_action":
            label = request.get("label")
            if request.keys() != {"action", "label"} or not isinstance(label, str) or label not in observable_actions:
                return {"status": "out_of_scope"}
            name = json.dumps(label, ensure_ascii=False)
            guard = json.dumps("css=" + _DIALOG_ACTION_GUARD)
            selector = f"role=button[name={name}s] >> internal:and={guard}"
            status, enabled = _read_browser_json(browser, tab, "eval", {
                "world": "isolated", "expression": _DIALOG_ACTION_ENABLED, "selector": selector,
            })
            if status != "ok" or type(enabled) is not bool:
                return {"status": "not_actionable"}
            return {"status": "ok", "enabled": enabled}
        if isinstance(request, dict) and request.get("action") in (
            "fill_dialog_field", "read_dialog_field", "blur_dialog_field",
        ):
            blur = request["action"] == "blur_dialog_field"
            keys = {"action"} if blur else {"action", "parameter"}
            token = request.get("semantic")
            if request.keys() == keys | {"semantic"}:
                if not isinstance(token, str) or token not in observed_semantics:
                    return {"status": "out_of_scope"}
                label = semantics[token]
            elif request.keys() == keys | {"label"}:
                label = request["label"]
            else:
                return {"status": "out_of_scope"}
            if not isinstance(label, str) or label not in fields:
                return {"status": "out_of_scope"}
            if blur:
                query = {"check": "focused"}
            else:
                parameter = request["parameter"]
                if not isinstance(parameter, str) or parameter not in fields[label]:
                    return {"status": "out_of_scope"}
                value = fields[label][parameter]
                query = {"check": "value", "value": value}
            guard = json.dumps("css=" + _DIALOG_TEXT_FIELD)
            if token is not None:
                selector = f"css={semantic_selectors[token]} >> internal:and={guard}"
            else:
                name = json.dumps(label, ensure_ascii=False)
                by_label = json.dumps(f"internal:label={name}s", ensure_ascii=False)
                by_placeholder = json.dumps(f"internal:attr=[placeholder={name}s]", ensure_ascii=False)
                selector = (
                    f"role=textbox[name={name}s] >> internal:or={by_label} "
                    f">> internal:or={by_placeholder} >> internal:and={guard}"
                )
            arguments = {
                "selector": selector, "world": "isolated", "expression": _DIALOG_FIELD_CHECK, "arg": query,
            }
            status, matches = _read_browser_json(browser, tab, "eval", arguments)
            if status != "ok" or type(matches) is not bool:
                return {"status": "not_actionable"}
            if blur:
                if matches is not True:
                    return {"status": "not_actionable"}
                status, payload = _read_browser_json(browser, tab, "press", {"selector": selector, "key": "Tab"})
                if status != "ok" or not isinstance(payload, dict) or payload.get("pressed") != ["Tab"]:
                    return {"status": "unknown_effect"}
                status, focused = _read_browser_json(browser, tab, "eval", arguments)
                if status != "ok" or type(focused) is not bool:
                    return {"status": "unknown_effect"}
                return {"status": "ok", "blurred": not focused}
            if request["action"] == "fill_dialog_field":
                status, _ = _read_browser_json(browser, tab, "fill", {"selector": selector, "value": value})
                if status != "ok":
                    return {"status": "unknown_effect"}
                status, matches = _read_browser_json(browser, tab, "eval", arguments)
                if status != "ok" or type(matches) is not bool:
                    return {"status": "unknown_effect"}
            return {"status": "ok", "matches": matches}
        if isinstance(request, dict) and (
            request.get("action") == "click_dialog_action"
            or (request.keys() == {"action", "label"} and request["action"] == "click")
        ):
            scoped_click = request["action"] == "click_dialog_action"
            if scoped_click and request.keys() != {"action", "label", "text"}:
                return {"status": "out_of_scope"}
            label = request["label"]
            text = request.get("text")
            if scoped_click and not isinstance(text, str):
                return {"status": "out_of_scope"}
            permitted = dialog_clicks.get(text, frozenset()) if scoped_click else clickable
            if not isinstance(label, str) or label not in permitted:
                return {"status": "out_of_scope"}
            name = json.dumps(label, ensure_ascii=False)
            guard = json.dumps("css=" + _BUTTON_GUARD)
            selector = f"role=button[name={name}s] >> internal:and={guard}"
            check = {"world": "isolated", "expression": _BUTTON_CHECK}
            if scoped_click:
                text_query = f"internal:text={json.dumps(text, ensure_ascii=False)}s"
                visible_text = text_query + " >> internal:and=" + json.dumps("css=:visible")
                scope = f"css={_DIALOG_SELECTOR} >> internal:has={json.dumps(visible_text, ensure_ascii=False)}"
                selector = f"{scope} >> {selector}"
                check.update(expression=_DIALOG_CLICK_CHECK, arg=text)
            status, eligible = _read_browser_json(browser, tab, "eval", {**check, "selector": selector})
            if status != "ok" or eligible is not True:
                return {"status": "not_actionable"}
            observed_semantics = frozenset()
            # Native click resolves the same strict predicate again before pointer dispatch.
            status, response = _read_browser_json(browser, tab, "click", {"selector": selector})
            if status != "ok" or not isinstance(response, dict) or not isinstance(response.get("clicked"), str):
                return {"status": "unknown_effect"}
            return {"status": "dispatched"}
        return asdict(FilteredObservation("out_of_scope"))

    return dispatch
