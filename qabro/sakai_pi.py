"""Run a minimal Pi worker or text-only explorer for the Sakai experiment."""

import argparse
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from secrets import token_urlsafe
from threading import Thread
from time import monotonic_ns
from tempfile import TemporaryDirectory

from qabro.sakai_cases import CREATE_CHECKS
from qabro.opencode_metrics import summarize
from qabro.sakai_comparison import compare_sakai, markdown_report, measure_sakai, measured_worker_run
from qabro.sakai_training import ExplorerDeclined, train_sakai
from qabro.sakai_smoke import PRICE, PUBLIC_URL, smoke


def run_pi(executable, model, prompt, cwd, *, timeout, extension=None, env=None):
    command = [
        executable, "--mode", "json", "--no-session", "--model", model,
        "--no-extensions", "--no-mcp", "--no-skills", "--no-context-files",
        "--no-prompt-templates", "--no-builtin-tools" if extension else "--no-tools",
    ]
    if extension:
        command.extend(["--extension", str(extension)])
    result = subprocess.run(
        [*command, prompt], cwd=cwd, env={**os.environ, **(env or {})},
        timeout=timeout, capture_output=True, text=True,
    )
    events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    messages = [event["message"] for event in events
                if event["type"] == "message_end" and event["message"]["role"] == "assistant"]
    if result.returncode or not messages or any(
        msg.get("stopReason") in {"aborted", "error"} for msg in messages
    ) or not any(event["type"] == "agent_settled" and not event.get("aborted") for event in events):
        raise RuntimeError("Pi did not complete the session. Check model availability and Pi configuration.")
    session = next(event["id"] for event in events if event["type"] == "session")
    body = "\n".join(block["text"] for block in messages[-1]["content"] if block["type"] == "text")
    return body, sum(message["usage"]["totalTokens"] for message in messages), len(messages), session


def run_codex(executable, model, prompt, cwd, *, timeout, extension=None, env=None):
    environment = {**os.environ, **(env or {})}
    for override in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL"):
        environment.pop(override, None)
    login = subprocess.run(
        [executable, "login", "status"], cwd=cwd, env=environment,
        capture_output=True, text=True, timeout=10,
    )
    if login.returncode or "Logged in using ChatGPT" not in login.stdout + login.stderr:
        raise RuntimeError("Codex must be signed in using ChatGPT for this experiment")
    command = [
        executable, "exec", "--json", "--ephemeral", "--ignore-user-config", "--skip-git-repo-check",
        "--sandbox", "read-only", "--disable", "shell_tool", "--disable", "plugins",
        "-c", 'web_search="disabled"', "-c", 'model_provider="openai"', "-m", model,
    ]
    if extension:
        shim = Path(__file__).with_name("sakai_codex_mcp.py")
        command.extend([
            "-c", "mcp_servers.sakai.command=" + json.dumps(sys.executable),
            "-c", "mcp_servers.sakai.args=" + json.dumps([str(shim)]),
            "-c", 'mcp_servers.sakai.env_vars=["QABRO_SAKAI_BRIDGE","QABRO_SAKAI_TOKEN"]',
            "-c", 'mcp_servers.sakai.tools.sakai.approval_mode="approve"',
        ])
    result = subprocess.run(
        [*command, prompt], cwd=cwd, env=environment, timeout=timeout,
        capture_output=True, text=True,
    )
    events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    if result.returncode or not any(event["type"] == "turn.completed" for event in events):
        raise RuntimeError("Codex did not complete the session")
    usage = next(event["usage"] for event in events if event["type"] == "turn.completed")
    session = next(event["thread_id"] for event in events if event["type"] == "thread.started")
    messages = [event["item"]["text"] for event in events
                if event["type"] == "item.completed" and event["item"]["type"] == "agent_message"]
    body = messages[-1].strip() if messages else ""
    if body.startswith("```markdown\n") and body.endswith("\n```"):
        body = body.removeprefix("```markdown\n").removesuffix("\n```")
    return body, usage["input_tokens"] + usage["output_tokens"], None, session


