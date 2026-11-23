"""Compile an explorer's declarative evidence query to a bounded observation."""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Literal

from qabro.browser import Outcome, normalize

_INPUTS = {
    "scope": {"type": "dynamic_scope_handle"},
    "label": {"type": "text"},
    "role": {"type": "optional_role_matcher"},
    "expected": {"type": "optional_typed_value"},
}
_PREDICATES = [
    {"type": "unique_current_label_in_scope"},
    {"type": "nonempty_explicit_html_link"},
    {"type": "unique_in_scope_noneditable_linked_wrapper"},
    {"type": "unique_visible_enabled_editable_descendant_matching_role_when_given"},
]
_OUTPUT = {
    "mode": "read_only",
    "handle": "ephemeral",
    "match_result": "unique_match_or_no_match",
    "value": {
        "type": "optional_typed_observation",
        "independent_when_expected_requested": True,
        "equality": "typed",
        "never_asserted_by_discovery": True,
    },
}
_SHAPE = {
    "status": "CANDIDATE_UNVALIDATED",
    "inputs": _INPUTS,
    "predicates": _PREDICATES,
    "abort_on": ["ambiguity", "missing_link", "stale_scope", "budget_exhaustion"],
    "output": _OUTPUT,
    "runtime_safety_policies": {"type": "prospective_guards", "are_observations": False},
}
_ROLES = frozenset({"textbox", "searchbox", "spinbutton", "combobox", "listbox"})
_STATUSES = frozenset({
    "unique_match", "no_match", "ambiguous", "missing_link", "stale_scope", "budget_exhausted",
})
_UNSET = object()
_HANDLE_TTL_SECONDS = 8
_NATIVE_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}")

_PROJECT = """(scope, query) => {
    const visible = el => !!el.getClientRects().length &&
        getComputedStyle(el).visibility === 'visible' &&
        !el.closest('[aria-hidden="true"],[inert]');
    if (!scope?.isConnected || scope.ownerDocument.location.origin !== query.origin ||
        !visible(scope) || scope.matches('dialog:not([open])')) return 'stale_scope';

    const editable = el => (
        (el.localName === 'input' &&
            ['text', 'email', 'tel', 'url', 'search', 'number'].includes(el.type)) ||
        el.localName === 'textarea' || el.localName === 'select'
    ) && !el.matches(':disabled,[readonly]') &&
        !el.closest('[aria-disabled="true"],[aria-readonly="true"]') && visible(el);

    const role = el => {
        if (el.hasAttribute('role')) return el.getAttribute('role').trim().split(/\\s+/)[0];
        if (el.localName === 'select') return el.multiple || el.size > 1 ? 'listbox' : 'combobox';
        if (el.localName === 'input' && el.type === 'search') return 'searchbox';
        if (el.localName === 'input' && el.type === 'number') return 'spinbutton';
        return 'textbox';
    };
    // Bound the entire local traversal, including non-candidates between candidates.
    const walker = scope.ownerDocument.createTreeWalker(scope, NodeFilter.SHOW_ELEMENT);
    const elements = [];
    for (let el = walker.nextNode(); el; el = walker.nextNode()) {
        if (elements.length === query.budget) return 'budget_exhausted';
        elements.push(el);
    }
    const labels = elements.filter(el =>
        el.localName === 'label' && visible(el) && el.innerText.trim() === query.label);
    if (!labels.length) return 'no_match';
    if (labels.length !== 1) return 'ambiguous';

    const id = labels[0].htmlFor;
    if (!id.trim()) return 'missing_link';
    const links = elements.filter(el => el.id === id);
    if (links.length > 1) return 'ambiguous';
    const linked = links[0];
    if (!linked) return 'missing_link';
    if (scope.ownerDocument.querySelectorAll('#' + CSS.escape(id)).length > 1) return 'ambiguous';
    if (scope.ownerDocument.getElementById(id) !== linked) return 'missing_link';
    if (!visible(linked) || linked.matches('input,textarea,select,button,[contenteditable]') ||
        linked.isContentEditable) return 'no_match';
    const matches = elements.filter(el =>
        el !== linked && linked.contains(el) && editable(el) &&
        (query.role === null || role(el) === query.role));
    if (matches.length !== 1) return matches.length ? 'ambiguous' : 'no_match';
    if (!query.captureIdentity) return 'unique_match';
    const field = matches[0];
    if (!field.id || scope.ownerDocument.querySelectorAll('#' + CSS.escape(field.id)).length !== 1)
        return 'unique_match';
    return {
        status: 'unique_match', wrapper: id, field: field.id,
        tag: field.localName, type: field.type, role: role(field),
    };
}"""


