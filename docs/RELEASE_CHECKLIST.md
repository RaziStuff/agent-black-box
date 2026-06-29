# Agent Black Box Release Checklist

Use this checklist before cutting a local alpha release.

## Version

- Update `src/agent_black_box/__init__.py`.
- Confirm `pyproject.toml` reads the version dynamically from `agent_black_box.__version__`.
- Update `docs/ALPHA_RELEASE_NOTES.md` with the user-visible changes, known limitations, and first-user ask.
- Confirm `docs/KNOWN_LIMITATIONS.md` and `docs/TROUBLESHOOTING.md` match the release scope.
- Confirm `docs/DESIGN_PARTNER_INTAKE.md` and `.csv` capture candidate scoring before the first send.
- Confirm `docs/DESIGN_PARTNER_HANDOFF.md` points to the current first-user workflow, support artifacts, feedback questions, privacy notes, and stop conditions.
- Confirm `docs/DESIGN_PARTNER_FIRST_SEND_PACKET.md` has current partner segments, exact outbound copy, follow-up schedule, support artifact order, and decision rubrics.
- Confirm `scripts/rank-design-partners.py` ranks candidates from `docs/DESIGN_PARTNER_INTAKE.csv`.
- Confirm `scripts/prepare-design-partner-send.py` creates checksum-filled outbound drafts and tracker rows from `dist/release-manifest.json`.

## Local Verification

```bash
python3 scripts/release-readiness.py
python3 scripts/build-release.py
PYTHONPYCACHEPREFIX=.pycache python3 -m compileall src examples tests
PYTHONPYCACHEPREFIX=.pycache python3 -m unittest discover -s tests
scripts/smoke.sh
python3 scripts/http-client-smoke.py --required
scripts/alpha-demo.sh
```

The release-readiness harness writes `.abb-release/readiness-*.json` and
`.abb-release/readiness-*.txt`, and ends with one of three decisions:
`SHIP`, `SHIP WITH KNOWN SKIPS`, or `DO NOT SHIP`. Treat `DO NOT SHIP` as a hard
block. Treat `SHIP WITH KNOWN SKIPS` as acceptable only when the skips are
documented optional dependencies such as Playwright/browser engines or Node.js.

## First User Verification

- Walk through `docs/FIRST_USER_WORKFLOW.md`.
- Walk through `docs/DESIGN_PARTNER_INTAKE.md` as the candidate selection gate.
- Walk through `docs/DESIGN_PARTNER_FIRST_SEND_PACKET.md` as the first three-partner operating packet.
- Walk through `docs/DESIGN_PARTNER_HANDOFF.md` as the design-partner cover note.
- Confirm `docs/DESIGN_PARTNER_OUTREACH.md` includes a ready-to-send message for the current artifact.
- Confirm `docs/DESIGN_PARTNER_FEEDBACK_FORM.md` captures setup, workflow completion, privacy, and support artifacts.
- Confirm `docs/DESIGN_PARTNER_TRACKER.md` and `.csv` capture send status, artifact checksum, blockers, returned artifacts, follow-up date, and decision.
- Confirm `scripts/rank-design-partners.py docs/DESIGN_PARTNER_INTAKE.csv --markdown .abb-send/design-partner-ranking.md` ranks and selects candidates.
- Confirm `scripts/prepare-design-partner-send.py --owner YOUR_NAME --json` writes `.abb-send/design-partner-send-queue.md` and `.abb-send/design-partner-tracker-rows.csv`.
- Confirm `scripts/feedback-summary.py` can summarize returned feedback forms into JSON and Markdown.
- Confirm `docs/LOCAL_ALPHA_CHECKLIST.md` has no open stop condition.
- Confirm the first-user path records a run, exports compare and handoff packets, ingests investigations, and links source/investigation runs in CLI and UI.

## Install Verification

```bash
scripts/dev-install.sh
. .venv/bin/activate
abb --help
abb doctor
abb doctor --json
abb endpoints --json
abb endpoints --openapi
abb agent-kit --json
abb agent-kit --zip --json
python3 examples/http_agent_client.py --help
abb init
abb init --mode sdk --json
python3 examples/openai_wrapper_agent.py
python3 examples/langchain_callback_agent.py
python3 examples/langgraph_node_agent.py
python3 examples/tool_call_agent.py
abb record -- python3 examples/basic_agent.py
abb runs
```

Confirm `abb doctor --json` includes `doctor_version`, `status`, `summary`,
`checks`, `api`, `next_steps`, and does not print secret values. Use
`abb doctor --strict` only in checks where the daemon is expected to be running.
Confirm `next_steps` mention API discovery, HTTP client examples, and support/troubleshooting.

