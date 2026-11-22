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

from qabro.sakai_cases import CREATE_CHECKS
from qabro.sakai_comparison import compare_sakai, markdown_report, measure_sakai, measured_worker_run
from qabro.sakai_training import train_sakai
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


def worker_driver(pi, model, cwd, skill, *, launch=run_pi):
    extension = Path(__file__).with_name("pi") / "sakai.js"
    body = skill.read_text() if skill else None

    def drive(dispatch):
        read_before_price = price_started = False
        tool_calls = 0

        def route(request):
            nonlocal read_before_price, price_started, tool_calls
            tool_calls += 1
            if request.get("action") == "read_skill":
                if body is not None and not price_started:
                    read_before_price = True
                return {"skill": body}
            targets = request.get("selectors")
            if (request.get("action") == "fill" and request.get("selector") == PRICE) or (
                request.get("action") == "fill_many" and isinstance(targets, list) and PRICE in targets
            ):
                price_started = True
            return dispatch(request)

        prompt = (
            "Create the supplied synthetic product using the sakai tool. "
            "Read the available skill if one is offered. Inspect visible controls and decide which action to take next. "
            "For fill, send one selector. For independent visible fields you choose to fill together, "
            "send fill_many with a selectors array. The host inserts their supplied values. "
            "The host runs all checks automatically, including dialog_open; do not stop to run them. "
            "An accepted response means continue to the next step. If unsure, inspect again. "
            "Stop only on creation_complete or if the tool says creation is stopped."
        )
        prompt += "\nSkill available: " + ("yes" if body is not None else "no")
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
    parser.add_argument("--codex", help="Use the signed-in Codex CLI instead of Pi")
    parser.add_argument("--pairs", type=int, default=5)
    parser.add_argument("--browse", default="browse")
    parser.add_argument("--model", required=True)
    parser.add_argument("--url", default=PUBLIC_URL)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--experiment", action="store_true", help="Train, validate, and measure five A/B pairs")
    parser.add_argument("--resume-training", action="store_true", help="Reuse a completed baseline before extraction")
    parser.add_argument("--candidate-from", type=Path, help="Reuse a previously validated experiment directory")
    parser.add_argument("--measurement-seed", type=int)
    args = parser.parse_args()
    if args.candidate_from and (not args.experiment or args.resume_training or args.measurement_seed is None):
        parser.error("--candidate-from requires --experiment and a fresh --measurement-seed")
    if args.resume_training and not args.experiment:
        parser.error("--resume-training requires --experiment")
    if not 1 <= args.pairs <= 5:
        parser.error("--pairs expects between one and five pairs")
    launch = run_codex if args.codex else run_pi
    executable = args.codex or args.pi
    output = args.output.resolve()
    if not args.resume_training:
        output.mkdir(mode=0o700)


    def run_worker(seed, skill):
        label = "assisted" if skill else "baseline"
        directory = output / f"{seed}-{label}"
        if args.resume_training and seed == args.seed and skill is None:
            saved = json.loads((directory / "smoke.json").read_text())
            environment = json.loads((directory / "environment.json").read_text())
            model = f"codex/{args.model}" if args.codex else args.model
            if environment.get("model") != model or environment.get("target_url") != args.url:
                raise ValueError("Saved training run used a different model or target")
            return directory / "smoke.sqlite", saved["attempt"]
        result = smoke(
            directory, args.browse, args.url, case="SAKAI-02", seed=seed,
            series=f"series-{seed}", pi_worker=worker_driver(
                executable, args.model, output, skill, launch=launch,
            ),
            model=f"codex/{args.model}" if args.codex else args.model, skill_sha256=sha256(skill.read_bytes()).hexdigest() if skill else None,
        )
        return directory / "smoke.sqlite", result["attempt"]

    if not args.experiment:
        database, attempt = run_worker(args.seed, None)
        from dataclasses import asdict

        print(json.dumps(asdict(measured_worker_run(database, attempt)), indent=2))
        return

    from qabro.browse_schema import inspect

    sources = {}
    def record_worker(seed, skill):
        result = run_worker(seed, skill)
        sources[result[1]] = result[0]
        return result

    def explorer(prompt):
        text, tokens, _, _ = launch(executable, args.model, prompt, output, timeout=90)
        return text, tokens

    seeds = tuple(range(args.seed, args.seed + 3))
    if args.candidate_from:
        previous = args.candidate_from.resolve()
        candidate_dir = previous / "candidate"
        candidate = json.loads((candidate_dir / "manifest.json").read_text())
        prior = json.loads((previous / "comparison.json").read_text())
        earlier_seeds = {
            int(path.parent.name.removesuffix("-baseline").removesuffix("-assisted"))
            for path in previous.glob("*/smoke.json")
        }
        baseline_seed = prior["pairs"][0]["seed"]
        environment = json.loads((previous / f"{baseline_seed}-baseline" / "environment.json").read_text())
        model = f"codex/{args.model}" if args.codex else args.model
        if environment.get("model") != model or environment.get("target_url") != args.url:
            raise ValueError("Saved experiment used a different model or target")
        if candidate.get("id") != "sakai-price-input":
            raise ValueError("Expected a component skill; legacy creation skills cannot be used")
        if candidate.get("status") != "active":
            raise ValueError("Expected a previously validated candidate")
        if candidate["browser_capabilities_sha256"] != inspect(args.browse)["schema_sha256"]:
            raise ValueError("Browser schema changed since candidate validation")
        learning = prior["learning_tokens"]
    else:
        candidate_dir = output / "candidate"
        candidate = train_sakai(candidate_dir, inspect(args.browse)["schema_sha256"], seeds, record_worker, explorer)
        training, = candidate["source_attempt_ids"]
        def cost(attempt):
            return measured_worker_run(sources[attempt], attempt).tokens
        learning = {
            "training": cost(training), "extraction": candidate["extraction_tokens"],
            "validation": sum(cost(attempt) for attempt in candidate["validation_attempt_ids"]),
        }
        earlier_seeds = set()
    first_seed = args.measurement_seed if args.measurement_seed is not None else args.seed + 3
    pairs = measure_sakai(
        candidate_dir, tuple(range(first_seed, first_seed + args.pairs)), frozenset(seeds) | earlier_seeds,
        lambda seed, skill: measured_worker_run(*run_worker(seed, skill)),
    )
    comparison = compare_sakai(
        pairs, frozenset(CREATE_CHECKS), training_tokens=learning["training"],
        extraction_tokens=learning["extraction"], validation_tokens=learning["validation"],
    )
    comparison["assisted_mode"] = "component_skill"
    (output / "comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")
    (output / "report.md").write_text(markdown_report(comparison))
    print(output / "report.md")


if __name__ == "__main__":
    main()
