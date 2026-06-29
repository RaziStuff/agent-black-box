# Local Alpha Checklist

Use this before handing Agent Black Box to a first local alpha user.

## Alpha Scope

Included:

- Local SQLite store in `.abb/`.
- CLI capture, search, annotations, artifacts, compare export, fixtures, diff, handoff, bundle import/export.
- Browser dashboard for runs, fixtures, diff, artifacts, bundle import, compare ingest, handoff export, and handoff ingest.
- Machine-readable local API manifest and OpenAPI document for agents and non-Python clients.
- Portable `abb agent-kit` folder with API contracts, HTTP clients, env template, and offline smoke script.
- Local release artifacts from `scripts/build-release.py`: a pure-Python wheel, source tarball, design-partner zip, and checksum manifest.
- Dependency-free Python and Node HTTP client examples for non-SDK agents.
- OpenAI-compatible import-swap wrapper for local model-call capture.
- LangChain-style callback adapter for chain/model/tool capture.
- LangGraph-style node wrapper for graph state transition capture.
- Plain and MCP-style tool call recorder for schema/input/output capture.
- OpenAI-compatible proxy recorder for local experiments.
- Redaction for obvious secrets in payloads and text artifacts.

Not included:

- Signed desktop app.
- Cloud sync.
- Multi-user auth.
- Hosted telemetry.
- Package registry release.

## Preflight

```bash
python3 scripts/release-readiness.py
python3 scripts/build-release.py --no-verify
PYTHONPYCACHEPREFIX=.pycache python3 -m compileall src examples tests
PYTHONPYCACHEPREFIX=.pycache python3 -m unittest discover -s tests
scripts/smoke.sh
python3 scripts/http-client-smoke.py --required
scripts/alpha-demo.sh
scripts/dev-install.sh
. .venv/bin/activate
abb doctor
abb doctor --json
abb endpoints --json
abb endpoints --openapi
python3 examples/http_agent_client.py --help
abb agent-kit --json
abb agent-kit --zip --json
abb init --json
python3 examples/openai_wrapper_agent.py
python3 examples/langchain_callback_agent.py
python3 examples/langgraph_node_agent.py
python3 examples/tool_call_agent.py
```

Pass criteria:

