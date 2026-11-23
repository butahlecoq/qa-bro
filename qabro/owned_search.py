"""Project a scoped browser search into evidence about a host-owned record."""

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Literal

from qabro.browser import Outcome, normalize
from qabro.owned_row_action import OwnedRowCell


@dataclass(frozen=True)
class SearchBindings:
    """Host-approved CSS for the editable search field, filter controls and results table."""

    search_selector: str
    filter_selector: str | None
    table_selector: str
    cells: tuple[OwnedRowCell, ...] = ()


@dataclass(frozen=True)
class OwnedSearchQuery:
    """A host-owned query generation tied to one navigation and filter/search dispatch."""

    generation: str
    filter: str | None
    marker: str
    identity: tuple[str, ...]

    def __post_init__(self):
        if (
            not isinstance(self.identity, tuple) or not 1 <= len(self.identity) <= 3
            or any(not isinstance(value, str) or not value.strip() for value in (
                self.generation, self.marker, *self.identity,
            ))
            or (self.filter is not None and (not isinstance(self.filter, str) or not self.filter.strip()))
        ):
            raise ValueError("Expected a scoped search and exact host-owned identity values")


@dataclass(frozen=True)
class SearchCompleted:
    """Reference to trusted evidence that this query settled with complete result coverage.

    The caller must establish both settlement and coverage for this specific generation.
    A missing spinner, elapsed sleep, stable visible count, or an empty page cannot supply it.
    """

    query: OwnedSearchQuery
    evidence_ref: str
    tab: str

    def __post_init__(self):
        if any(not isinstance(value, str) or not value.strip() for value in (self.evidence_ref, self.tab)):
            raise ValueError("Expected a positive, query-specific completion evidence reference")


@dataclass(frozen=True)
class SearchLifecycleSample:
    """Shaped evidence from the same observed table, approved field and filter."""

    scope_current: bool
    query_matches: bool
    after_exact_input: bool
    busy: bool | None
    error_visible: bool
    data_rows: int | None
    total: int | None = None
    scoped_empty: bool = False


def admit_search_completion(
    query: OwnedSearchQuery, tab: str, samples: tuple[SearchLifecycleSample, ...], evidence_ref: str,
) -> SearchCompleted | None:
    """Admit a witnessed post-input loading cycle with full rendered result coverage.

    The host supplies observations from a watcher armed before the fill. The loading,
    counter and empty-state observations must belong to the same results region.
    """

    if not 3 <= len(samples) <= 64:
        return None
    initial = samples[0]
    first_input = next((index for index, sample in enumerate(samples) if sample.after_exact_input is True), 0)
    if first_input == 0 or initial.query_matches is not False:
        return None
    if any(sample.scope_current is not True or sample.error_visible is not False for sample in samples):
        return None
    if any(sample.after_exact_input is not False or sample.busy is not False for sample in samples[:first_input]):
        return None
    current = samples[first_input:]
    if any(
        sample.after_exact_input is not True or sample.query_matches is not True
        or type(sample.busy) is not bool for sample in current
    ):
        return None
    final = current[-1]
    if final.busy or not any(sample.busy for sample in current[:-1]):
        return None
    if type(final.data_rows) is not int or final.data_rows < 0:
        return None
    if final.total is not None and (type(final.total) is not int or final.total < 0):
        return None
    if final.scoped_empty is True:
        covered = final.data_rows == 0 and final.total in (None, 0)
    else:
        covered = final.total == final.data_rows
    return SearchCompleted(query, evidence_ref, tab) if covered else None


@dataclass(frozen=True)
class OwnedSearchEvidence:
    """An owned match confirms displayed identifiers in a row, without assuming column semantics."""

    status: Literal["partial", "complete", "read_failed"]
    match: Literal["none", "owned", "conflict", "multiple"] | None = None
    identity_matches: tuple[bool, ...] = ()
    completion_ref: str | None = None

    @property
    def proves_empty(self) -> bool:
        """Whether this single filter has complete evidence of zero exact marker matches."""
        return self.status == "complete" and self.match == "none" and self.completion_ref is not None


