"""Acquire and measure a single-component autocomplete skill on local Sakai."""

import argparse
import json
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from time import monotonic_ns, sleep
from urllib.parse import urlsplit
from uuid import uuid4

from qabro.browse_schema import inspect
from qabro.browse_transport import BrowseTransport
from qabro.sakai_comparison import SakaiRun, compare_sakai, markdown_report
from qabro.sakai_pi import bridge, run_opencode

MODEL = "openai/gpt-6-luna"
LOCAL_URL = "http://127.0.0.1:4173/uikit/input"
INPUT = 'role=combobox[name="Search"]'
KEYS = ("ArrowDown", "Enter")
CHECK = "selected_chip"
LEARNING_LABELS = ("Denmark", "Argentina", "Iceland")
MEASUREMENT_LABELS = (
    "Nepal", "Uruguay", "Poland", "Romania", "Greece", "Hungary", "Chile", "Estonia",
    "Latvia", "Lithuania", "Peru", "Singapore", "Slovakia", "Slovenia", "Switzerland", "Thailand",
)
OBSERVE = """() => {
    const el = document.querySelector('input[role=combobox][placeholder=Search]');
    if (!el) return null;
    const list = document.getElementById(el.getAttribute('aria-controls'));
    const focused = document.getElementById(el.getAttribute('aria-activedescendant'));
    return {
        query: el.value, input: 'role=combobox[name="Search"]',
        expanded: el.getAttribute('aria-expanded') === 'true',
        focused: focused?.getAttribute('aria-label') ?? null,
        choices: [...(list?.querySelectorAll('[role=option][aria-disabled=false]') ?? [])]
            .map(option => option.getAttribute('aria-label')),
        selected: [...el.closest('ul').querySelectorAll('[data-pc-section=chipitem]')]
            .map(chip => chip.textContent.trim()),
    };
}"""


def component_tool(assisted):
    actions = ["inspect", "click", "fill", "press"]
    if assisted:
        actions.append("choose")
    return {
        "name": "autocomplete", "description": "Inspect or interact with the country autocomplete widget.",
        "inputSchema": {"type": "object", "properties": {
            "action": {"type": "string", "enum": actions}, "value": {"type": "string"},
        }, "required": ["action"], "additionalProperties": False},
    }


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n")