- `python3 scripts/release-readiness.py` exits 0 and reports `SHIP` or `SHIP WITH KNOWN SKIPS`.
- `python3 scripts/release-readiness.py --strict` reports `SHIP` in environments where optional browser and Node checks are expected to pass.
- All commands exit with status 0.
- `python3 scripts/build-release.py --no-verify` writes `dist/agent_black_box-0.1.0-py3-none-any.whl`, `dist/agent-black-box-0.1.0.tar.gz`, `dist/agent-black-box-0.1.0-design-partner.zip`, and `dist/release-manifest.json` with SHA-256 checksums.
- `abb doctor` reports storage as ok and calls out daemon status as ok or warning.
- `abb doctor --json` returns `status`, `summary`, `checks`, `api`, and `next_steps`.
- `abb doctor --json` next steps mention API discovery, HTTP client examples, and support/troubleshooting.
- `abb endpoints --json` lists `/v1/endpoints`, `/v1/agent-kit`, compare export, compare evidence, handoff ingest, and bundle import routes.
- `abb endpoints --openapi` returns OpenAPI 3.1 with `/v1/openapi.json`, `/v1/agent-kit`, compare export, compare evidence, handoff ingest, bundle import, artifact, run, and proxy routes.
- `python3 examples/http_agent_client.py --help` shows the dependency-free HTTP client options without requiring the daemon.
- `examples/js-agent-client.mjs` uses built-in `fetch` and documents the same HTTP flow for Node.js 18 or newer.
- `abb agent-kit --json`, `abb agent-kit --zip`, `POST /v1/agent-kit`, and the dashboard Agent Kit action create a portable `.abb/agent-kit/` folder with `AGENT_BLACK_BOX.md`, endpoint contracts, Python and Node clients, `env.example`, `smoke.sh`, a machine-readable manifest, and an optional `agent-kit.zip` with SHA-256.
- `abb init --json` creates a markdown guide, env helper, and JSON init plan under the local store.
- `python3 examples/openai_wrapper_agent.py` records an `openai-wrapper` run without an API key.
- `python3 examples/langchain_callback_agent.py` records a `langchain-adapter` run without LangChain installed.
- `python3 examples/langgraph_node_agent.py` records a `langgraph-adapter` run without LangGraph installed.
- `python3 examples/tool_call_agent.py` records a `tool-adapter` run with schema, input, and output artifacts.
- The wrapper run shows token usage in `abb show RUN_ID`, the browser timeline, and handoff output.
- Run detail includes a compact summary with model/tool calls, graph nodes, warnings, errors, artifacts, usage, and first failure.
- `abb show RUN_ID`, the browser run detail, and handoff output include a `Debug Path` that starts with failures, warnings, annotations, or the first decision point.
- Browser debug-path cards expose direct artifact buttons and the artifact preview shows kind, media type, size, redaction state, and formatted JSON where possible.
- Browser run detail and handoff output group related artifacts by span so request/response/schema/input/output blobs are inspectable together.
- Browser run detail opens grouped artifacts in a focused span inspector, with timeline and group cards able to switch the selected span.
- The span inspector compares request/response, input/output, or schema/input artifacts side by side when those pairs exist.
- The span inspector can copy or download the selected compare pair as Markdown or JSON.
- `abb compare-export RUN_ID` exports the same `agent_black_box.compare_pair` payload for another agent without opening the browser.
- `abb compare-ingest PATH` creates a linked investigation run with `compare.packet`, `compare.briefing`, `compare.left`, and `compare.right` artifacts.
- `abb show COMPARE_INVESTIGATION_ID` prints a `Compare Investigation` block with source run/span, pair, and evidence artifact IDs.
- `abb compare-evidence COMPARE_INVESTIGATION_ID --left/--right/--packet/--briefing` opens evidence directly without copying artifact IDs.
- `/v1/runs/COMPARE_INVESTIGATION_ID/compare-evidence?part=left&format=text` returns the same unwrapped evidence for local agents and non-Python clients.
- Browser `Ingest Compare` accepts a local compare JSON path and opens the created investigation run.
- Compare-created investigation runs show a focused compare panel with source trace, packet, briefing, left body, and right body buttons.
- `python3 scripts/browser-smoke.py` verifies the rendered browser Agent Kit action, span inspector, artifact compare, compare export copy/fallback path, compare ingest path, evidence buttons, and source-trace jump through stable `data-testid` selectors when Playwright/browser dependencies are installed, and skips clearly otherwise.
- `python3 scripts/http-client-smoke.py --required` starts an in-process daemon, runs the Python HTTP client against it, verifies the recorded run, and runs the Node client when Node.js 18 or newer is available.
- Smoke creates a run, compare packet, compare investigation, handoff packet, handoff investigation, fixture, bundle, and remapped import.
- Alpha demo prints a reviewer summary with run IDs, export paths, and dashboard command.
- `abb support RUN_ID` creates a local support packet without full artifact payloads by default.
- Support packet `README.txt` includes the bug-report checklist and the packet includes `TROUBLESHOOTING.txt` and `KNOWN_LIMITATIONS.txt`.
- `docs/TROUBLESHOOTING.md` and `docs/KNOWN_LIMITATIONS.md` match the alpha scope.

## First User Script

Give the user [FIRST_USER_WORKFLOW.md](FIRST_USER_WORKFLOW.md) and ask them to complete:

