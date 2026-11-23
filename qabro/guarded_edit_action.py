"""Host-issued ownership receipts for separate guarded edit operations."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from threading import Lock
from time import monotonic

from qabro.guarded_form_action import (
    ApprovedFormAction, FormActionReceipt, FormFieldBinding, _guarded_form_operations,
)
from qabro.owned_row_action import OwnedRowCell, make_owned_row_dispatch
from qabro.owned_search import SearchCompleted

_PROOF_SECONDS = 90
_ROW_READY = """(action, origin) => !!action?.isConnected &&
    action.ownerDocument.location.origin === origin &&
    ![...action.ownerDocument.querySelectorAll('dialog[open],[role~="dialog"],[role~="alertdialog"]')]
        .some(el => !!el.getClientRects().length && getComputedStyle(el).visibility === 'visible' &&
                    !el.closest('[aria-hidden="true"],[inert]'))"""


@dataclass(frozen=True)
class RoleObservationBinding:
    """Host adapter for an exact current role that has no readable native value."""

    expected: str
    observe: Callable[[str, str, str], bool]


@dataclass(frozen=True)
class EditBinding:
    """Host bindings for three exact row identity cells and a single editable draft."""

    form: ApprovedFormAction
    table_selector: str
    row_identity: tuple[OwnedRowCell, OwnedRowCell, OwnedRowCell]
    initial_search: SearchCompleted
    edit_action: str
    stable_role: FormFieldBinding | RoleObservationBinding
    stable_active: FormFieldBinding
    original_draft: FormFieldBinding
    updated_draft: FormFieldBinding


class EditDialogReceipt:
    """Opaque receipt. Only the issuing edit lease can redeem it."""

    __slots__ = ()


@dataclass(frozen=True)
class GuardedEdit:
    open_owned: Callable[[], FormActionReceipt]
    read_owned_original: Callable[[], EditDialogReceipt | None]
    save: Callable[[EditDialogReceipt], FormActionReceipt]
    reopen_owned: Callable[[SearchCompleted], FormActionReceipt]
    read_persisted: Callable[[], bool]


def _search_matches(completion, form, identity):
    return (
        isinstance(completion, SearchCompleted) and completion.tab == form.tab
        and (completion.query.marker, *completion.query.identity) == tuple(cell.text for cell in identity)
    )


def _checks(browser, binding):
    form = binding.form
    role_fields = (binding.stable_role,) if isinstance(binding.stable_role, FormFieldBinding) else ()
    stable = (*form.fields, *role_fields, binding.stable_active)
    original = replace(form, fields=(*stable, binding.original_draft))
    updated = replace(form, fields=(*stable, binding.updated_draft))
    read, _ = _guarded_form_operations(browser, original, operation="edit")
    read_updated, save = _guarded_form_operations(browser, updated, operation="edit")
    return read, read_updated, save


def make_guarded_edit(browser: Callable[[str, str, dict], object], binding: EditBinding) -> GuardedEdit:
    """Authorize Save only after a freshly observed edit of the exact owned row.

    All UI steps are separate. The host waits for each scenario's visible state
    and uses its separate field action to set the draft before redeeming the proof.
    The host must own the dedicated tab exclusively and discard these closures on
    navigation. The final isolated check and native Save are sequential, as in
    the guarded-create boundary. A dispatch receipt is not proof of persistence.
    """
    if not isinstance(binding, EditBinding):
        raise ValueError("Expected a host edit binding")
    form, original, updated = binding.form, binding.original_draft, binding.updated_draft
    role = binding.stable_role
    native_role = isinstance(role, FormFieldBinding)
    if (
        not isinstance(form, ApprovedFormAction) or form.operation != "edit"
        or not isinstance(binding.row_identity, tuple) or len(binding.row_identity) != 3
        or any(not isinstance(cell, OwnedRowCell) for cell in binding.row_identity)
        or not _search_matches(binding.initial_search, form, binding.row_identity)
        or not isinstance(role, (FormFieldBinding, RoleObservationBinding))
        or not isinstance(role.expected, str) or not role.expected.strip()
        or (not native_role and not callable(role.observe))
        or not isinstance(binding.stable_active, FormFieldBinding) or type(binding.stable_active.expected) is not bool
        or not isinstance(form.fields, tuple) or len(form.fields) != 3
        or any(not isinstance(field, FormFieldBinding) for field in form.fields)
        or {cell.text for cell in binding.row_identity} != {
            field.expected for field in form.fields if isinstance(field.expected, str)
        }
        or not isinstance(original, FormFieldBinding) or not isinstance(updated, FormFieldBinding)
        or not isinstance(original.expected, str) or not isinstance(updated.expected, str)
        or original.expected == updated.expected
        or not original.require_editable or not updated.require_editable
        or (original.element_id, original.html_name) != (updated.element_id, updated.html_name)
        or len({(field.element_id, field.html_name) for field in (
            *form.fields, *((role,) if native_role else ()), binding.stable_active, original,
        )}) != (6 if native_role else 5)
    ):
        raise ValueError("Edit needs exact row and form identity and one approved draft field")
    def row_browser(tab, tool, args):
        if tool == "eval":
            args = {**args, "expression": _ROW_READY, "arg": form.origin}
        return browser(tab, tool, args)

    guard = make_owned_row_dispatch(
        row_browser, form.tab, table_selector=binding.table_selector,
        marker=binding.row_identity[0], identity=binding.row_identity[1:],
        approved_actions=frozenset({binding.edit_action}),
    )
    read_original, read_updated, click_save = _checks(browser, binding)
    lock = Lock()
    open_attempted = False
    deadline = 0.0
    proof = None
    save_result = None
    reopen_attempted = False
    reopen_deadline = 0.0

    def open_owned():
        nonlocal open_attempted, deadline
        with lock:
            if open_attempted:
                return FormActionReceipt("already_attempted")
            open_attempted = True
            result = guard({"action": "click_owned_row", "label": binding.edit_action})
            status = result["status"]
            if status == "dispatched":
                deadline = monotonic() + _PROOF_SECONDS
            return FormActionReceipt(status if status in {"dispatched", "unknown_effect"} else "not_actionable")

    def role_matches():
        if native_role:
            return True
        try:
            return role.observe(form.tab, form.title, role.expected) is True
        except (OSError, RuntimeError, ValueError):
            return False

    def read_owned_original():
        nonlocal proof
        with lock:
            if (
                proof is not None or monotonic() >= deadline or not role_matches()
                or not read_original() or monotonic() >= deadline
            ):
                return None
            proof = EditDialogReceipt()
            return proof

    def save(receipt):
        nonlocal deadline, save_result
        with lock:
            if proof is None or receipt is not proof or monotonic() >= deadline:
                return FormActionReceipt("not_actionable")
            active_until = deadline
            deadline = 0.0
            if not role_matches() or monotonic() >= active_until:
                return FormActionReceipt("not_actionable")
            save_result = click_save()
            return save_result

    def reopen_owned(completion):
        nonlocal reopen_attempted, reopen_deadline
        with lock:
            if reopen_attempted:
                return FormActionReceipt("already_attempted")
            if (
                save_result is None or save_result.status not in {"dispatched", "unknown_effect"}
                or not _search_matches(completion, form, binding.row_identity)
                or completion.query.generation == binding.initial_search.query.generation
                or completion.evidence_ref == binding.initial_search.evidence_ref
            ):
                return FormActionReceipt("not_actionable")
            reopen_attempted = True
            result = guard({"action": "click_owned_row", "label": binding.edit_action})
            status = result["status"]
            if status == "dispatched":
                reopen_deadline = monotonic() + _PROOF_SECONDS
            return FormActionReceipt(status if status in {"dispatched", "unknown_effect"} else "not_actionable")

    def read_persisted():
        with lock:
            return (
                monotonic() < reopen_deadline and role_matches() and read_updated()
                and monotonic() < reopen_deadline
            )

    return GuardedEdit(open_owned, read_owned_original, save, reopen_owned, read_persisted)
