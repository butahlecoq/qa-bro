"""Dispatch a host-approved action on a uniquely identified synthetic table row."""

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from qabro.browser import Outcome, normalize


@dataclass(frozen=True)
class OwnedRowCell:
    column: int
    text: str
    direct_text_selector: str | None = None

    def __post_init__(self):
        selector = self.direct_text_selector
        if selector is not None and (
            not _simple_selector(selector)
            or re.split(r"[.#]", selector, maxsplit=1)[0] in {"input", "script", "noscript", "style"}
            or not _bounded_text(self.text) or ">>" in self.text
        ):
            raise ValueError("Expected an approved direct child tag or compound selector and exact text")


_VISIBLE = ':visible:not(:is([aria-hidden="true"],[inert]),:is([aria-hidden="true"],[inert]) *)'
_LEAF = _VISIBLE + ':not(:has(*))'
_CELL = ':is(td,[role~="cell"],[role~="gridcell"],[role~="rowheader"])'
_ROW = ':is(tr,[role~="row"])'
_TABLE = ':is(table,[role~="table"],[role~="grid"],[role~="treegrid"])'
_ROWS = f'css:light=:is(:scope > :is(tbody,[role~="rowgroup"]:not(thead)) > {_ROW}, :scope > {_ROW}){_VISIBLE}'
_SAFE_BUTTON = (
    'css:light=button:not([form],[type="submit" i],[type="reset" i],:disabled,form *,'
    '[aria-disabled="true"],[aria-disabled="true"] *)' + _VISIBLE
)


def _literal_pattern(text: str) -> str:
    units = text.encode("utf-16-le")
    literal = "".join(
        rf"\u{int.from_bytes(units[index:index + 2], 'little'):04x}" for index in range(0, len(units), 2)
    )
    return rf"internal:has-text=/^{literal}(?![\s\S])/"


def _predicate(engine: str, query: str) -> str:
    return f" >> internal:{engine}={json.dumps(query)}"


def _without_duplicate(query: str) -> str:
    return _predicate("has-not", query + " >> nth=1")


def _matches_cell(cell: OwnedRowCell, *, require_visible_text: bool = True) -> str:
    column = f"css:light=:scope > :nth-child({cell.column}){_CELL}{_VISIBLE}"
    if cell.direct_text_selector is not None:
        child = f"css:light=:scope > {cell.direct_text_selector}{_VISIBLE}"
        exact = f"text:light={json.dumps(cell.text, ensure_ascii=False)}"
        target = child + _predicate("and", exact)
        if require_visible_text:
            column += _without_duplicate(child)
        return _predicate("has", column + " >> " + target)
    text = _literal_pattern(cell.text)
    matched = column + " >> " + text
    if not require_visible_text:
        return _predicate("has", matched)
    leaf = f"css:light=:scope{_LEAF} >> {text}"
    descendant = f"css:light=:scope *{_LEAF} >> {text}"
    return _predicate("has", matched + _predicate("has", leaf + _predicate("or", descendant)))


def _value(raw: object, *, max_chars: int = 4096) -> object:
    if normalize(raw) != Outcome.RETURNED:
        return None
    content = raw["content"]
    if len(content) != 1 or content[0]["type"] != "text":
        return None
    text = content[0].get("text")
    if not isinstance(text, str) or len(text) > max_chars:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def _bounded_text(text: object) -> bool:
    return isinstance(text, str) and 0 < len(text) <= 160 and text.isprintable()


def _simple_selector(selector: object) -> bool:
    return (
        isinstance(selector, str) and len(selector) <= 160
        and re.fullmatch(r"[a-z][a-z0-9-]*(?:[.#][A-Za-z_][A-Za-z0-9_-]*)*", selector) is not None
    )


def make_owned_row_dispatch(
    browser: Callable[[str, str, dict], object],
    tab: str,
    *,
    table_selector: str,
    marker: OwnedRowCell,
    identity: tuple[OwnedRowCell, ...],
    approved_actions: frozenset[str],
    action_icons: Mapping[str, str] | None = None,
    action_columns: Mapping[str, int] | None = None,
    timeout_ms: int = 1000,
) -> Callable[[dict], dict]:
    cells = (marker, *identity)
    icons = dict(action_icons or {})
    columns = dict(action_columns or {})
    if (
        not tab or not _bounded_text(table_selector) or ">>" in table_selector
        or not 1 <= len(identity) <= 3
        or any(
            not isinstance(cell, OwnedRowCell) or type(cell.column) is not int
            or not 1 <= cell.column <= 128 or not _bounded_text(cell.text)
            for cell in cells
        )
        or len({cell.column for cell in cells}) != len(cells)
        or len({cell.text for cell in cells}) != len(cells)
        or not approved_actions or any(not _bounded_text(label) or ">>" in label for label in approved_actions)
        or icons.keys() - approved_actions or any(not _simple_selector(icon) for icon in icons.values())
        or columns.keys() - approved_actions
        or any(type(column) is not int or not 1 <= column <= 128 for column in columns.values())
        or type(timeout_ms) is not int or not 1 <= timeout_ms <= 5000
    ):
        raise ValueError("invalid owned-row action binding")

    table = f"css:light=:is({table_selector}){_TABLE}{_VISIBLE}"
    marked_rows = _ROWS + _matches_cell(marker, require_visible_text=False)
    owned_rows = _ROWS + _predicate("has-not", f"css:light=:scope :is({_ROW},{_TABLE})")
    owned_rows += "".join(_matches_cell(cell) for cell in cells)
    scope = (
        "css:light=:root" + _without_duplicate(table) + " >> " + table
        + _predicate("and", 'css:light=:not([aria-busy="true"],[aria-busy="true"] *)')
        + _without_duplicate(marked_rows) + " >> " + owned_rows
    )
    selectors = {}
    for label in approved_actions:
        if label in icons:
            icon = f"css:light=:scope > {icons[label]}:visible"
            button = "role=button" + _predicate("has", icon)
            visible_button = button + _predicate("and", f"css:light=button{_VISIBLE}")
            button += _without_duplicate(icon)
        else:
            button = f'role=button[name={json.dumps(label, ensure_ascii=False)}s]'
            visible_button = button + _predicate("and", f"css=*{_VISIBLE}")
        action_scope = scope + _without_duplicate(visible_button)
        if label in columns:
            action_scope += f" >> css:light=:scope > :nth-child({columns[label]}){_CELL}{_VISIBLE}"
        selectors[label] = action_scope + " >> " + button + _predicate("and", _SAFE_BUTTON)

    def dispatch(request: dict) -> dict:
        if not isinstance(request, dict) or request.keys() != {"action", "label"} or request["action"] != "click_owned_row":
            return {"status": "out_of_scope"}
        label = request["label"]
        if not isinstance(label, str) or label not in selectors:
            return {"status": "out_of_scope"}
        target = {"selector": selectors[label], "timeout": timeout_ms}
        try:
            ready = _value(browser(tab, "eval", {**target, "expression": "el => !!el", "world": "isolated"}))
        except Exception:
            ready = None
        if ready is not True:
            return {"status": "not_actionable"}
        try:
            # Browse includes the native selector in its click receipt.
            limit = min(65_536, len(json.dumps(target["selector"])) + 4096)
            receipt = _value(browser(tab, "click", target), max_chars=limit)
        except Exception:
            receipt = None
        if isinstance(receipt, dict) and isinstance(receipt.get("clicked"), str) and receipt["clicked"]:
            return {"status": "dispatched"}
        return {"status": "unknown_effect"}

    return dispatch
