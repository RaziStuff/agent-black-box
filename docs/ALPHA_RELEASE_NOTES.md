# Agent Black Box 0.1.0 Local Alpha Notes

Agent Black Box is a local-first flight recorder for AI agents. This alpha is for
one friendly user or a very small design-partner loop, not a public package
release.

## What This Alpha Can Do

- Record a local command as an agent run.
- Store runs, spans, events, annotations, and artifacts in a local SQLite-backed `.abb/` store.
- Inspect timelines from the CLI and browser dashboard.
- See a compact run summary with model calls, tool calls, graph nodes, token totals, warnings, errors, artifacts, and first failure.
- Follow a `Debug Path` in CLI, browser, and handoff output to inspect failures, warnings, annotations, and artifact refs first.
- Open referenced artifacts directly from browser debug-path cards with metadata and formatted JSON previews.
- Inspect related artifacts grouped by span for each model call, tool call, or graph node.
- Compare request/response, input/output, or schema/input artifacts side by side in the browser span inspector.
- Add debugging annotations.
- Preview text and JSON artifacts.
- Create replay fixtures and compare runs.
- Export compact `.handoff.json` packets for another agent.
- Print agent-ready handoff briefings from live runs or saved packets.
- Ingest a handoff packet into a new running investigation run.
- Link source runs and handoff-created investigations in CLI and UI.
- Create local support packets with briefing, handoff JSON, timeline metadata, doctor report, and optional full bundle.
- Run `abb doctor --json` for a machine-readable local readiness report that agents, scripts, and support packets can consume.
- Run `abb endpoints --json`, `abb endpoints --openapi`, `/v1/endpoints`, or `/v1/openapi.json` to discover the local HTTP API for agents and non-Python clients.
- Use dependency-free Python and Node HTTP client examples to record a run without the Python SDK.
- Run `abb agent-kit --zip`, use dashboard Agent Kit, or call `POST /v1/agent-kit` to generate a portable folder or zip with API contracts, HTTP clients, env template, checksum, and offline kit smoke check for another local agent.
- Run `python3 scripts/build-release.py` to create a local wheel, source tarball, design-partner zip, and checksum manifest for design-partner installation without publishing to a registry.
- Use `docs/DESIGN_PARTNER_INTAKE.md` and `python3 scripts/rank-design-partners.py` to score and rank candidate names before the first send.
- Use `docs/DESIGN_PARTNER_FIRST_SEND_PACKET.md` to pick the first three design partners, send exact messages, schedule follow-ups, and apply the cohort decision rubric.
- Run `python3 scripts/prepare-design-partner-send.py` to generate checksum-filled outbound drafts and tracker rows from the release manifest.
- Run `python3 scripts/feedback-summary.py` on returned feedback forms to turn design-partner notes into JSON and Markdown triage.
- Track each send in `docs/DESIGN_PARTNER_TRACKER.csv` so install status, blockers, support artifacts, follow-up date, and alpha decision are explicit.
- Run `abb init` to generate a local setup guide for CLI capture, Python SDK instrumentation, OpenAI import-swap capture, and OpenAI-compatible proxy routing.
- Export/import portable `.abb` bundles, including duplicate `skip` and `remap` modes.
- Record OpenAI-compatible model calls through `from agent_black_box.openai import OpenAI` without starting the daemon.
- Record LangChain-style chain/model/tool callbacks through `AgentBlackBoxCallbackHandler` without requiring LangChain at install time.
- Record LangGraph-style node state transitions through `LangGraphRecorder.wrap_node` without requiring LangGraph at install time.
- Record plain and MCP-style tool calls through `ToolCallRecorder` with schemas, inputs, and outputs.
- Record OpenAI-compatible proxy requests and responses when the user explicitly routes traffic through the local proxy.
- Surface model token usage in `abb show`, the browser timeline, and handoff briefings when OpenAI-compatible responses include usage data.

## What Is Intentionally Not Included

See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) for the full current list.

- Signed desktop app.
- Cloud sync.
- Multi-user auth.
- Hosted telemetry.
- Package registry distribution.
- Long-running production observability backend.
- Rich visual replay beyond the current terminal-style fixture view.
- Full streaming proxy capture; streaming responses are buffered in this alpha.
- Full parity with the official OpenAI Python SDK; the wrapper currently targets `chat.completions.create(...)` and `responses.create(...)`.

## How To Try It

```bash
scripts/dev-install.sh
python3 scripts/build-release.py --no-verify
. .venv/bin/activate
abb doctor
abb doctor --json
abb endpoints --json
abb endpoints --openapi
abb agent-kit --json
abb agent-kit --zip --json
python3 examples/http_agent_client.py --help
abb init
python3 examples/openai_wrapper_agent.py
python3 examples/langchain_callback_agent.py
python3 examples/langgraph_node_agent.py
python3 examples/tool_call_agent.py
abb record --name alpha-demo -- python3 examples/basic_agent.py
abb runs
```