def run_opencode(executable, model, prompt, cwd, *, timeout, extension=None, env=None, component_tool=None):
    if model != "openai/gpt-6-luna":
        raise ValueError("The OpenCode adapter uses subscription model openai/gpt-6-luna")
    environment = {**os.environ, **(env or {})}
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENCODE_CONFIG", "OPENCODE_CONFIG_CONTENT"):
        environment.pop(key, None)
    environment["OPENCODE_DISABLE_PLUGIN"] = "true"
    environment["OPENCODE_DISABLE_EXTERNAL_SKILLS"] = "true"
    environment.pop("QABRO_COMPONENT_TOOL", None)
    if component_tool is not None:
        environment["QABRO_COMPONENT_TOOL"] = json.dumps(component_tool)
    config = {
        "permission": {"*": "deny"},
        "share": "disabled",
        "autoupdate": False,
        "enabled_providers": ["openai"],
    }
    if extension or component_tool is not None:
        shim = Path(__file__).with_name("sakai_codex_mcp.py")
        config["mcp"] = {"qabro": {"type": "local", "command": [sys.executable, str(shim)]}}
        config["permission"]["qabro_*"] = "allow"
    with TemporaryDirectory(prefix="opencode-", dir=cwd) as workspace:
        environment["OPENCODE_CONFIG_DIR"] = workspace
        (Path(workspace) / "opencode.json").write_text(json.dumps(config))
        auth = subprocess.run(
            [executable, "auth", "export"], cwd=workspace, env=environment,
            timeout=10, capture_output=True, text=True,
        )
        try:
            accounts = json.loads(auth.stdout) if auth.returncode == 0 else []
            oauth = any(
                account["integrationID"] == "openai" and account["active"]
                and account["value"]["type"] == "oauth"
                and account["value"]["methodID"] == "chatgpt-token-sharing"
                for account in accounts
            )
        except (TypeError, ValueError, KeyError):
            oauth = False
        if not oauth:
            raise RuntimeError("OpenCode requires an active OpenAI OAuth sign-in")
        del accounts, auth
        result = subprocess.run(
            [executable, "--standalone", "run", "--archived", "--auto", "--format", "json", "-m", model, prompt],
            cwd=workspace, env=environment, timeout=timeout, capture_output=True, text=True,
        )
    events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    finishes = [event["part"] for event in events if event["type"] == "step_finish"]
    if result.returncode or not finishes or any(event["type"] == "error" for event in events):
        raise RuntimeError("OpenCode did not complete the Luna session")
    usage = summarize(result.stdout.splitlines())
    tokens = sum(usage[counter] for counter in (
        "input_tokens", "output_tokens", "reasoning_tokens", "cache_read_tokens", "cache_write_tokens",
    ))
    body = "\n".join(event["part"]["text"] for event in events if event["type"] == "text").strip()
    if body.startswith("```json\n") and body.endswith("\n```"):
        body = body.removeprefix("```json\n").removesuffix("\n```")
    return body, tokens, len(finishes), events[0]["sessionID"]


@contextmanager
def bridge(dispatch):
    secret = token_urlsafe()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            if self.headers.get("Authorization") != f"Bearer {secret}":
                self.send_error(403)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 4096:
                    raise ValueError
                result = dispatch(json.loads(self.rfile.read(size)))
            except (TypeError, ValueError):
                self.send_error(400)
                return
            except Exception as error:
                result = {"error": type(error).__name__}
            payload = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield {
                "QABRO_SAKAI_BRIDGE": f"http://127.0.0.1:{server.server_port}/",
                "QABRO_SAKAI_TOKEN": secret,
            }
        finally:
            server.shutdown()
            thread.join()