@dataclass(frozen=True)
class ApprovedQueryScope:
    """Host-owned binding for the current dispatch. Never deserialize from worker input."""

    tab: str
    origin: str
    selector: str
    label: str
    role: str | None = None
    generation: str | None = None


@dataclass(frozen=True)
class CompiledEvidenceQuery:
    max_candidates: int


@dataclass(frozen=True)
class EphemeralEvidence:
    """One observation only. No reusable locator or assertion is exposed."""

    status: Literal[
        "unique_match", "no_match", "ambiguous", "missing_link", "stale_scope",
        "budget_exhausted", "read_failed", "value_observation_unsupported",
    ]


def compile_evidence_query(proposal: object) -> CompiledEvidenceQuery:
    """Accept only the bounded declarative query operators the runtime implements."""
    if not isinstance(proposal, dict) or proposal.keys() != {*_SHAPE, "scan_budget", "provenance"}:
        raise ValueError("Unsupported evidence query shape")
    try:
        same_operators = all(json.dumps(proposal[key], sort_keys=True) ==
                             json.dumps(value, sort_keys=True) for key, value in _SHAPE.items())
    except (TypeError, ValueError, RecursionError):
        same_operators = False
    if not same_operators:
        raise ValueError("Unsupported evidence query operator")
    budget = proposal["scan_budget"]
    if (
        not isinstance(budget, dict) or budget.keys() != {"type", "max_candidates"}
        or budget["type"] != "finite" or type(budget["max_candidates"]) is not int
        or not 1 <= budget["max_candidates"] <= 100
    ):
        raise ValueError("Evidence query needs a bounded scan budget")
    provenance = proposal["provenance"]
    if (
        not isinstance(provenance, list) or not 1 <= len(provenance) <= 16
        or any(not isinstance(item, str) or not re.fullmatch(r"[a-f0-9]{64}", item)
               for item in provenance)
    ):
        raise ValueError("Evidence query needs bounded provenance hashes")
    return CompiledEvidenceQuery(budget["max_candidates"])


def observe_evidence_query(
    browser: Callable[[str, str, dict], object], query: CompiledEvidenceQuery,
    scope: ApprovedQueryScope | None, *, expected: object = _UNSET,
) -> EphemeralEvidence:
    """Run a fixed isolated-world read. Exact value observation is a separate capability."""
    if expected is not _UNSET:
        return EphemeralEvidence("value_observation_unsupported")
    return _observe(browser, query, scope)[0]


VerifiedFieldHandle = Callable[[ApprovedQueryScope, Callable[[str, str], None]], bool]