Or run the full reviewer demo:

```bash
scripts/alpha-demo.sh
```

Then follow [FIRST_USER_WORKFLOW.md](FIRST_USER_WORKFLOW.md) for the full path:

1. Record a run.
2. Inspect and annotate it.
3. Create a fixture and diff.
4. Export a handoff packet.
5. Ingest the handoff into a new investigation.
6. Open the browser dashboard.
7. Export/import a portable bundle.

For a design-partner handoff, use
[DESIGN_PARTNER_INTAKE.md](DESIGN_PARTNER_INTAKE.md),
[DESIGN_PARTNER_FIRST_SEND_PACKET.md](DESIGN_PARTNER_FIRST_SEND_PACKET.md),
[DESIGN_PARTNER_HANDOFF.md](DESIGN_PARTNER_HANDOFF.md),
[DESIGN_PARTNER_OUTREACH.md](DESIGN_PARTNER_OUTREACH.md), and
[DESIGN_PARTNER_FEEDBACK_FORM.md](DESIGN_PARTNER_FEEDBACK_FORM.md), then track
the loop in [DESIGN_PARTNER_TRACKER.md](DESIGN_PARTNER_TRACKER.md).

## First-User Ask

Ask the first user to complete the workflow and answer:

- Could you record your first run without help?
- Did the init guide make the available setup paths clear?
- Could you run the OpenAI wrapper demo without an API key?
- Could you run the LangChain callback demo without installing LangChain?
- Could you run the LangGraph node demo without installing LangGraph?
- Could you run the tool call demo and see schema/input/output artifacts?
- Could you see model usage counts in the wrapper run timeline?
- Did `abb show` and the browser timeline make the run understandable?
- Did the run summary help you decide where to inspect first?
- Did the debug path point you to the right failure, warning, or artifact quickly?
- Could you open the referenced artifact directly from the debug path?
- Could you inspect the grouped request/response/schema/input/output artifacts for one call?
- Could you switch the browser span inspector between calls from the timeline or artifact groups?
- Could you compare paired artifacts inside the span inspector without jumping to the raw artifact list?
- Which artifact did you inspect first, and why?
- Did the handoff briefing give enough context for another agent to continue?
- Did handoff ingest make the follow-up investigation obvious?
- Could you tell which investigation came from which source run?
- Could another local agent discover the routes it needs through `abb endpoints --json`, `abb endpoints --openapi`, `/v1/endpoints`, or `/v1/openapi.json`?
- Could another local agent use the Python or Node HTTP example without adopting the SDK?
- Could another local agent use `abb agent-kit` without reading this repository first?
- Did the local-first/privacy boundary feel clear?

## Expected Support Artifacts

If something fails, ask for the smallest useful artifact:

- `abb handoff RUN_ID` output for a compact briefing.
- `.abb/exports/RUN_ID.handoff.json` if they can share the handoff packet.
- `.abb/exports/RUN_ID.abb` only if they can share the full trace archive with artifact payloads.
- `abb support RUN_ID` output directory if they want one local folder with the briefing, packet, timeline metadata, and doctor report.
- The output of `abb doctor` or `abb doctor --json`.
- The command they ran and the exact error text.

Use [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common local setup, daemon,
Node, browser smoke, auth token, compare, handoff, and bundle import issues.

## Privacy Notes

- Data stays local by default in `.abb/`.
- Set `ABB_HOME` or use `--data-dir` to choose another local store.
- `.handoff.json` packets summarize traces and do not embed artifact payloads.
- `abb support RUN_ID` does not include artifact payloads unless `--include-bundle` is used.
- `.abb` bundles include local artifact payloads and should be handled as full trace archives.
- The app itself does not call the network except for user-requested OpenAI-compatible proxy traffic.
- Redaction covers obvious API keys, bearer tokens, passwords, and private keys, but users should still inspect artifacts before sharing.

## Verification Before Sharing

Run:

```bash
python3 scripts/release-readiness.py
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
abb init --json
python3 examples/openai_wrapper_agent.py
python3 examples/langchain_callback_agent.py
python3 examples/langgraph_node_agent.py
python3 examples/tool_call_agent.py
```

Use [LOCAL_ALPHA_CHECKLIST.md](LOCAL_ALPHA_CHECKLIST.md) as the final gate.

## Known Limitations

See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

## Release Decision

Ship this alpha only when:

- Smoke passes.
- The first-user workflow can be completed end to end.
- A handoff packet can be exported, read, ingested, and linked back to the source run.
- A portable `.abb` bundle can be imported into a fresh local store.
- No known secret appears unredacted in the demo artifacts.