_PROJECT = r"""(_, binding) => {
    const rowSelector = 'tr,[role~="row"]';
    const tableSelector = 'table,[role~="table"],[role~="grid"],[role~="treegrid"]';
    const boundCellSelector = 'td,[role~="cell"],[role~="gridcell"],[role~="rowheader"]';
    const cellSelector = 'th,' + boundCellSelector;
    const visible = element => !!element.getClientRects().length &&
        getComputedStyle(element).visibility === 'visible' &&
        !element.closest('[aria-hidden="true"],[inert]');
    const visibleMatches = selector => [...document.querySelectorAll(selector)].filter(visible);
    const failed = {scope: false, marker_count: 0, identity_matches: []};
    const fields = visibleMatches(binding.search_selector);
    const tables = visibleMatches(binding.table_selector);
    const selected = binding.filter_selector === null ? [] : visibleMatches(binding.filter_selector).filter(control =>
        control.getAttribute('aria-selected') === 'true' ||
        control.getAttribute('aria-pressed') === 'true' ||
        control.getAttribute('aria-checked') === 'true' ||
        control.matches(':checked'));
    if (fields.length !== 1 || tables.length !== 1 ||
        selected.length !== (binding.filter_selector === null ? 0 : 1)) return failed;
    const [field] = fields;
    const [table] = tables;
    const [filter] = selected;
    const labelledBy = (filter?.getAttribute('aria-labelledby') ?? '').split(/\s+/)
        .map(id => document.getElementById(id)?.innerText?.trim()).filter(Boolean).join(' ');
    const filterName = filter ? labelledBy || (
        filter.getAttribute('aria-label') ?? filter.labels?.[0]?.innerText ?? filter.innerText) : null;
    if (field.tagName !== 'INPUT' || !['text', 'search'].includes(field.type) ||
        field.value !== binding.marker || (filterName?.trim() ?? null) !== binding.filter ||
        !table.matches(tableSelector) || table.closest('[aria-busy="true"]')) return failed;

    let marker_count = 0;
    let identity_matches = [];
    const normalizeText = text => text.replace(/[\u200b\u00ad]/g, '').trim().replace(/\s+/g, ' ');
    function immediateMatch(el, value) {
        let segment = '';
        for (const child of el.childNodes) {
            if (child.nodeType === 3) segment += child.nodeValue || '';
            else if (child.nodeType !== 8) {
                if (segment && normalizeText(segment) === value) return true;
                segment = '';
            }
        }
        return !!segment && normalizeText(segment) === value;
    }
    function readBoundCell(row, binding) {
        const cell = row.children[binding.column - 1];
        if (!cell?.matches(boundCellSelector) || !visible(cell)) return [false, false];
        if (binding.direct_text_selector !== null) {
            const candidates = [...cell.children].filter(el =>
                el.matches(binding.direct_text_selector) && visible(el));
            const value = normalizeText(binding.text);
            const found = candidates.some(el => immediateMatch(el, value));
            return [found, found && candidates.length === 1];
        }
        const found = cell.textContent === binding.text;
        const leaf = [cell, ...cell.querySelectorAll('*')].some(el =>
            !el.childElementCount && visible(el) && el.textContent === binding.text);
        return [found, found && leaf];
    }
    for (const row of table.querySelectorAll(rowSelector)) {
        if (row.closest(tableSelector) !== table || !visible(row) || row.closest('thead')) continue;
        if (binding.cells?.length) {
            if (row.parentElement !== table &&
                (!row.parentElement.matches('tbody,[role~="rowgroup"]:not(thead)') ||
                 row.parentElement.parentElement !== table)) continue;
            const [marker, ...identity] = binding.cells;
            const [found, verified] = readBoundCell(row, marker);
            if (!found) continue;
            if (++marker_count === 2) return {scope: true, marker_count, identity_matches: []};
            const unnested = !row.querySelector(rowSelector + ',' + tableSelector);
            identity_matches = identity.map(cell => verified && unnested && readBoundCell(row, cell)[1]);
            continue;
        }
        const texts = new Set();
        for (const cell of row.querySelectorAll(cellSelector)) {
            if (cell.closest(rowSelector) !== row || !visible(cell) ||
                cell.parentElement.closest(cellSelector)) continue;
            if (!cell.querySelector(rowSelector + ',[aria-hidden="true"],[inert]')) {
                texts.add(cell.innerText?.trim());
            }
            for (const leaf of cell.querySelectorAll('*')) {
                if (!leaf.childElementCount && leaf.closest(rowSelector) === row && visible(leaf)) {
                    texts.add(leaf.innerText?.trim());
                }
            }
        }
        // Identity mismatches on the exact marker are conflicts, not evidence of absence.
        if (!texts.has(binding.marker)) continue;
        if (++marker_count === 2) return {scope: true, marker_count, identity_matches: []};
        identity_matches = binding.identity.map(value => texts.has(value));
    }
    return {scope: true, marker_count, identity_matches};
}"""


def observe_owned_search(
    browser: Callable[[str, str, dict], object], tab: str,
    bindings: SearchBindings, query: OwnedSearchQuery, *,
    completed: SearchCompleted | None = None,
) -> OwnedSearchEvidence:
    """Read only shaped evidence. No settled-query witness means a partial read."""

    failed = OwnedSearchEvidence("read_failed")
    if (bindings.filter_selector is None) != (query.filter is None):
        return failed
    if bindings.cells:
        cells = bindings.cells
        if (
            not isinstance(cells, tuple)
            or any(not isinstance(cell, OwnedRowCell) or type(cell.column) is not int
                   or not 1 <= cell.column <= 128 for cell in cells)
            or len({cell.column for cell in cells}) != len(cells)
            or tuple(cell.text for cell in cells) != (query.marker, *query.identity)
        ):
            return failed
    try:
        raw = browser(tab, "eval", {
            "world": "isolated", "expression": _PROJECT,
            "arg": {**asdict(bindings), "filter": query.filter, "marker": query.marker,
                    "identity": list(query.identity)},
        })
    except (OSError, RuntimeError, ValueError):
        return failed
    if normalize(raw) is not Outcome.RETURNED:
        return failed
    content = raw["content"]
    if len(content) != 1 or content[0]["type"] != "text":
        return failed
    text = content[0].get("text")
    if not isinstance(text, str) or len(text) > 4096:
        return failed
    try:
        payload = json.loads(text)
    except (ValueError, RecursionError):
        return failed
    if not isinstance(payload, dict) or payload.keys() != {"scope", "marker_count", "identity_matches"}:
        return failed
    count, matches = payload["marker_count"], payload["identity_matches"]
    if (
        payload["scope"] is not True or type(count) is not int or count not in (0, 1, 2)
        or not isinstance(matches, list) or any(type(value) is not bool for value in matches)
        or len(matches) != (len(query.identity) if count == 1 else 0)
    ):
        return failed
    if count == 0:
        match = "none"
    elif count == 2:
        match = "multiple"
    else:
        match = "owned" if all(matches) else "conflict"
    if completed is not None and completed.query == query and completed.tab == tab:
        return OwnedSearchEvidence("complete", match, tuple(matches), completed.evidence_ref)
    return OwnedSearchEvidence("partial", match, tuple(matches))
