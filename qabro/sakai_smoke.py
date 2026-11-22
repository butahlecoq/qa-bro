"""Run the Sakai CRUD smoke test through the installed browse MCP transport."""

import argparse
import json
from pathlib import Path
from time import monotonic, sleep
from urllib.parse import urlsplit
from uuid import uuid4

from qabro.artifacts import ArtifactStore
from qabro.browse_schema import snapshot_schema
from qabro.browse_transport import BrowseTransport
from qabro.browser import BrowserCalls, Outcome
from qabro.journal import Journal
from qabro.redaction import TraceRedactor
from qabro.sakai_cases import product_for


PUBLIC_URL = "https://sakai.primevue.org/pages/crud"
DIALOG = '[role="dialog"]'
PRICE = f'{DIALOG} [role="spinbutton"] >> nth=0'
SEARCH = 'input[placeholder="Search..."]'
ROW = 'tbody tr'


def smoke(output: Path, executable: str, url: str, *, case: str = "smoke") -> dict:
    parsed = urlsplit(url)
    if parsed.path != "/pages/crud" or not (
        url == PUBLIC_URL or parsed.scheme == "http" and parsed.hostname == "127.0.0.1"
    ):
        raise ValueError("Expected the public Sakai demo or a loopback Sakai deployment")
    output.mkdir(mode=0o700)
    database = output / "smoke.sqlite"
    journal, store = Journal(database), ArtifactStore(database)
    attempt = f"sakai-{uuid4().hex[:12]}"
    data = product_for(1, attempt, 0)
    product, description = data.name, data.description
    price = f"{data.price_cents // 100}.{data.price_cents % 100:02d}"
    journal.start(attempt, attempt, "smoke")
    journal.claim_tab("sakai", attempt, attempt)

    with BrowseTransport(executable) as live:
        live.prepare_tab(attempt, allowed_origins=(f"{parsed.scheme}://{parsed.netloc}",))
        try:
            browser = BrowserCalls(journal, attempt, "sakai", attempt, live, TraceRedactor(), artifacts=store)
            sequence = 0

            def invoke(step, tool, args, *, read=False):
                nonlocal sequence
                sequence += 1
                result = browser.invoke(f"smoke-{sequence}", step, tool, args, read_only=read)
                if result.outcome is not Outcome.RETURNED:
                    raise RuntimeError(f"{step}: {tool} failed; see the local trace")
                return result.raw["content"][0]["text"], result.artifact_id

            def evaluate(step, expression):
                raw, proof = invoke(step, "eval", {"expression": expression}, read=True)
                return json.loads(raw), proof

            def check(step, expression, expected):
                deadline = monotonic() + 3
                while True:
                    actual, proof = evaluate(step, expression)
                    matched = type(actual) is type(expected) and actual == expected
                    if matched or monotonic() >= deadline:
                        break
                    sleep(0.15)
                journal.append(attempt, f"check:{step}", "checkpoint", {
                    "step": step, "outcome": "observed_match" if matched else "observed_mismatch",
                    "artifact_id": proof,
                })
                if not matched:
                    raise RuntimeError(f"{step}: observed state did not match; see the local trace")

            def click(step, selector):
                invoke(step, "click", {"selector": selector})

            def fill(step, selector, value):
                invoke(step, "fill", {"selector": selector, "value": value})

            def open_page(step):
                invoke(step, "navigate", {"url": url})
                deadline = monotonic() + 10
                while monotonic() < deadline:
                    ready, _ = evaluate(step, "() => !!document.querySelector('tbody tr')")
                    if ready:
                        return
                    sleep(0.25)
                raise RuntimeError(f"{step}: product table did not become ready")

            environment = {
                "browse": snapshot_schema(live), "target_url": url, "tab": attempt,
                "connection": "browse stdio MCP", "model": None, "harness": None,
            }
            open_page("ready")
            traits, _ = evaluate("environment", "() => ({user_agent:navigator.userAgent, width:innerWidth, height:innerHeight})")
            environment.update(traits)
            (output / "environment.json").write_text(json.dumps(environment, indent=2))
            closed = """() => !document.querySelector('[role=dialog]')"""
            ready = """() => !document.querySelector('[role=dialog]') &&
                !!document.querySelector('tbody tr[data-pc-section=bodyrow]')"""
            fields = """() => {
                const dialog = document.querySelector('[role=dialog]');
                return [dialog?.querySelector('#name')?.value, dialog?.querySelector('#description')?.value,
                        Math.round(Number(dialog?.querySelector('[role=spinbutton]')?.value.replace(/[^0-9.]/g, '')) * 100)];
            }"""
            exact_rows = f"""[...document.querySelectorAll('tbody tr')].filter(row =>
                [...row.cells].some(cell => cell.textContent.trim() === {json.dumps(product)}))"""
            count = f"() => {exact_rows}.length"

            def prices(cents):
                return f"""() => {exact_rows}.map(row => [...row.cells].some(cell =>
                    /^[ $0-9,.]+$/.test(cell.textContent) && cell.textContent.includes('$') &&
                    Math.round(Number(cell.textContent.replace(/[^0-9.]/g, '')) * 100) === {cents}))"""

            def button(step, label):
                click(step, f'{DIALOG} button:has-text("{label}")')

            def row_action(step, icon):
                # Search results must contain exactly one row, and it must be our generated product.
                check(f"{step}_target", f"() => [{exact_rows}.length, document.querySelectorAll('tbody tr[data-pc-section=bodyrow]').length]", [1, 1])
                click(step, f"{ROW} button:has(.pi-{icon})")

            open_page("initial_reset")
            fill("reset_search", SEARCH, product)
            check("reset_absent", count, 0)
            fill("reset_clear", SEARCH, "")
            check("reset_ready", ready, True)
            click("new", 'role=button[name="New"]')
            check("dialog_open", """() => document.querySelector('[role=dialog] [data-pc-section=title]')?.textContent""", "Product Details")
            if case in {"smoke", "SAKAI-01"}:
                click("empty_save", f'{DIALOG} button:has-text("Save")')
                check("required_name", """() => document.querySelector('[role=dialog]')?.innerText.includes('Name is required.') ?? false""", True)
            if case == "SAKAI-01":
                button("cancel_empty", "Cancel")
                check("table_ready", ready, True)
            else:
                fill("name", f"{DIALOG} #name", product)
                fill("description", f"{DIALOG} #description", description)
                fill("price", PRICE, price)
                check("entered_fields", fields, [product, description, data.price_cents])
                button("save", "Save")
                check("saved", closed, True)
                fill("search", SEARCH, product)
                check("exact_row_and_price", prices(data.price_cents), [True])
                row_action("edit", "pencil")
                check("saved_fields", fields, [product, description, data.price_cents])
                button("cancel", "Cancel")
                check("record_remains", f"() => [{exact_rows}.length, !!document.querySelector('[role=dialog]')]", [1, False])
                if case == "SAKAI-03":
                    row_action("edit_again", "pencil")
                    check("original_price", fields, [product, description, data.price_cents])
                    cents = data.updated_price_cents
                    fill("update_price", PRICE, f"{cents // 100}.{cents % 100:02d}")
                    check("entered_price", fields, [product, description, cents])
                    button("save_update", "Save")
                    check("updated_closed", closed, True)
                    check("updated_row", prices(cents), [True])
                    row_action("reopen", "pencil")
                    check("persisted_update", fields, [product, description, cents])
                    button("close_update", "Cancel")
                    check("table_ready", ready, True)
                if case == "SAKAI-04":
                    confirm = f"""() => {{
                        const dialog = document.querySelector('[role=dialog]');
                        return dialog?.querySelector('[data-pc-section=title]')?.textContent === 'Confirm'
                            && dialog.innerText.includes({json.dumps(product)});
                    }}"""
                    row_action("delete", "trash")
                    check("confirm_open", confirm, True)
                    button("decline_delete", "No")
                    check("cancel_preserves_row", f"() => [{exact_rows}.length, !!document.querySelector('[role=dialog]')]", [1, False])
                    row_action("delete_again", "trash")
                    check("confirm_reopened", confirm, True)
                    button("confirm_delete", "Yes")
                    check("confirm_closed", closed, True)
                    check("record_absent", count, 0)
                if case == "smoke":
                    open_page("reset")
                    fill("search_after_reset", SEARCH, product)
                    check("record_absent", count, 0)
                    fill("clear_search", SEARCH, "")
                    check("table_ready", ready, True)
            result = {"verdict": "PASS", "case": case, "attempt": attempt, "target_url": url}
            journal.append(attempt, "scenario:finish", "scenario_finish", result)
            (output / "smoke.json").write_text(json.dumps(result, indent=2))
            return result
        finally:
            live(attempt, "tabs", {"action": "close"})
            journal.release_tab("sakai", attempt, attempt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New directory outside the public checkout")
    parser.add_argument("--browse", default="browse")
    parser.add_argument("--url", default=PUBLIC_URL)
    parser.add_argument("--case", choices=("smoke", "SAKAI-01", "SAKAI-02", "SAKAI-03", "SAKAI-04"), default="smoke")
    args = parser.parse_args()
    print(json.dumps(smoke(args.output, args.browse, args.url, case=args.case), indent=2))
