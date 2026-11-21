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

Run these commands in another terminal using the same dedicated relay configuration. Start or restart that relay with `OPENCODE_BROWSER_TOOLS=plain` so its MCP tool list includes the individual browser operations. Browse requires an explicit allowed origin for loopback navigation.

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

For the corporate Pi smoke test, use the existing authenticated harness with an empty skill catalog. Record the installed browse schema, ordered step and tool events, attempt verdict, evidence references, and model usage for one existing scenario. Record measured `model_calls`, `input_tokens`, `output_tokens` and `elapsed_ns` in the attempt's `baseline:usage` event. Run `python -m qabro.baseline_evidence DATABASE ATTEMPT_ID` to check source step order, installed tool identities and evidence references. The command prints an evidence summary without raw browser output. Inspect persisted evidence locally to verify that authentication material was redacted.

### Skill lookup from an existing agent

The local skills MCP server pins the catalog when it starts. The worker supplies a unique run ID, the observed UI scope, and its verified browser capabilities. The agent calls `find_skills` for summaries and `read_hint` with the ID and revision of a result it chooses. An empty result lets the agent continue its ordinary workflow.

Run this from the repository root to seed a hint for the local fixture and connect it to a disposable OpenCode project.

```sh
project_root="$PWD"
agent_workspace="$(mktemp -d)"
git -C "$agent_workspace" init -q
python - "$agent_workspace/catalog.sqlite" <<'PY'
from pathlib import Path
from sys import argv

from qabro.catalog import Catalog, Scope, SkillRef

Catalog(Path(argv[1])).seed_verified_hint(
    SkillRef("fixture-date", "1", "Choose date"),
    Scope("fixture", "form", "requirements", "editor"),
    "Use the date field for the due date.",
)
PY
(
  cd "$agent_workspace"
  opencode mcp add qa-skills --env "PYTHONPATH=$project_root" -- \
    "$(command -v python)" -m qabro.skill_mcp "$agent_workspace/catalog.sqlite" \
    smoke fixture form requirements editor
  opencode --standalone run --archived --auto --format json \
    -m opencode/deepseek-v4.1-flash-free \
    'Find skills for date with qa-skills, read the offered hint, and return its exact text.'
)
```

### Local retention

Run retention against the local evidence database when the tester's workspace is idle.

```sh
python -m qabro.retention /tmp/qabro-smoke.sqlite --age-days 30 --journal-bytes 10000000 --artifact-bytes 100000000
```

The report counts stored payload bytes. SQLite file size also includes indexes, free pages, and database overhead. Active leases, unresolved effects, and pinned evidence can keep usage above the configured limits.

## Learn a hint from recorded runs

Attach `record_verified_steps` to the scenario runner with an operation label for the reusable behavior. Run `scan_experience` against the local journal and queue once multiple attempts have recorded the same costly operation in the same scope. Routine clicks can be excluded when recording episodes.

Use `synthesize_next_hint` with the worker's configured text model callback. It reads the source artifacts, filters known run values and snapshot references, and asks for a hint with an excerpt from a recorded observation. The explorer records the token and browser costs against the job. A draft enters the validation queue with its source evidence and becomes discoverable only after independent validation.

### Replay a recipe

A recipe maps each browser action to its original scenario step. Replay resolves bindings and registered observations at runtime, applies typed checks, and records each dispatched action through the ordinary browser dispatcher. Nested recipes use pinned revisions. Repeated observations have both an iteration limit and a deadline. Scenario assertions remain in their original positions.

Use `report_run` with the journal and run ID to inspect replay progress. The report shows the stopping point, recorded arguments, evidence references, and whether effects are complete, partial, absent, or unknown. A command that returned and a scenario assertion that matched are recorded independently.

### Validate a recipe before publication

For each independent validation attempt, record the installed browse tool list as a `browse:schema` journal event using `snapshot_schema`. Keep the action and checkpoint evidence in the same database as the catalog. Validation requires three fresh attempts and at least two datasets when the source permits variation.

When a controlled defect fixture is available, supply `defect_trials` to `validate_next_hint`. Return the persisted plain and recipe attempt IDs for each trial. Both modes must report the same observed checkpoint failure. On an already published revision, use `quarantine_false_pass` after a controlled comparison confirms a false pass. A shared product failure leaves the active revision in place.

## Compiled execution trial

Plain browse dispatch remains the default. In a paired local Chromium trial, the single-call prototype preserved the ordered step outcomes and final form state on success and on a failed checkpoint. With a missing target after a successful fill, the form retained the first value on both backends. When the outer `execute` deadline expired during target resolution, the response omitted the completed step prefix. This prevents recovery from using the returned trace to locate the partial effect, so latency savings cannot qualify this prototype for activation.

Run the paired trial with the same relay and fixture as the smoke test. Set `QABRO_BROWSE` if the browse executable is outside `PATH`.

```sh
QABRO_FIXTURE_URL=http://127.0.0.1:18765/requirements.html \
  python -m unittest discover -s tests -p test_live_compiled_browser.py -v
```

## Report a pilot

Run the reporting command inside the environment that ran the pilot.

```sh
python -m qabro.pilot pilot.json > pilot-report.json
```

A frozen export has `kind: "frozen"`, `training_workflows`, `learning` costs keyed by mode, and `trials`. Each trial has a `case` with `id`, `workflow` and `expected`, along with the trial's `mode`, `setup`, `verdict`, `elapsed_ns`, `worker_tokens` and measured `usage`. Use the same setup identifier for matched trials across all four modes. The identifier should pin model, data, browser and budgets. Report explorer and validation costs in `learning`. An optional `release` entry supplies `minimum_tokens_saved` and per-case `evidence` containing mandatory and reported condition IDs and the observed number of duplicate effects.

To report skill break-even, add a `skills` object keyed by skill ID and revision. Each entry lists ordered `uses` with `case_id` and assisted `mode`, per-skill `learning` costs, and optional `maintenance_tokens`. Attribute a use only when the run actually reused the skill. Each use is paired with that case's baseline trial.

An online export has `kind: "online"` and ordered `attempts`. Each entry includes `attempt_id`, `trial`, `available_revisions` as skill ID and revision pairs, and `learning_since_previous`. Set `final_learning` for costs incurred after the final attempt. Keep the online and frozen exports separate.

Only use corporate Pi runs when reporting release or transfer results for corporate platforms. The local browser fixture verifies the reporting and evidence pipeline.