def run_case(output, opencode, executable, url, target, *, knowledge=None, probe=False):
    origin = f"http://{urlsplit(url).netloc}"
    tab = f"autocomplete-{uuid4().hex}"
    trace = []
    actions = []
    used_skill = False
    session = None
    selected = None
    started = monotonic_ns()

    with BrowseTransport(executable) as browser:
        browser.prepare_tab(tab, allowed_origins=(origin,))
        try:
            def call(tool, args):
                instant = monotonic_ns()
                result = browser(tab, tool, args)
                failed = bool(result.get("isError"))
                trace.append({"tool": tool, "arguments": args, "ok": not failed,
                              "elapsed_ns": monotonic_ns() - instant})
                return {"error" if failed else "text": result["content"][0]["text"]}

            def observe():
                result = call("eval", {"expression": OBSERVE})
                return json.loads(result["text"]) if "text" in result else None

            def wait_for(predicate):
                deadline = monotonic_ns() + 1_500_000_000
                state = observe()
                while not predicate(state) and monotonic_ns() < deadline:
                    sleep(0.1)
                    state = observe()
                return state

            def fill(value):
                return call("fill", {"selector": INPUT, "value": value})

            def press(key):
                return call("press", {"selector": INPUT, "key": key})

            def choose(label, keyboard):
                state = observe()
                if not state or state["query"] != label:
                    result = fill(label)
                    if "error" in result:
                        return result
                state = wait_for(lambda current: current and current["choices"] == [label])
                if not state or state["choices"] != [label]:
                    return {"error": "Expected exactly one matching suggestion"}
                focus_key, confirm_key = keyboard
                if state["focused"] != label:
                    result = press(focus_key)
                    focused = observe()
                    if "error" in result or not focused or focused["focused"] != label:
                        return {"error": "The exact option is not focused"}
                return press(confirm_key)

            def dispatch(request):
                action, value = request.get("action"), request.get("value")
                actions.append(action)
                if action == "inspect":
                    return {"component": observe()}
                if action == "fill" and isinstance(value, str) and len(value) <= 80:
                    return fill(value)
                if action == "press" and value in ("ArrowDown", "ArrowUp", "Enter", "Escape"):
                    return press(value)
                if action == "click" and isinstance(value, str) and value in (observe() or {}).get("choices", []):
                    return call("click", {"selector": f"role=option[name={json.dumps(value)}]"})
                if action == "choose" and knowledge and value == target:
                    return choose(value, knowledge["keys"])
                return {"error": "Action unavailable for this component"}

            def route(request):
                nonlocal used_skill
                result = dispatch(request)
                action = request.get("action")
                if "error" not in result and (action in ("choose", "click") or
                                               action == "press" and request.get("value") == "Enter"):
                    state = observe()
                    if state and state["selected"] == [target]:
                        used_skill = used_skill or action == "choose"
                        return {"status": "selection_verified"}
                return result

            navigation = call("navigate", {"url": url})
            if "error" in navigation:
                raise RuntimeError("Could not open the local autocomplete demo")
            initial = wait_for(lambda state: state is not None)
            if initial is None or initial["selected"]:
                raise RuntimeError("Expected a fresh, empty autocomplete widget")

            if probe:
                choose(target, knowledge["keys"] if knowledge else KEYS)
                tokens = steps = 0
            else:
                prompt = (
                    f"Select exactly one country in the AutoComplete widget, {target}. "
                    "Inspect exposes the current widget state and selected chips. Fill takes query text in value. "
                    "Click takes an option label in value. Press takes a key in value. "
                    f"Stop at selection_verified. Current widget state: {json.dumps(initial)}."
                )
                if knowledge:
                    prompt += (
                        " Available component skill: choose selects the exact singleton suggestion "
                        "in this widget. Use the target label as value."
                    )
                with bridge(route) as env:
                    _, tokens, steps, session = run_opencode(
                        opencode, MODEL, prompt, output, timeout=90, env=env,
                        component_tool=component_tool(bool(knowledge)),
                    )
            observed = observe()
            if observed is not None:
                selected = observed["selected"]
        finally:
            browser(tab, "tabs", {"action": "close"})

    verdict = "PASS" if selected == [target] else "FAIL" if selected else "INCONCLUSIVE"
    return {
        "target": target, "selected": selected, "verdict": verdict,
        "elapsed_ns": monotonic_ns() - started, "tokens": tokens, "model_steps": steps,
        "session": session, "worker_actions": actions, "browser_trace": trace, "used_skill": used_skill,
    }


def acquire(output, opencode, browse, url, schema):
    started = monotonic_ns()
    source, *validation_labels = LEARNING_LABELS
    training = run_case(output, opencode, browse, url, source, probe=True)
    write_json(output / "training.json", training)
    if training["verdict"] != "PASS":
        raise RuntimeError("Explorer probe did not select the expected chip")
    keys = [call["arguments"]["key"] for call in training["browser_trace"] if call["tool"] == "press"]
    if tuple(keys) != KEYS:
        raise RuntimeError("Explorer probe did not observe the exact keyboard behavior")
    response, tokens, steps, _ = run_opencode(
        opencode, MODEL,
        "Evaluate this independently verified PrimeVue AutoComplete observation. One component interaction "
        "typed the target, verified exactly one matching suggestion, focused it and confirmed it. "
        f"The observed keys were {json.dumps(keys)} and the resulting chip matched. "
        'Should this reusable capability be validated? Reply only {"reuse":true} or {"reuse":false}.',
        output, timeout=90,
    )
    decision = json.loads(response)
    if decision != {"reuse": True}:
        write_json(output / "acquisition.json", {"status": "declined", "extraction_tokens": tokens})
        raise RuntimeError("Explorer declined the observed autocomplete capability")
    knowledge = {"component": "PrimeVue AutoComplete", "keys": keys}
    checks = [run_case(output, opencode, browse, url, label, knowledge=knowledge, probe=True)
              for label in validation_labels]
    write_json(output / "validation.json", checks)
    if not all(run["verdict"] == "PASS" for run in checks):
        raise RuntimeError("The component failed independent validation")
    write_json(output / "acquisition.json", {
        "status": "active", "knowledge": knowledge, "url": url, "model": MODEL, "schema": schema,
        "learning_labels": LEARNING_LABELS, "extraction_tokens": tokens, "extraction_steps": steps,
        "elapsed_ns": monotonic_ns() - started,
    })


