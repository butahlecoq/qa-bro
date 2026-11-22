"""Run the Sakai CRUD smoke test through the installed browse MCP transport."""

import argparse
import json
from hashlib import sha256
from pathlib import Path
from time import monotonic_ns
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



class SakaiMismatch(RuntimeError):
    """An independent browser check observed a different result."""


def smoke(
    output: Path, executable: str, url: str, *, case: str = "smoke",
    seed: int = 1, series: str | None = None, pi_worker=None, model: str | None = None,
    skill_sha256: str | None = None,
) -> dict:
    parsed = urlsplit(url)
    if parsed.path != "/pages/crud" or not (
        url == PUBLIC_URL or parsed.scheme == "http" and parsed.hostname == "127.0.0.1"
    ):
        raise ValueError("Expected the public Sakai demo or a loopback Sakai deployment")
    output.mkdir(mode=0o700)
    database = output / "smoke.sqlite"
    journal, store = Journal(database), ArtifactStore(database)
    attempt = f"sakai-{uuid4().hex[:12]}"
    data = product_for(seed, series or attempt, 0)
    started = monotonic_ns()
    worker_result = None
    product, description = data.name, data.description
    price = f"{data.price_cents // 100}.{data.price_cents % 100:02d}"
    journal.start(attempt, attempt, "smoke")
    journal.claim_tab("sakai", attempt, attempt)

    with BrowseTransport(executable) as live:
        live.prepare_tab(attempt, allowed_origins=(f"{parsed.scheme}://{parsed.netloc}",))
        try:
            def record(verdict):
                if worker_result is not None:
                    _, tokens, model_calls, session, read_skill, tool_calls = worker_result
                    scenario = Path(__file__).resolve().parents[1] / "scenarios/sakai/SAKAI-02.md"
                    journal.append(attempt, "sakai:worker", "worker_metadata", {
                        "session_id": session, "seed": seed, "model": model, "target_url": url,
                        "browser_schema_sha256": environment["browse"]["schema_sha256"],
                        "scenario_sha256": sha256(scenario.read_bytes()).hexdigest(),
                        "budgets": {"model_calls": 12, "worker_requests": 24, "worker_seconds": 90},
                        "skill_applied": bool(skill_sha256 and read_skill and position == len(steps) and failure is None),
                        "skill_sha256": skill_sha256,
                    })
                    events = journal.events(attempt)
                    calls = {event: payload for _, event, kind, payload in events if kind == "tool_start"}
                    finishes = {event: payload for _, event, kind, payload in events if kind == "tool_finish"}
                    actions = 0
                    for event, call in calls.items():
                        if call["read_only"]:
                            continue
                        fields = call["arguments"].get("fields") if call["tool"] == "fill" else None
                        if fields is not None and finishes.get(
                            event.removesuffix(":start") + ":finish", {}
                        ).get("outcome") != Outcome.RETURNED:
                            actions = None
                            break
                        actions += len(fields) if fields is not None else 1
                    journal.append(attempt, "sakai:usage", "worker_usage", {
                        "tokens": tokens, "model_calls": model_calls, "elapsed_ns": monotonic_ns() - started,
                        "worker_tool_calls": tool_calls,
                        "mcp_calls": len(calls),
                        "browser_actions": actions,
                    })
                result = {"verdict": verdict, "case": case, "attempt": attempt, "target_url": url}
                journal.append(attempt, "scenario:finish", "scenario_finish", result)
                (output / "smoke.json").write_text(json.dumps(result, indent=2))
                return result

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

            def wait_for(step, expression, expected, *, wait_ms=3000):
                predicate = f"""async () => {{
                    const observe = ({expression});
                    const expected = {json.dumps(expected, allow_nan=False)};
                    const deadline = performance.now() + {wait_ms};
                    let samples = 0;
                    let actual;
                    do {{
                        actual = observe();
                        samples++;
                        if (JSON.stringify(actual) === JSON.stringify(expected)) break;
                        const remaining = deadline - performance.now();
                        if (remaining <= 0) break;
                        await new Promise(resolve => setTimeout(resolve, Math.min(150, remaining)));
                    }} while (performance.now() <= deadline);
                    return {{observed: actual !== undefined, value: actual ?? null, samples}};
                }}"""
                raw, proof = invoke(step, "eval", {"expression": predicate, "timeout": wait_ms + 1000}, read=True)
                result = json.loads(raw)
                actual = result["value"]
                return result["observed"] and type(actual) is type(expected) and actual == expected, proof

            def check(step, expression, expected):
                matched, proof = wait_for(step, expression, expected)
                journal.append(attempt, f"check:{step}", "checkpoint", {
                    "step": step, "outcome": "observed_match" if matched else "observed_mismatch",
                    "artifact_id": proof,
                })
                if not matched:
                    raise SakaiMismatch(f"{step}: observed state did not match; see the local trace")

            def click(step, selector):
                invoke(step, "click", {"selector": selector})

            def fill(step, selector, value):
                invoke(step, "fill", {"selector": selector, "value": value})

            def open_page(step):
                invoke(step, "navigate", {"url": url})
                ready, _ = wait_for(step, "() => !!document.querySelector('tbody tr')", True, wait_ms=10_000)
                if not ready:
                    raise RuntimeError(f"{step}: product table did not become ready")

            environment = {
                "browse": snapshot_schema(live), "target_url": url, "tab": attempt,
                "connection": "browse stdio MCP", "model": model,
                "harness": ("qa-bro Codex" if model and model.startswith("codex/") else "qa-bro Pi")
                if pi_worker else None,
            }
            open_page("initial_reset")
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

            fill("reset_search", SEARCH, product)
            check("reset_absent", count, 0)
            fill("reset_clear", SEARCH, "")
            check("reset_ready", ready, True)
            dialog_title = """() => document.querySelector('[role=dialog] [data-pc-section=title]')?.textContent"""
            if pi_worker:
                if case != "SAKAI-02":
                    raise ValueError("The Pi harness currently supports SAKAI-02")
                steps = [
                    ("new", "click", 'role=button[name="New"]', None),
                    ("name", "fill", f"{DIALOG} #name", product),
                    ("description", "fill", f"{DIALOG} #description", description),
                    ("price", "fill", PRICE, price),
                    ("save", "click", f'{DIALOG} button:has-text("Save")', None),
                ]
                controls = dict(zip(("New", "Name", "Description", "Price", "Save"), steps))
                position = requests = 0
                failure = None

                def dispatch(request):
                    nonlocal position, requests, failure
                    requests += 1
                    if requests > 24 or failure is not None:
                        return {"error": "Creation is stopped"}
                    if position == len(steps):
                        return {"status": "creation_complete"}
                    if request.get("action") == "inspect":
                        visible, _ = evaluate("inspect", """() => {
                            const dialog = document.querySelector('[role=dialog]');
                            if (!dialog) {
                                return [...document.querySelectorAll('button')].some(
                                    button => button.innerText.trim() === 'New'
                                ) ? ['New'] : [];
                            }
                            const controls = [];
                            if (dialog.querySelector('#name')) controls.push('Name');
                            if (dialog.querySelector('#description')) controls.push('Description');
                            if (dialog.querySelector('[role=spinbutton]')) controls.push('Price');
                            if ([...dialog.querySelectorAll('button')].some(
                                button => button.innerText.trim() === 'Save'
                            )) controls.push('Save');
                            return controls;
                        }""")
                        return {"visible_controls": [
                            {"label": label, "selector": target}
                            for label, (_, _, target, _) in controls.items() if label in visible
                        ]}
                    pending = steps[position:4] if 1 <= position < 4 else steps[position:position + 1]
                    if request.get("action") == "fill_many":
                        selectors = request.get("selectors")
                        by_selector = {item[2]: item for item in pending if item[1] == "fill"}
                        if (
                            not isinstance(selectors, list) or not 2 <= len(selectors) <= 3
                            or not all(isinstance(target, str) and target in by_selector for target in selectors)
                            or len(set(selectors)) != len(selectors)
                        ):
                            return {"error": "Choose distinct unfilled fields in the open form"}
                        selected = [by_selector[target] for target in selectors]
                        remaining = [item for item in pending if item[2] not in selectors]
                        steps[position:4] = selected + remaining
                        position += len(selected)
                        schema = next(tool["inputSchema"] for tool in environment["browse"]["tools"]
                                      if tool["name"] == "fill")
                        try:
                            if "fields" in schema["properties"]:
                                invoke("form_fields", "fill", {"fields": [
                                    {"selector": target, "value": value} for _, _, target, value in selected
                                ]})
                            else:
                                for step, _, target, value in selected:
                                    fill(step, target, value)
                        except Exception as error:
                            failure = error
                            raise
                        return {"status": "accepted"}
                    matches = [
                        item for item in pending if
                        request.get("action") == item[1] and request.get("selector") == item[2]
                    ]
                    if not matches:
                        return {"error": "Action is not allowed in the current form state"}
                    selected, = matches
                    at = steps.index(selected, position)
                    steps[position], steps[at] = steps[at], steps[position]
                    step, tool, selector, value = selected
                    position += 1
                    try:
                        if step == "save":
                            check("entered_fields", fields, [product, description, data.price_cents])
                        if step == "save":
                            try:
                                click(step, selector)
                            except TimeoutError:
                                journal.append(attempt, "sakai:save_uncertain", "recovery", {
                                    "step": "save", "strategy": "verify_dialog_and_read_back",
                                })
                        elif tool == "click":
                            click(step, selector)
                        else:
                            fill(step, selector, value)
                        if step == "new":
                            check("dialog_open", dialog_title, "Product Details")
                        if step == "save":
                            check("saved", closed, True)
                    except Exception as error:
                        failure = error
                        raise
                    return {"status": "creation_complete" if position == len(steps) else "accepted"}

                worker_result = pi_worker(dispatch)
                if failure is not None:
                    raise failure
                if position != len(steps):
                    raise RuntimeError("Pi ended before completing creation")
            else:
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
            if case != "SAKAI-01":
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
            return record("PASS")
        except (RuntimeError, TimeoutError) as error:
            if worker_result is None:
                raise
            return record("FAIL" if isinstance(error, SakaiMismatch) else "INCONCLUSIVE")
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