Confirm `abb endpoints --json` includes `/v1/endpoints`, `/v1/agent-kit`, compare export, compare
evidence, handoff ingest, and bundle import routes for agents and non-Python clients.
Confirm `abb endpoints --openapi` includes OpenAPI 3.1 paths for `/v1/openapi.json`, `/v1/agent-kit`,
run timeline, artifacts, compare export, compare evidence, handoff ingest, bundle
import, and the OpenAI-compatible proxy.
Confirm `examples/http_agent_client.py`, `examples/js-agent-client.mjs`, and
`docs/AGENT_INTEGRATION_PROMPT.md` describe the same HTTP record flow.
Confirm `abb agent-kit --json`, `abb agent-kit --zip`, `POST /v1/agent-kit`, and the dashboard Agent Kit action create `AGENT_BLACK_BOX.md`, `endpoints.json`,
`openapi.json`, `python_client.py`, `node_client.mjs`, `env.example`, `smoke.sh`,
`agent-kit.json`, and optional `agent-kit.zip` with SHA-256; run the generated
`smoke.sh` before sharing the folder or zip.
Confirm `python3 scripts/http-client-smoke.py --required` records and verifies a
run through `examples/http_agent_client.py`; use `--node-required` in environments
where Node.js 18 or newer is expected.
Confirm support packet `README.txt` includes the bug-report checklist and points to troubleshooting and known limitations.

Confirm `abb init` writes a markdown guide, env helper, and JSON init plan under
`.abb/init/`, and that `--mode cli`, `--mode sdk`, and `--mode proxy` each include
the expected setup path without editing project source code.

## OpenAI Wrapper Verification

Confirm unit tests cover `from agent_black_box.openai import OpenAI` with a fake
transport, successful `chat.completions.create(...)`, `responses.create(...)`
missing-credential failure, local request/response artifacts, and `abb_run_id`
on the returned response object.

Confirm `python3 examples/openai_wrapper_agent.py` records an `openai-wrapper`
run without `OPENAI_API_KEY` or outbound network access.
Confirm `python3 examples/langchain_callback_agent.py` records a `langchain-adapter`
run without LangChain installed, with chain, model, and tool spans.
Confirm `python3 examples/langgraph_node_agent.py` records a `langgraph-adapter`
run without LangGraph installed, with `langgraph.node` spans and node input/output artifacts.
Confirm `python3 examples/tool_call_agent.py` records a `tool-adapter` run with
`tool.call` spans, schema artifacts, input artifacts, output artifacts, and an MCP-shaped call.
Confirm the wrapper run shows token usage in `abb show RUN_ID`, and that its
handoff briefing includes the same usage summary.
Confirm `abb show RUN_ID`, the browser run detail, and handoff briefing include
a compact run summary with model/tool calls, graph nodes, warnings, errors, artifacts, usage,
and first failure when present.
Confirm the same surfaces include a `Debug Path` with reason, next action, and
refs for the first failures, warnings, annotations, or decision points.
Confirm browser debug-path artifact buttons open the referenced artifact preview
without using the side artifact list, and JSON artifacts are readable.
Confirm browser artifact groups and handoff artifact groups organize request,
response, schema, input, and output blobs by span.
Confirm the browser `Span Inspector` opens the first artifact group by default
and switches when a timeline span or artifact-group card is selected.
Confirm the span inspector renders side-by-side artifact comparisons for
request/response, input/output, and schema/input pairs when present.
Run `ABB_BROWSER_SMOKE_REQUIRED=1 python3 scripts/browser-smoke.py` in release
verification environments that have Playwright and browser engines installed.
Confirm dashboard controls used by the browser smoke retain stable `data-testid`
selectors for run detail, span inspector, artifact compare, compare controls,
Agent Kit controls, compare copy/download controls, compare ingest controls,
compare investigation evidence buttons, copy result/fallback surface, and compare panes.

## Daemon And UI Verification

```bash
abb start
```

Open `http://127.0.0.1:43188` and verify:

- Runs load.
- Search and filters work.
- Timeline opens.
- Annotations can be added.
- Artifacts preview.
- Debug-path artifact buttons open previews for request/response/schema/input/output refs.
- Artifact groups show related blobs for each model/tool/node span.
- The span inspector switches between model/tool/node spans and opens their artifacts.
- The span inspector compares paired artifacts side by side.
- `GET /v1/endpoints` returns the same manifest as `abb endpoints --json`.
- `GET /v1/openapi.json` returns the same OpenAPI 3.1 document as `abb endpoints --openapi`.
- `python3 examples/http_agent_client.py` records a run over HTTP when the daemon is running.
- `node examples/js-agent-client.mjs` records a run over HTTP with Node.js 18 or newer when the daemon is running.
- `abb compare-export RUN_ID --format json` exports an `agent_black_box.compare_pair` payload for request/response or input/output pairs.
- `abb compare-ingest PATH` creates a linked compare investigation with packet, briefing, and left/right evidence artifacts.
- Fixture creation works.
- Fixture replay view opens.
- Diff view compares two runs.
- Handoff export writes a `.handoff.json` packet.

## Handoff Verification