- Send [DESIGN_PARTNER_HANDOFF.md](DESIGN_PARTNER_HANDOFF.md) as the operator-facing cover note.
- Score possible names in [DESIGN_PARTNER_INTAKE.csv](DESIGN_PARTNER_INTAKE.csv), then run `python3 scripts/rank-design-partners.py docs/DESIGN_PARTNER_INTAKE.csv --markdown .abb-send/design-partner-ranking.md`.
- Use [DESIGN_PARTNER_FIRST_SEND_PACKET.md](DESIGN_PARTNER_FIRST_SEND_PACKET.md) to choose the three initial partner segments, exact message, follow-up date, and decision rubric.
- Generate checksum-filled outbound drafts with `python3 scripts/prepare-design-partner-send.py --owner YOUR_NAME --json`.
- Use [DESIGN_PARTNER_OUTREACH.md](DESIGN_PARTNER_OUTREACH.md) for the first message.
- Track the send in [DESIGN_PARTNER_TRACKER.csv](DESIGN_PARTNER_TRACKER.csv).
- Ask them to fill [DESIGN_PARTNER_FEEDBACK_FORM.md](DESIGN_PARTNER_FEEDBACK_FORM.md) after the workflow.
- Summarize returned forms with `python3 scripts/feedback-summary.py FEEDBACK_DIR --markdown FEEDBACK_DIR/summary.md`.
- Install locally.
- Generate an init guide.
- Review the agent integration prompt and HTTP client examples.
- Run the OpenAI wrapper demo.
- Run the LangChain callback demo.
- Run the LangGraph node demo.
- Run the tool call demo.
- Record the demo agent.
- Open the browser UI.
- Export and ingest a compare pair.
- Export and read a handoff packet.
- Ingest the handoff packet into a new investigation.
- Export/import a portable bundle.
- Update [DESIGN_PARTNER_TRACKER.csv](DESIGN_PARTNER_TRACKER.csv) with status, blocker, support artifact paths, follow-up date, and decision.

## Acceptance Criteria

The alpha is usable when a first user can answer:

- What happened in this agent run?
- What should I inspect first, and why?
- Which artifact should I inspect first?
- Can I open that artifact directly from the debug path?
- Can I inspect all artifacts for a model/tool/node call as one group?
- Can I switch between model/tool/node calls in the span inspector without scanning the raw artifact list?
- Can I compare the request and response, or input and output, without opening separate artifact previews?
- Can I create a focused investigation from the compare pair?
- Can I see the source run/span and evidence artifact IDs from terminal output?
- Can I read compare evidence bodies from terminal output without copying artifact IDs?
- Can I open the compare packet, briefing, left/right bodies, and source trace from that investigation?
- What did the handoff packet tell the next agent?
- Can I create a follow-up investigation from the handoff?
- Can I move the full trace to another local store?
- Can I see source and investigation links in CLI and UI?
- Do I have a clear next setup path for CLI capture, SDK instrumentation, OpenAI import swap, or proxy routing?
- Can I capture a model-shaped call locally without a live API key?
- Can I capture chain/model/tool callbacks without changing framework behavior?
- Can I capture graph node state transitions without installing or changing LangGraph?
- Can I capture tool schemas, inputs, outputs, and MCP-shaped calls without a framework adapter?
- Can I see token usage without opening raw JSON artifacts?
- Can I use the summary to choose what to inspect first?
- Can I use the debug path to move from first failure or warning to the right artifact?
- Can another local agent discover the HTTP routes through `abb endpoints --json`, `abb endpoints --openapi`, `/v1/endpoints`, or `/v1/openapi.json`?
- Can another local agent copy the Python or Node HTTP example and record a run without the Python SDK?

## Privacy Gate

Confirm:

- The app does not require an account.
- The app does not make network calls except user-requested wrapper or proxy traffic.
- Data stays in the configured local store.
- `.handoff.json` does not embed artifact payloads.
- `.abb` bundles include artifact payloads and should be treated as shareable trace archives.
- Obvious API keys, bearer tokens, passwords, and private keys are redacted.

## Handoff For Support

If the first user hits a problem, ask them for one of:

- `abb support RUN_ID` output directory for a local support packet.
- `abb handoff RUN_ID` output for a compact debug briefing.
- `abb export RUN_ID --format handoff` output path if they can share the packet.
- `abb bundle export RUN_ID` only if they can share the full trace archive.
- The section of [TROUBLESHOOTING.md](TROUBLESHOOTING.md) they followed, if any.

## Stop Conditions

Do not hand this to more users if:

- Smoke fails.
- Redaction leaks a known secret in the workflow.
- Bundle import cannot recover a trace in a fresh local store.
- The browser UI cannot open the recorded run.
- Handoff ingest cannot create an investigation run.
