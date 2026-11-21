# QA Bro

QA Bro is a proposed local skill system for an existing Pi QA agent that drives a browser through opencode browse. It learns from UI test runs so the agent can reuse a verified hint or replay a recurring operation with fewer model calls. The agent chooses when to use a skill. The source scenario determines the actions and expected results.

## Project status

The specification and implementation backlog are available. Development can start with an opencode session, browse and a local fixture. Integration with the existing Pi harness and validation on corporate platforms take place inside the corporate environment.

- [Design specification](SPEC.md)
- [Glossary](GLOSSARY.md)
- [Implementation issues](https://github.com/butahlecoq/qa-bro/issues)
- [Delivery milestones](https://github.com/butahlecoq/qa-bro/milestones)

Start with [baseline capture](https://github.com/butahlecoq/qa-bro/issues/1) and [the scenario and evidence contract](https://github.com/butahlecoq/qa-bro/issues/2). Each issue lists its prerequisites and acceptance criteria.

## Local browser smoke test

Start a browse relay paired with a dedicated Chromium profile and serve the fixture from the repository root.

```sh
python -m http.server 18765 --bind 127.0.0.1 --directory tests/fixtures
```

Run these commands in another terminal using the same browse relay configuration. Browse requires an explicit allowed origin for loopback navigation.

```sh
python -m qabro.browse_schema
browse tabs --json '{"action":"new","id":"fixture-ok","allowedOrigins":["http://127.0.0.1:18765"]}'
browse tabs --json '{"action":"new","id":"fixture-defect","allowedOrigins":["http://127.0.0.1:18765"]}'
python -m qabro.baseline --database /tmp/qabro-smoke.sqlite --tab fixture-ok --url http://127.0.0.1:18765/requirements.html
python -m qabro.baseline --database /tmp/qabro-smoke.sqlite --tab fixture-defect --url 'http://127.0.0.1:18765/requirements.html?wrong-category'
```

Expect `PASS` for the first run and `FAIL` for the second. Each run reports seven browser calls and zero model calls. The runner uses fixed inputs for this transport check. Both results were verified with browse 0.1.5 and Chromium 155. The opencode agent baseline and corporate Pi integration are tracked in issue #1.

### OpenCode agent baseline

Use a disposable Git workspace and the paired relay from the browser smoke test. OpenCode v2.3.0 reads the MCP configuration from that project's root.

```sh
project_root="$PWD"
agent_workspace="$(mktemp -d)"
git -C "$agent_workspace" init -q
browse_path="$(command -v browse)"
(
  cd "$agent_workspace"
  opencode mcp add browse -- "$browse_path" mcp
  opencode --standalone run --archived --auto --format json \
    -m opencode/deepseek-v4.1-flash-free \
    'Use browse on http://127.0.0.1:18765/requirements.html. Open a fresh named tab qa-agent-fixture with allowedOrigins ["http://127.0.0.1:18765"]. Fill Name with Agent sample, Due date with 2027-01-20, select Operations, and click Create once. Verify that the created row is exactly Agent sample | 2027-01-20 | operations. Report PASS or FAIL and the observed row.' \
    > baseline.jsonl
)
cd "$project_root"
python -m qabro.opencode_metrics < "$agent_workspace/baseline.jsonl"
```

On the verified run the agent reported `PASS` with the exact expected row. The JSONL trace recorded ten completed model steps, nine OpenCode tool dispatches, and 31.2 seconds between the first and last events. OpenCode v2 exposes browser MCP tools through its `execute` dispatcher, so its dispatch count can differ from the number of individual browser calls.

To exercise the controlled defect, append `?wrong-category` to the fixture URL in the prompt and choose a different tab name. Keep the expected row unchanged. In the verified run, the browser returned `Agent sample | 2027-01-20 | wrong` after reporting successful creation. The agent reported `FAIL`. The trace recorded 11 completed model steps, 10 OpenCode tool dispatches, and 29.4 seconds between the first and last events.

For the corporate Pi smoke test, use the existing authenticated harness with an empty skill catalog. Record the installed browse schema, ordered step and tool events, attempt verdict, evidence references, and model usage for one existing scenario. Verify that the references resolve locally and that the stored trace omits authentication material.
