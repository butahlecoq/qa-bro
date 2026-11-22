# QA Bro

QA Bro is a local skill system for an existing Pi QA agent that drives a browser through opencode browse. It learns from UI test runs so the agent can reuse a verified hint or replay a recurring operation with fewer model calls. The agent chooses when to use a skill. The source scenario determines the actions and expected results.

## Project status

This repository evaluates the implementation on locally controlled fixtures and open-source applications with browse and an OpenCode session.

- [Baseline smoke test](https://github.com/butahlecoq/qa-bro/issues/1) verified the local requirements fixture with an empty catalog.
- [Held-out pilot](https://github.com/butahlecoq/qa-bro/issues/11) measured all four modes on local applications. The release gate failed on incomplete edit checks and acquisition cost.
- [Compiled backend evaluation](https://github.com/butahlecoq/qa-bro/issues/12) kept plain dispatch as the default after paired category-picker trials.

- [Design specification](SPEC.md)
- [Glossary](GLOSSARY.md)
- [Implementation issues](https://github.com/butahlecoq/qa-bro/issues)
- [Delivery milestones](https://github.com/butahlecoq/qa-bro/milestones)

The smoke test below runs locally. Each issue lists the prerequisites and evidence required for acceptance.

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

For an integration smoke test, run a scenario with an empty skill catalog. Record the installed browse schema, ordered step and tool events, attempt verdict, evidence references, and model usage. Record measured `model_calls`, `input_tokens`, `output_tokens` and `elapsed_ns` in the attempt's `baseline:usage` event. Run `python -m qabro.baseline_evidence DATABASE ATTEMPT_ID` to check source step order, installed tool identities and evidence references. The command prints an evidence summary without raw browser output. Inspect persisted evidence locally to verify that authentication material was redacted.

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

Plain browse dispatch remains the default. In a paired local Chromium trial, the single-call prototype preserved the ordered step outcomes and final form state on success and on a failed checkpoint. With a missing target after a successful fill, the form retained the first value on both backends. When the outer `execute` deadline expired during target resolution, the response omitted the structured evidence. Console markers now identify the completed prefix and the operation that was in flight. The timed-out trace remains incomplete, so the prototype stays disabled.

A local timing check with browse 0.1.5 ran six paired successful executions, alternating which backend ran first. The median was 402.1 ms for plain dispatch (394.6–427.5 ms) and 399.7 ms for `execute` (386.6–410.9 ms). Both modes completed all four operations and produced the expected final field value in all six trials. Timing covered browser dispatch and result parsing after tab preparation. The ranges overlap, and the check did not profile the runtime or measure the end-to-end Pi path. The result is inconclusive for performance and leaves plain dispatch in place.

Run the paired trial with the same relay and fixture as the smoke test. Set `QABRO_BROWSE` if the browse executable is outside `PATH`.

```sh
QABRO_FIXTURE_URL=http://127.0.0.1:18765/requirements.html \
  python -m unittest discover -s tests -p test_live_compiled_browser.py -v
```

For the pilot decision, export `recipe_fingerprint`, `validated_recipe_fingerprints`, a positive `minimum_saved_ns` selected before comparison, and `pairs` for success, checkpoint failure, and partial effect. Each pair has `case`, `plain`, and `compiled` entries. Each backend run records its recipe fingerprint, ordered events, verdict, elapsed nanoseconds, and whether the trace is complete. Record evidence, relative deadlines, and retry events in the trace. Run `python -m qabro.backend_evaluation backend-trials.json` on the pilot host.

## Report a pilot

Run the reporting command inside the environment that ran the pilot.

```sh
python -m qabro.pilot pilot.json > pilot-report.json
```

A frozen export has `kind: "frozen"`, `training_workflows`, `learning` costs keyed by mode, and `trials`. Each trial has a `case` with `id`, `workflow` and `expected`, along with the trial's `mode`, `setup`, `verdict`, `elapsed_ns`, `worker_tokens` and measured `usage`. Use the same setup identifier for matched trials across all four modes. The identifier should pin model, data, browser and budgets. Report explorer and validation costs in `learning`. An optional `release` entry supplies `minimum_tokens_saved` and per-case `evidence` containing mandatory and reported condition IDs and the observed number of duplicate effects.

To report skill break-even, add a `skills` object keyed by skill ID and revision. Each entry lists ordered `uses` with `case_id` and assisted `mode`, per-skill `learning` costs, and optional `maintenance_tokens`. Attribute a use only when the run actually reused the skill. Each use is paired with that case's baseline trial.

An online export has `kind: "online"` and ordered `attempts`. Each entry includes `attempt_id`, `trial`, `available_revisions` as skill ID and revision pairs, and `learning_since_previous`. Set `final_learning` for costs incurred after the final attempt. Keep the online and frozen exports separate.

For a second-platform comparison, include `platform` in the frozen export and a `transfer` object with the distinct target `platform`, its matched `trials` and its `learning` costs. The report shows the target results independently of the source platform's release criteria.

Scope release and transfer results to the applications exercised by the pilot.

## Sakai Vue smoke test

Run against the public demo with a dedicated browse tab, or pass `--url http://127.0.0.1:5173/pages/crud` for a local Sakai deployment. Supply a new private output directory outside the checkout. The smoke test uses generated product data and leaves the demo records alone.

```sh
python -m qabro.sakai_smoke /path/to/new-private-output --browse "$(command -v browse)"
```

Pass `--case SAKAI-01`, `SAKAI-02`, `SAKAI-03`, or `SAKAI-04` to run one scenario in a fresh tab. Use a new output directory for each attempt. The command records the installed browse schema, browser environment, and redacted MCP trace locally. It checks empty-name validation, product creation, exact-row lookup, saved fields, and reset. The four natural-language experiment inputs are in [scenarios/sakai](scenarios/sakai). The smoke test runs directly through browse MCP. The standalone Pi harness described below supports the Sakai worker and explorer experiment. The corporate Pi harness is separate.

Build local A/B reports from measured Sakai worker runs with `python -m qabro.sakai_comparison runs.json /path/to/new-private-report`. The manifest supplies `required_checks`, ordered `pairs` with `baseline` and `assisted` records, and `learning` with `training_tokens`, `extraction_tokens` and `validation_tokens`. Each worker record supplies `seed`, `setup`, `verdict`, matched `checks`, `tokens`, `model_calls` and `elapsed_ns`. Assisted records also supply `skill_revision` and `skill_applied`. Include the skill instructions in the assisted token count. The command writes `comparison.json` and `report.md`.

Call `train_sakai` with three distinct seeds, a worker callback, and a text-only explorer callback. The worker callback receives the requested seed and either an empty catalog or the candidate Markdown path. It starts a fresh Pi session and returns the journal path and attempt ID. The worker records a `sakai:worker` event containing `session_id`, `seed`, `browser_schema_sha256`, `scenario_sha256`, `skill_applied` and `skill_sha256`. Training uses an empty catalog. Validation records the digest of the candidate the worker actually applied. The activation check resolves the six required checkpoint artifacts from each attempt's local database.

Use `measure_sakai` to run SAKAI-02 pairs through the same Pi worker adapter. It accepts an active candidate directory, held-out measurement seeds, and the training and validation seeds. The callback starts a fresh worker for each attempt and returns its measured `SakaiRun`. The runner alternates A/B order and verifies the candidate's digest before and after every attempt.

To build a `SakaiRun` from the worker's database, call `measured_worker_run(database, attempt)`. Its `sakai:worker` event also supplies `model`, `target_url` and `budgets`, which are hashed with the scenario and browser schema to match paired setups. Record measured `tokens`, `model_calls`, `elapsed_ns`, `mcp_calls` and `browser_actions` in `sakai:usage`. A claimed PASS without stored artifacts for all six SAKAI-02 checks is reported as INCONCLUSIVE, with its measured costs intact.

### Minimal Sakai Pi harness

Use Pi with a configured model and the same browse relay as the smoke test. A single attempt runs SAKAI-02 with an empty catalog.

```sh
python -m qabro.sakai_pi /path/to/new-private-output \
  --pi /path/to/pi --browse "$(command -v browse)" --model provider/model
```

Add `--experiment` to train, extract in a separate text-only Pi session, validate on two fresh seeds, and run five held-out SAKAI-02 pairs. The command writes local worker journals, `comparison.json`, and `report.md` after a complete run. Use `--url http://127.0.0.1:5173/pages/crud` to use a local Sakai deployment.

Both modes use the same constrained creation tool. Inspect returns visible control labels and locators, and the host supplies only generated values. The model cannot browse other pages, change existing products, or repeat Save. Independent checks and readback run in the host. The assisted mode counts skill use when the worker reads the candidate before attempting to fill Price and completes the procedure. This measures the benefit of a skill for this restricted workflow.

### Run the Sakai experiment with a ChatGPT subscription

The Codex adapter requires an existing ChatGPT sign-in. It ignores user provider configuration and removes any OpenAI API key from the child process environment. Only the dedicated local Sakai MCP tool is enabled for the worker. Use a new private directory for each run.

```sh
python -m qabro.sakai_pi /path/to/new-private-output \
  --codex "$(command -v codex)" --model gpt-6-luna \
  --browse "$(command -v browse)" --experiment --pairs 1
```

One pair is a smoke experiment. Omit `--pairs 1` for five pairs. Codex reports aggregate input and output tokens for the session, including cached input in the input count. The experiment leaves the LLM call count blank because Codex CLI does not report the number of provider calls. Keep Codex and Pi results separate.

To run the same experiment through OpenCode with a ChatGPT subscription, use an active OpenAI OAuth sign-in and run the following command.

```sh
python -m qabro.sakai_pi /path/to/new-private-output \
  --opencode "$(command -v opencode)" --model openai/gpt-6-luna \
  --browse "$(command -v browse)" --experiment --pairs 1
```

The adapter rejects stored API-key credentials and removes API-key environment overrides. OpenCode reports completed model steps and token usage. Keep its results separate from Pi and Codex runs.

For a 30-pair batch, clone [Sakai Vue 5.0.0](https://github.com/primefaces/sakai-vue/releases/tag/5.0.0) with `git clone --branch 5.0.0 --recurse-submodules https://github.com/primefaces/sakai-vue.git`. In the clone, run `npm ci` and `npm run build`, then start `npm run preview -- --host 127.0.0.1 --port 4173 --strictPort`. Pass `--url http://127.0.0.1:4173/pages/crud --pairs 30` to the OpenCode command. Each pair uses a fresh seed for SAKAI-02. Results from that batch characterize this one scenario across synthetic inputs.

On a local deployment, add `--jobs 3` to run three independent pairs concurrently. Each pair still runs its two modes in order and gets its own browser tabs and model sessions. Compare batch wall times to measure throughput, and use the per-attempt timings to compare latency.

To measure a fresh pair with a previously validated skill, add `--candidate-from /path/to/previous-experiment --measurement-seed 5` and use a new output directory. The harness checks the browser schema, model, target URL, and candidate digest. It keeps reports for separate runs independent.

Validation asks the worker to consult the candidate. During measurement, the worker can skip the skill when live inspection gives it enough information. The report counts those passes separately from verified skill reuse. In both modes, the worker selects visible fields and the harness validates and executes any batch.

Use `--require-skill` on a fresh measurement seed to measure the cost of deliberately consulting the candidate. Keep these runs separate from optional-skill runs.

In the 30-pair local Sakai run with OpenCode and subscription-backed `openai/gpt-6-luna`, the baseline passed 30/30 and the skill-available arm passed 29/30. Live inspection already exposed the Price locator. The worker used the skill in 14 passing attempts.

| Metric | Baseline | Skill available |
| --- | ---: | ---: |
| Median elapsed time across 29 matched passes | 31.176 s | 37.083 s |
| Tokens across all 30 attempts per mode | 236,818 | 357,974 |
| Completed model steps | 194 | 269 |
| Browser MCP calls | 674 | 714 |

Acquisition cost 37,389 tokens. The assisted arm consumed 158,545 more tokens including acquisition, with no measured break-even. [30-pair results](https://github.com/butahlecoq/qa-bro/issues/16#issuecomment-7078670471)

The throughput benchmark ran the same 30 held-out SAKAI-02 inputs with one worker and with three independent workers. It alternated arm order over six blocks of five cases. Both arms used fresh OpenCode sessions, fresh tabs, and an empty skill catalog.

| Metric | One worker | Three workers |
| --- | ---: | ---: |
| Batch wall time, sum of six blocks | 978.128 s | 419.362 s |
| Cases passing all six checks | 30/30 | 30/30 |
| Median per-case latency | 31.855 s | 34.292 s |
| Tokens | 232,884 | 243,180 |
| Completed model steps | 192 | 199 |
| Browser MCP calls | 672 | 678 |
| Browser actions | 330 | 330 |

Concurrency increased aggregate throughput by 2.33× on this workload. Per-case median latency and aggregate token usage increased.




With Pi, the final successful creation tool response ends the worker session without a follow-up model turn when Pi can terminate that tool batch. The host still checks the saved record before issuing a verdict.

The Sakai learner stores a locator for one verified Price field interaction. Both modes can request `fill_many` by selecting two or three independent fields in an open form. The harness validates the selected targets, uses native batch fill when supported, and checks field values before permitting a separate Save. The worker chooses the actions from the live controls. Previous scenario-replay reports are historical and cannot be used to measure component learning.