def worker_driver(pi, model, cwd, skill, *, launch=run_pi, validate_skill=False):
    extension = Path(__file__).with_name("pi") / "sakai.js"
    body = skill.read_text() if skill else None
    form = json.loads(body.split("\n\n", 1)[1]) if body and body.startswith("# Sakai Product Details controls\n") else None

    def drive(dispatch):
        read_before_price = price_started = False
        form_delivered = False
        tool_calls = 0

        def route(request):
            nonlocal read_before_price, price_started, tool_calls, form_delivered
            tool_calls += 1
            if request.get("action") == "read_skill":
                if body is not None and not form and not price_started:
                    read_before_price = True
                return {"skill": body}
            targets = request.get("selectors")
            if (request.get("action") == "fill" and request.get("selector") == PRICE) or (
                request.get("action") == "fill_many" and isinstance(targets, list) and PRICE in targets
            ):
                read_before_price = read_before_price or form_delivered
                if validate_skill and not read_before_price:
                    return {"error": "Read the candidate before filling Price in this validation attempt"}
                price_started = True
            outcome = dispatch(request)
            if form and outcome.get("component_scope") == form["scope"]:
                form_delivered = True
                return {**outcome, "visible_controls": [
                    {"label": label, "selector": selector} for label, selector in form["controls"].items()
                ]}
            return outcome

        prompt = (
            "Create the supplied synthetic product using the sakai tool. "
            "Use the latest controls returned by the tool, or inspect if none are available. Decide the next action. "
            "If a skill is offered, read it only when it could resolve an interaction you are unsure about. "
            "For fill, send one selector. For independent visible fields you choose to fill together, "
            "send fill_many with a selectors array. The host inserts their supplied values. "
            "The host runs all checks automatically, including dialog_open; do not stop to run them. "
            "An accepted response means continue to the next step. If unsure, inspect again. "
            "Stop only on creation_complete or if the tool says creation is stopped."
        )
        prompt += "\nAvailable component skill: " + ("Sakai Price input" if body is not None and not form else "none")
        if validate_skill and not form:
            prompt += "\nThis is a validation attempt. Read the Price skill before filling Price."
        with bridge(route) as env:
            body_text, tokens, calls, session = launch(
                pi, model, prompt, cwd, timeout=90, extension=extension,
                env={**env, "QABRO_SAKAI_TURNS": "12"},
            )
        return body_text, tokens, calls, session, read_before_price, tool_calls

    return drive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--pi", default="pi")
    harness = parser.add_mutually_exclusive_group()
    harness.add_argument("--opencode", help="Use the subscription-backed OpenCode CLI")
    harness.add_argument("--codex", help="Use the signed-in Codex CLI instead of Pi")
    parser.add_argument("--pairs", type=int, default=5)
    parser.add_argument("--jobs", type=int, default=1, help="Run independent held-out pairs concurrently")
    parser.add_argument("--browse", default="browse")
    parser.add_argument("--model", required=True)
    parser.add_argument("--url", default=PUBLIC_URL)
    parser.add_argument("--seed", type=int, default=1)
    phase = parser.add_mutually_exclusive_group()
    phase.add_argument("--experiment", action="store_true", help="Measure held-out pairs, training first if needed")
    phase.add_argument("--train-only", action="store_true", help="Finish exploration and validation without measuring")
    parser.add_argument("--learn-form", action="store_true", help="Learn an unordered component control map")
    parser.add_argument("--resume-training", action="store_true", help="Reuse a completed baseline before extraction")
    parser.add_argument("--candidate-from", type=Path, help="Reuse a previously validated experiment directory")
    parser.add_argument("--measurement-seed", type=int)
    parser.add_argument("--require-skill", action="store_true", help="Require skill use in assisted measurement")
    args = parser.parse_args()
    if args.candidate_from and (not args.experiment or args.resume_training or args.measurement_seed is None):
        parser.error("--candidate-from requires --experiment and a fresh --measurement-seed")
    if args.resume_training and not (args.experiment or args.train_only):
        parser.error("--resume-training requires --experiment or --train-only")
    if args.require_skill and not args.experiment:
        parser.error("--require-skill requires --experiment")
    if not 1 <= args.pairs <= 30:
        parser.error("--pairs expects between one and thirty pairs")
    if args.pairs > 5 and args.url == PUBLIC_URL:
        parser.error("Use a loopback Sakai deployment for batches larger than five pairs")
    if not 1 <= args.jobs <= args.pairs:
        parser.error("--jobs must be between one and the number of pairs")
    if args.jobs > 1 and (not args.experiment or args.url == PUBLIC_URL):
        parser.error("Concurrent pairs require --experiment and a loopback Sakai deployment")
    launch = run_opencode if args.opencode else run_codex if args.codex else run_pi
    executable = args.opencode or args.codex or args.pi
    model = f"opencode/{args.model}" if args.opencode else f"codex/{args.model}" if args.codex else args.model
    output = args.output.resolve()
    if not args.resume_training:
        output.mkdir(mode=0o700)


    def run_worker(seed, skill, *, validate_skill=False):
        label = "assisted" if skill else "baseline"
        directory = output / f"{seed}-{label}"
        if args.resume_training and seed == args.seed and skill is None:
            saved = json.loads((directory / "smoke.json").read_text())
            environment = json.loads((directory / "environment.json").read_text())
            if environment.get("model") != model or environment.get("target_url") != args.url:
                raise ValueError("Saved training run used a different model or target")
            return directory / "smoke.sqlite", saved["attempt"]
        result = smoke(
            directory, args.browse, args.url, case="SAKAI-02", seed=seed,
            series=f"series-{seed}", pi_worker=worker_driver(
                executable, args.model, output, skill, launch=launch, validate_skill=validate_skill,
            ),
            model=model, skill_sha256=sha256(skill.read_bytes()).hexdigest() if skill else None,
        )
        return directory / "smoke.sqlite", result["attempt"]

    if not (args.experiment or args.train_only):
        database, attempt = run_worker(args.seed, None)
        from dataclasses import asdict

        print(json.dumps(asdict(measured_worker_run(database, attempt)), indent=2))
        return

    from qabro.browse_schema import inspect

    sources = {}
    def record_worker(seed, skill):
        result = run_worker(seed, skill, validate_skill=skill is not None)
        sources[result[1]] = result[0]
        return result

    def explorer(prompt):
        text, tokens, _, _ = launch(executable, args.model, prompt, output, timeout=90)
        return text, tokens

    seeds = tuple(range(args.seed, args.seed + 3))
    acquisition_elapsed_ns = None
    if args.candidate_from:
        previous = args.candidate_from.resolve()
        candidate_dir = previous / "candidate"
        earlier_seeds = {
            int(path.parent.name.removesuffix("-baseline").removesuffix("-assisted"))
            for path in previous.glob("*/smoke.json")
        }
        acquisition_path = previous / "acquisition.json"
        if acquisition_path.is_file():
            prior = json.loads(acquisition_path.read_text())
            if prior["status"] != "active":
                parser.error("The saved acquisition did not produce an active candidate")
            environment = prior
            acquisition_elapsed_ns = prior["elapsed_ns"]
            earlier_seeds.update(prior["learning_seeds"])
        else:
            prior = json.loads((previous / "comparison.json").read_text())
            baseline_seed = prior["pairs"][0]["seed"]
            environment = json.loads((previous / f"{baseline_seed}-baseline" / "environment.json").read_text())
        candidate = json.loads((candidate_dir / "manifest.json").read_text())
        if acquisition_path.is_file() and prior["skill_sha256"] != candidate["content_sha256"]:
            raise ValueError("Saved acquisition refers to a different candidate revision")
        if environment.get("model") != model or environment.get("target_url") != args.url:
            raise ValueError("Saved experiment used a different model or target")
        if candidate.get("id") not in {"sakai-price-input", "sakai-form-controls"}:
            raise ValueError("Expected a component skill; legacy creation skills cannot be used")
        if candidate.get("status") != "active":
            raise ValueError("Expected a previously validated candidate")
        if candidate["browser_capabilities_sha256"] != inspect(args.browse)["schema_sha256"]:
            raise ValueError("Browser schema changed since candidate validation")
        learning = prior["learning_tokens"]
    else:
        acquisition_started = monotonic_ns()
        candidate_dir = output / "candidate"
        def cost(attempt):
            return measured_worker_run(sources[attempt], attempt).tokens
        try:
            candidate = train_sakai(
                candidate_dir, inspect(args.browse)["schema_sha256"], seeds, record_worker, explorer,
                learn_form=args.learn_form,
            )
        except ExplorerDeclined as decision:
            candidate = None
            training, = sources
            learning = {"training": cost(training), "extraction": decision.tokens, "validation": 0}
        else:
            training, = candidate["source_attempt_ids"]
            learning = {
                "training": cost(training), "extraction": candidate["extraction_tokens"],
                "validation": sum(cost(attempt) for attempt in candidate["validation_attempt_ids"]),
            }
        if not args.resume_training:
            acquisition_elapsed_ns = monotonic_ns() - acquisition_started
        acquisition = {
            "model": model, "target_url": args.url,
            "status": "active" if candidate else "declined",
            "learning_seeds": seeds, "skill_sha256": candidate["content_sha256"] if candidate else None,
            "learning_tokens": learning,
            "elapsed_ns": acquisition_elapsed_ns,
        }
        acquisition_path = output / "acquisition.json"
        acquisition_path.write_text(json.dumps(acquisition, indent=2) + "\n")
        earlier_seeds = set()
        if args.train_only:
            print(acquisition_path)
            return
        if candidate is None:
            parser.error(f"No candidate qualified for measurement. See {acquisition_path}")
    first_seed = args.measurement_seed if args.measurement_seed is not None else args.seed + 3
    started = monotonic_ns()
    pairs = measure_sakai(
        candidate_dir, tuple(range(first_seed, first_seed + args.pairs)), frozenset(seeds) | earlier_seeds,
        lambda seed, skill: measured_worker_run(*run_worker(
            seed, skill, validate_skill=args.require_skill and skill is not None,
        )),
        jobs=args.jobs,
    )
    measurement_elapsed_ns = monotonic_ns() - started
    comparison = compare_sakai(
        pairs, frozenset(CREATE_CHECKS), training_tokens=learning["training"],
        extraction_tokens=learning["extraction"], validation_tokens=learning["validation"],
    )
    comparison["assisted_mode"] = "required_component_skill" if args.require_skill else "component_skill"
    comparison["measurement_jobs"] = args.jobs
    comparison["measurement_elapsed_ns"] = measurement_elapsed_ns
    comparison["acquisition_elapsed_ns"] = acquisition_elapsed_ns
    (output / "comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")
    (output / "report.md").write_text(markdown_report(comparison))
    print(output / "report.md")


if __name__ == "__main__":
    main()