def mint_verified_field(
    browser: Callable[[str, str, dict], object], query: CompiledEvidenceQuery,
    scope: ApprovedQueryScope,
) -> tuple[EphemeralEvidence, VerifiedFieldHandle | None]:
    """Return a host-only, eight-second, single-use handoff for a separate native action.

    The dispatcher must supply the currently leased scope object on redemption and
    replace it on navigation or phase changes. Keep the handoff and the native
    selector in the host. Re-resolution and action are sequential, so callers
    need exclusive tab ownership plus independent outcome evidence.
    """
    if not isinstance(scope, ApprovedQueryScope) or not scope.generation:
        return EphemeralEvidence("stale_scope"), None
    evidence, identity = _observe(browser, query, scope, capture_identity=True)
    if identity is None:
        return evidence, None
    wrapper, field, tag, field_type, role = identity
    selector = (
        f'{scope.selector} >> css=[id="{wrapper}"] {tag}[id="{field}"]:visible'
        ':not(:disabled,[readonly],[aria-disabled="true"],[aria-disabled="true"] *,'
        '[aria-readonly="true"],[aria-readonly="true"] *,[aria-hidden="true"],'
        '[aria-hidden="true"] *,[inert],[inert] *)'
    )
    if tag == "input":
        type_filter = f'[type="{field_type}" i]'
        selector += f":is(:not([type]),{type_filter})" if field_type == "text" else type_filter
    selector += " >> internal:and=" + json.dumps("role=" + role)
    deadline = monotonic() + _HANDLE_TTL_SECONDS
    lock = Lock()
    redeemed = False

    def consume(current_scope: ApprovedQueryScope, use: Callable[[str, str], None]) -> bool:
        nonlocal redeemed
        with lock:
            if redeemed or current_scope is not scope or monotonic() >= deadline:
                return False
            redeemed = True
            _, current = _observe(browser, query, current_scope, capture_identity=True)
            if current != identity or monotonic() >= deadline:
                return False
            use(scope.tab, selector)
            return True

    return evidence, consume


def _observe(browser, query, scope, *, capture_identity=False):
    if (
        not isinstance(scope, ApprovedQueryScope)
        or any(not isinstance(value, str) or not value.strip()
               for value in (scope.tab, scope.origin, scope.selector, scope.label))
        or len(scope.label) > 256
        or (scope.role is not None and (
            not isinstance(scope.role, str) or scope.role not in _ROLES
        ))
    ):
        return EphemeralEvidence("stale_scope"), None
    if type(query.max_candidates) is not int or not 1 <= query.max_candidates <= 100:
        return EphemeralEvidence("read_failed"), None
    args = {
        "origin": scope.origin, "label": scope.label,
        "role": scope.role, "budget": query.max_candidates,
    }
    if capture_identity:
        args["captureIdentity"] = True
    try:
        result = browser(scope.tab, "eval", {
            "world": "isolated", "selector": scope.selector, "expression": _PROJECT,
            "arg": args,
        })
    except (OSError, RuntimeError, ValueError):
        return EphemeralEvidence("read_failed"), None
    if normalize(result) is not Outcome.RETURNED or len(result["content"]) != 1:
        return EphemeralEvidence("read_failed"), None
    item = result["content"][0]
    status = item.get("text")
    if item.get("type") != "text" or not isinstance(status, str):
        return EphemeralEvidence("read_failed"), None
    if status in _STATUSES:
        return EphemeralEvidence(status), None
    if not capture_identity or len(status) > 1024:
        return EphemeralEvidence("read_failed"), None
    try:
        record = json.loads(status)
    except (ValueError, RecursionError):
        return EphemeralEvidence("read_failed"), None
    if (
        not isinstance(record, dict) or record.keys() != {"status", "wrapper", "field", "tag", "type", "role"}
        or record["status"] != "unique_match"
        or any(not isinstance(record[key], str) or not _NATIVE_ID.fullmatch(record[key])
               for key in ("wrapper", "field", "tag", "type", "role"))
        or record["wrapper"] == record["field"]
        or record["tag"] not in {"input", "textarea", "select"} or record["role"] not in _ROLES
        or (scope.role is not None and scope.role != record["role"])
    ):
        return EphemeralEvidence("read_failed"), None
    identity = tuple(record[key] for key in ("wrapper", "field", "tag", "type", "role"))
    return EphemeralEvidence("unique_match"), identity