def measure(output, opencode, browse, url, schema, acquisition, labels):
    content = acquisition.read_bytes()
    frozen = json.loads(content)
    if (frozen["status"], frozen["url"], frozen["model"], frozen["schema"]) != ("active", url, MODEL, schema):
        raise ValueError("Acquisition does not match the URL, model, or browser schema")
    if frozen["knowledge"] != {"component": "PrimeVue AutoComplete", "keys": list(KEYS)}:
        raise ValueError("Unknown component capability")
    if len(labels) != len(set(labels)) or set(labels) & set(frozen["learning_labels"]):
        raise ValueError("Measurement labels must be distinct and separate from learning")
    digest = sha256(content).hexdigest()
    setup = sha256(json.dumps({"schema": schema, "url": url, "model": MODEL}, sort_keys=True).encode()).hexdigest()
    pairs = []
    sessions = set()
    started = monotonic_ns()
    for seed, label in enumerate(labels):
        pair = {}
        for assisted in ((False, True) if seed % 2 == 0 else (True, False)):
            if acquisition.read_bytes() != content:
                raise RuntimeError("Acquisition changed during measurement")
            mode = "assisted" if assisted else "baseline"
            row = run_case(output, opencode, browse, url, label, knowledge=frozen["knowledge"] if assisted else None)
            write_json(output / f"{seed:02d}-{mode}.json", row)
            if not row["session"] or row["session"] in sessions:
                raise RuntimeError("Measurement must use fresh worker sessions")
            sessions.add(row["session"])
            trace = row["browser_trace"]
            passed = row["verdict"] == "PASS"
            pair[assisted] = SakaiRun(
                seed, setup, row["verdict"], (CHECK,) if passed else (),
                row["tokens"], row["model_steps"], row["elapsed_ns"], digest if assisted else None,
                skill_applied=assisted and passed and row["used_skill"],
                mcp_calls=len(trace), browser_actions=sum(call["tool"] != "eval" for call in trace),
                worker_tool_calls=len(row["worker_actions"]), browser_ns=sum(call["elapsed_ns"] for call in trace),
            )
            print(label, mode, row["verdict"], f"{row['elapsed_ns'] / 1_000_000_000:.2f} s", flush=True)
        pairs.append((pair[False], pair[True]))
    if acquisition.read_bytes() != content:
        raise RuntimeError("Acquisition changed during measurement")
    report = compare_sakai(pairs, frozenset({CHECK}), training_tokens=0,
                           extraction_tokens=frozen["extraction_tokens"], validation_tokens=0)
    report.update(acquisition_elapsed_ns=frozen["elapsed_ns"], measurement_elapsed_ns=monotonic_ns() - started,
                  measurement_jobs=1, labels=list(labels))
    write_json(output / "comparison.json", report)
    (output / "report.md").write_text(markdown_report(report))
    print(output / "report.md")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--opencode", default="opencode")
    parser.add_argument("--browse", default="browse")
    parser.add_argument("--url", default=LOCAL_URL)
    parser.add_argument("--label", action="append", help="Repeat to override the default held-out labels")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--train-only", action="store_true")
    mode.add_argument("--candidate-from", type=Path)
    args = parser.parse_args()
    parsed = urlsplit(args.url)
    if parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1") or parsed.path != "/uikit/input":
        parser.error("Use the /uikit/input route on a loopback Sakai deployment")
    schema = inspect(args.browse)["schema_sha256"]
    output = args.output.resolve()
    output.mkdir(mode=0o700)
    if args.train_only:
        acquire(output, args.opencode, args.browse, args.url, schema)
    else:
        measure(output, args.opencode, args.browse, args.url, schema,
                args.candidate_from.resolve(), args.label or MEASUREMENT_LABELS)


if __name__ == "__main__":
    main()