```bash
abb export RUN_ID --format handoff
COMPARE_PATH="$(abb compare-export RUN_ID --format json)"
COMPARE_INVESTIGATION_ID="$(abb compare-ingest "$COMPARE_PATH" --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["run"]["run_id"])')"
abb compare-evidence "$COMPARE_INVESTIGATION_ID" --left
abb handoff RUN_ID
abb handoff --file .abb/exports/RUN_ID.handoff.json
abb handoff --ingest .abb/exports/RUN_ID.handoff.json
abb support RUN_ID
```

Confirm:

- The packet includes `handoff_version`, `run`, `summary`, `counts`, `debug_path`, `artifact_groups`, `attention`, `timeline`, `artifacts`, `annotations`, `fixtures`, and `suggested_next_steps`.
- Timeline entries include IDs and refs for linked spans, events, and artifacts.
- The packet is compact JSON and does not embed artifact payloads.
- The briefing calls out debug path items, attention items, artifacts, fixtures, and next steps without requiring raw JSON inspection.
- Compare ingest creates a new running investigation run with `compare.packet`, `compare.briefing`, `compare.left`, and `compare.right` artifacts.
- `abb show` for a compare-created investigation prints source run/span, pair, and evidence artifact IDs.
- `abb compare-evidence` prints or writes packet, briefing, left body, and right body evidence directly from the compare investigation.
- `GET /v1/runs/COMPARE_INVESTIGATION_ID/compare-evidence?part=left&format=text` returns the same unwrapped evidence over the daemon API.
- `abb endpoints --json`, `abb endpoints --openapi`, `GET /v1/endpoints`, and `GET /v1/openapi.json` document the compare and handoff routes another local agent needs.
- Handoff ingest creates a new running investigation run with `handoff.packet` and `handoff.briefing` artifacts.
- Browser `Ingest Compare` accepts a local compare JSON path and opens the created investigation run.
- Browser compare investigations show source trace, packet, briefing, left body, and right body buttons.
- Browser `Ingest Handoff` accepts a local `.handoff.json` path and opens the created investigation run.
- Source runs show linked investigations, and investigation runs link back to their source trace in CLI and UI.
- `abb support RUN_ID` creates a support directory with briefing, handoff JSON, timeline metadata, doctor report, and offline troubleshooting/known-limitations notes.
- The support packet `doctor.json` uses the same schema as `abb doctor --json`.
- `abb support RUN_ID --include-bundle` adds the full `.abb` trace archive.

## Bundle Verification

```bash
abb bundle export RUN_ID
abb --data-dir /tmp/abb-import bundle import .abb/exports/RUN_ID.abb
abb --data-dir /tmp/abb-import bundle import .abb/exports/RUN_ID.abb --on-conflict skip
abb --data-dir /tmp/abb-import bundle import .abb/exports/RUN_ID.abb --on-conflict remap
abb --data-dir /tmp/abb-import show RUN_ID
```

Confirm:

- The imported run opens.
- Timeline counts match.
- Annotations are present.
- Artifacts can be read.
- Default import rejects a bundle when the run ID already exists in the target store.
- `--on-conflict skip` exits successfully without writing a duplicate run.
- `--on-conflict remap` imports a new run and keeps spans, events, artifacts, annotations, and fixtures linked to the remapped IDs.
- Browser `Import ABB` accepts a local bundle path and supports fail, skip, and remap conflict modes.

## Privacy And Redaction

- Confirm obvious API keys, bearer tokens, passwords, and private keys are redacted.
- Confirm exports do not include unredacted known secrets.
- Confirm `.abb` bundles include only redacted trace data and local artifact payloads.
- Confirm OpenAI wrapper request/response artifacts are stored locally.
- Confirm OpenAI wrapper/proxy usage stats are stored locally when responses include usage data.
- Confirm OpenAI proxy request/response artifacts are stored locally.
- Confirm no telemetry or network calls are made by the app itself except user-requested proxy traffic.

## Packaging Notes

- The MVP has no runtime dependencies outside the Python standard library.
- `scripts/dev-install.sh` installs editable mode into `.venv`.
- `scripts/build-release.py` creates `dist/agent_black_box-<version>-py3-none-any.whl`, `dist/agent-black-box-<version>.tar.gz`, `dist/agent-black-box-<version>-design-partner.zip`, and `dist/release-manifest.json` with SHA-256 checksums.
- Run `python3 scripts/build-release.py` before sharing an alpha wheel; it installs the wheel in an isolated virtualenv and checks `abb --help`.
- Share `dist/agent-black-box-<version>-design-partner.zip` when the reviewer should not need the source checkout.
- Use `python3 scripts/build-release.py --no-verify` only for fast readiness gates where a full venv install would be redundant.
- `scripts/smoke.sh` uses an isolated `.abb-smoke` store.
- Do not publish to a package registry until license, project URLs, and release ownership are finalized.
