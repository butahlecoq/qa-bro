"""Run a minimal Pi worker or text-only explorer for the Sakai experiment."""

import argparse
import json
import os
import subprocess
from contextlib import contextmanager
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from secrets import token_urlsafe
from threading import Thread

from qabro.sakai_cases import CREATE_CHECKS
from qabro.sakai_comparison import compare_sakai, markdown_report, measure_sakai, measured_worker_run
from qabro.sakai_training import train_sakai
from qabro.sakai_smoke import PUBLIC_URL, smoke


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


def worker_driver(pi, model, cwd, skill):
    extension = Path(__file__).with_name("pi") / "sakai.js"
    body = skill.read_text() if skill else None

    def drive(dispatch):
        read_before_action = acted = False

        def route(request):
            nonlocal read_before_action, acted
            if request.get("action") == "read_skill":
                if body is not None and not acted:
                    read_before_action = True
                return {"skill": body}
            if request.get("action") in {"click", "fill"}:
                acted = True
            return dispatch(request)

        prompt = (
            "Create the supplied synthetic product using the sakai tool. "
            "Read the available skill if one is offered. Inspect the UI if you need a selector. "
            "Fill the three inputs and save once. The host verifies the result. "
            "Stop when creation completes."
        )
        prompt += "\nSkill available: " + ("yes" if body is not None else "no")
        with bridge(route) as env:
            body_text, tokens, calls, session = run_pi(
                pi, model, prompt, cwd, timeout=90, extension=extension,
                env={**env, "QABRO_SAKAI_TURNS": "12"},
            )
        return body_text, tokens, calls, session, read_before_action

    return drive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--pi", default="pi")
    parser.add_argument("--browse", default="browse")
    parser.add_argument("--model", required=True)
    parser.add_argument("--url", default=PUBLIC_URL)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--experiment", action="store_true", help="Train, validate, and measure five A/B pairs")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(mode=0o700)
    def run_worker(seed, skill):
        label = "assisted" if skill else "baseline"
        directory = output / f"{seed}-{label}"
        result = smoke(
            directory, args.browse, args.url, case="SAKAI-02", seed=seed,
            series=f"series-{seed}", pi_worker=worker_driver(args.pi, args.model, output, skill),
            model=args.model, skill_sha256=sha256(skill.read_bytes()).hexdigest() if skill else None,
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
        text, tokens, _, _ = run_pi(args.pi, args.model, prompt, output, timeout=90)
        return text, tokens

    seeds = tuple(range(args.seed, args.seed + 3))
    candidate_dir = output / "candidate"
    candidate = train_sakai(candidate_dir, inspect(args.browse)["schema_sha256"], seeds, record_worker, explorer)
    training, = candidate["source_attempt_ids"]
    cost = lambda attempt: measured_worker_run(sources[attempt], attempt).tokens
    pairs = measure_sakai(
        candidate_dir, tuple(range(args.seed + 3, args.seed + 8)), frozenset(seeds),
        lambda seed, skill: measured_worker_run(*run_worker(seed, skill)),
    )
    comparison = compare_sakai(
        pairs, frozenset(CREATE_CHECKS), training_tokens=cost(training),
        extraction_tokens=candidate["extraction_tokens"],
        validation_tokens=sum(cost(attempt) for attempt in candidate["validation_attempt_ids"]),
    )
    (output / "comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")
    (output / "report.md").write_text(markdown_report(comparison))
    print(output / "report.md")


if __name__ == "__main__":
    main()
