"""Read the complete ordered options of a native HTML select."""

import json

from qabro.bindings import Option, Options, UnresolvedBinding
from qabro.browser import BrowserCalls, Outcome


def read_native_options(browser: BrowserCalls, probe: str, step: str, selector: str) -> Options:
    result = browser.invoke(probe, step, "eval", {
        "selector": selector,
        "expression": """element => element.tagName === "SELECT"
            ? Array.from(element.options, option => ({id: option.value, label: option.label}))
            : null""",
    }, read_only=True)
    if result.outcome is not Outcome.RETURNED:
        raise UnresolvedBinding("Unable to read native select")
    try:
        content = result.raw["content"]
        if len(content) != 1 or content[0]["type"] != "text":
            raise ValueError("Unexpected option response")
        entries = json.loads(content[0]["text"])
        options = tuple(Option(**entry) for entry in entries)
        if any(not isinstance(item.id, str) or not isinstance(item.label, str) for item in options):
            raise ValueError("Invalid option identity")
        if len({item.id for item in options}) != len(options):
            raise ValueError("Ambiguous option identity")
    except (KeyError, TypeError, ValueError) as error:
        raise UnresolvedBinding("Cannot establish complete native select options") from error
    return Options(options, complete=True)
