# Agent Black Box

Agent Black Box is a local-first flight recorder for AI agents. This repository now contains the first runnable MVP spine: local SQLite storage, a localhost daemon, a tiny browser viewer, a CLI, a Python SDK, redaction, export, and a demo agent.

## Quickstart

For the end-to-end local alpha path, use `docs/FIRST_USER_WORKFLOW.md`.
For a one-command reviewer demo, run `scripts/alpha-demo.sh`.
For design-partner sharing, use `docs/DESIGN_PARTNER_INTAKE.md`,
`docs/DESIGN_PARTNER_FIRST_SEND_PACKET.md`, `docs/DESIGN_PARTNER_HANDOFF.md`,
`docs/DESIGN_PARTNER_OUTREACH.md`, `docs/DESIGN_PARTNER_FEEDBACK_FORM.md`, and
`docs/DESIGN_PARTNER_TRACKER.md`.
For known limits and common fixes, see `docs/KNOWN_LIMITATIONS.md` and
`docs/TROUBLESHOOTING.md`.

Install the local development CLI:

```bash
scripts/dev-install.sh
. .venv/bin/activate
```

Run the doctor:

```bash
abb doctor
abb doctor --json
abb endpoints --json
abb endpoints --openapi
```

`abb doctor` checks Python, local storage, CLI entrypoint, daemon reachability,
and OpenAI-compatible proxy readiness. The JSON form is intended for agents,
scripts, and support packets. `abb endpoints --json` prints the local daemon API
manifest, `abb endpoints --openapi` prints the OpenAPI 3.1 document, and the
daemon serves the same contracts at `/v1/endpoints` and `/v1/openapi.json`; see
`docs/API_REFERENCE.md` for the route reference. Use `abb doctor --strict` when
warnings, such as the dashboard daemon not running, should fail the command.
When a workflow fails, start with `docs/TROUBLESHOOTING.md`.

Create a local setup guide for an agent project:

```bash
abb init
abb init --mode sdk
abb init --mode proxy --json
```

`abb init` writes a markdown guide, shell env helper, and machine-readable init
plan under `.abb/init/`. Use modes `cli`, `sdk`, `proxy`, or `all` depending on
how much instrumentation the agent project can accept. SDK mode includes snippets
for direct spans, OpenAI import swaps, LangChain callbacks, and LangGraph-style
node wrappers, plus plain and MCP-style tool call capture.

Create a portable onboarding kit for another local agent:

```bash
abb agent-kit
abb agent-kit --json
abb agent-kit --zip
abb agent-kit --force
```

`abb agent-kit` writes `.abb/agent-kit/` with `AGENT_BLACK_BOX.md`,
`endpoints.json`, `openapi.json`, dependency-free Python and Node HTTP clients,
`env.example`, `smoke.sh`, and `agent-kit.json`. The daemon exposes the same
generator at `POST /v1/agent-kit`, and the dashboard has an Agent Kit action.
Use `--zip` to create `agent-kit.zip` with a reported SHA-256 checksum, and
`--force` to refresh an existing kit. The kit lets an agent inspect the API
contract, validate the pack offline, then record a run after `abb start` is
running.

Use the HTTP API from another local agent or runtime:

```bash
abb start
python3 examples/http_agent_client.py
node examples/js-agent-client.mjs
```

Both examples discover `/v1/openapi.json`, create a run/span/artifact/event over
HTTP, end the run, and print the run ID. `docs/AGENT_INTEGRATION_PROMPT.md`
contains a copy-paste prompt for agents that should use the local API directly.

Record the demo agent:

```bash
abb record -- python3 examples/basic_agent.py
```

List runs:

```bash
abb runs
```

Search runs:

```bash
abb search refund
```

Show a timeline:

```bash
abb show RUN_ID
```

Run detail views include a compact summary with model calls, tool calls, graph
nodes, warnings, errors, artifacts, token totals, and first failure when present.
They also include a `Debug Path` that points to the first failures, warnings,
annotations, and referenced artifacts worth inspecting before scanning the whole
timeline.
Debug-path cards in the browser include direct artifact buttons for request,
response, schema, input, and output blobs, and the preview panel formats JSON
artifacts with metadata.
Related artifacts are also grouped by span, so a model call, tool call, or graph
node can be inspected as one request/response/schema/input/output unit.
The browser run detail opens the first group in a focused `Span Inspector`, and
timeline or artifact-group cards can switch the inspector to another span.
When a span has a natural pair, the inspector compares request/response,
input/output, or schema/input artifacts side by side. The selected pair can be
copied or downloaded as Markdown for human handoff notes, or JSON for another
agent to ingest.

Annotate a run:

```bash
abb annotate RUN_ID "First bad model decision happens before tool selection"
abb annotations RUN_ID
```

Export a run:

```bash
abb export RUN_ID --format markdown
abb export RUN_ID --format jsonl
abb export RUN_ID --format handoff
```

The `handoff` export writes a compact JSON packet for another agent: run identity,
provenance, summary, counts, debug path, artifact groups, attention items,
timeline references, artifacts, annotations, fixtures, and suggested next steps.

Export just one comparable artifact pair for an agent:

```bash
abb compare-export RUN_ID
abb compare-export RUN_ID --span SPAN_ID --pair request-response --format json
abb compare-export RUN_ID --pair input-output --format markdown --output -
abb compare-ingest .abb/exports/RUN_ID.SPAN_ID.request-response.compare.json
abb compare-evidence COMPARE_INVESTIGATION_ID --left
abb compare-evidence COMPARE_INVESTIGATION_ID --packet --output compare.packet.json
```

`compare-export` writes an `agent_black_box.compare_pair` payload with run ID,
span metadata, pair type, both artifact records, and both artifact bodies.
`compare-ingest` creates a new running investigation with the compare packet,
a briefing, and left/right evidence body artifacts attached. The daemon exposes
the same export data at `/v1/runs/RUN_ID/compare-export?pair=request-response&format=json`
and accepts compare packets through `POST /v1/compare/ingest`.
`abb show` for a compare-created investigation prints a focused compare block
with source run/span metadata and the packet, briefing, left-body, and right-body
artifact IDs.
`compare-evidence` reads those evidence artifacts directly; left/right evidence
is unwrapped to the original body text by default, with `--raw` available when
the wrapper metadata is needed. The daemon exposes the same evidence at
`/v1/runs/COMPARE_INVESTIGATION_ID/compare-evidence?part=left&format=text`
or as JSON at `/v1/runs/COMPARE_INVESTIGATION_ID/compare-evidence?part=left`.

Print an agent-ready handoff briefing:

```bash
abb handoff RUN_ID
abb handoff --file .abb/exports/RUN_ID.handoff.json
abb handoff --ingest .abb/exports/RUN_ID.handoff.json
```

Ingesting a handoff creates a new running investigation run with the packet and rendered
briefing attached as artifacts.
The browser UI exposes the same action through `Ingest Handoff` in the Runs sidebar.
Source runs and handoff/compare-created investigation runs are linked in `abb show`
and the run detail UI.

Create a local support packet:

```bash
abb support RUN_ID
abb support RUN_ID --include-bundle
```

Support packets include a briefing, handoff JSON, timeline metadata, the same
structured doctor report returned by `abb doctor --json`, offline troubleshooting
and known-limitations notes, and an optional full `.abb` bundle when
`--include-bundle` is used.

Export and import a portable bundle:

```bash
abb bundle export RUN_ID
abb --data-dir /tmp/abb-import bundle import .abb/exports/RUN_ID.abb
abb --data-dir /tmp/abb-import bundle import .abb/exports/RUN_ID.abb --on-conflict skip
abb --data-dir /tmp/abb-import bundle import .abb/exports/RUN_ID.abb --on-conflict remap
```

Bundle imports fail by default when the target store already has the same run ID.
Use `--on-conflict skip` to make repeated imports idempotent, or `--on-conflict remap`
to import the bundle as a new independent run with all internal trace references rewritten.
Imported and remapped runs are labeled in the browser UI and CLI detail output.
The browser UI also has an `Import ABB` control in the Runs sidebar for importing a local
`.abb` bundle path with the same conflict modes.

Delete a local run and its default export files:

```bash
abb delete RUN_ID --yes
abb delete RUN_ID --yes --keep-exports
abb delete RUN_ID --yes --json
```

Delete removes the run, spans, events, annotations, replay fixtures, artifact
rows, unreferenced local object files, and default files in `.abb/exports/` for
that run. Linked handoff or compare investigation runs are kept and reported.
The browser run detail has the same action, and the daemon exposes it as
`DELETE /v1/runs/RUN_ID`.

Create and replay a fixture:

```bash
abb fixture create RUN_ID --name "refund regression"
abb fixture list
abb replay FIXTURE_ID
```

Compare two runs:

```bash
abb diff RUN_ID_A RUN_ID_B
```

Inspect artifacts:

```bash
abb artifacts RUN_ID
abb artifact ARTIFACT_ID
```

Start the local daemon and browser UI:

```bash
abb start
```

Then open:

```text
http://127.0.0.1:43188
```

The local UI has three main views:

- `Runs`: search/filter runs, inspect timelines, add annotations, preview artifacts, import/export bundles, ingest compare and handoff packets, export agent handoff packets, create fixtures, and delete local runs.
- `Fixtures`: replay a captured run as a terminal-style sequence.
- `Diff`: compare two runs by counts, span/event types, and first divergence.

## Current Shape

- `src/agent_black_box/storage.py`: SQLite and local object storage.
- `src/agent_black_box/api_manifest.py`: machine-readable local daemon API manifest.
- `src/agent_black_box/daemon.py`: localhost API and minimal browser UI.
- `src/agent_black_box/cli.py`: `abb` commands.
- `src/agent_black_box/sdk.py`: Python instrumentation helpers.
- `src/agent_black_box/handoff.py`: handoff briefing formatter.
- `src/agent_black_box/diff.py`: run comparison helpers.
- `src/agent_black_box/replay.py`: visual fixture replay helpers.
- `src/agent_black_box/openai.py`: dependency-free OpenAI-compatible client wrapper.
- `src/agent_black_box/proxy.py`: OpenAI-compatible proxy recorder.
- `src/agent_black_box/adapters/langchain.py`: dependency-free LangChain-style callback handler.
- `src/agent_black_box/adapters/langgraph.py`: dependency-free LangGraph-style node recorder.
- `src/agent_black_box/adapters/tools.py`: dependency-free plain and MCP-style tool call recorder.
- `examples/http_agent_client.py`: dependency-free Python client for the local HTTP API.
- `examples/js-agent-client.mjs`: dependency-free Node client for the local HTTP API.
- `docs/AGENT_INTEGRATION_PROMPT.md`: copy-paste prompt for agents using the local API.
- `examples/basic_agent.py`: instrumented demo agent.
- `examples/openai_wrapper_agent.py`: no-network OpenAI wrapper demo.
- `examples/langchain_callback_agent.py`: no-dependency LangChain callback demo.
- `examples/langgraph_node_agent.py`: no-dependency LangGraph-style node demo.
- `examples/tool_call_agent.py`: no-dependency tool call and MCP-shaped call demo.
- `tests/test_storage.py`: storage and redaction smoke tests.
- `AGENT_BLACK_BOX_BUILD_PLAN.md`: detailed build, ship, and adoption plan.

By default, data is stored in `.abb/` in the current working directory. Set `ABB_HOME` or pass `--data-dir` to choose another local store.

You can still run the repository entrypoint directly while hacking:

```bash
python3 abb.py --help
```

## Development

Run the local smoke suite:

```bash
scripts/smoke.sh
```

The smoke suite uses `.abb-smoke/` as an isolated local store and exercises compile checks, unit tests, optional rendered browser UI smoke, live HTTP client smoke, agent-kit creation, init guide creation, OpenAI wrapper demo capture, compare-pair export and ingest, LangChain callback demo capture, LangGraph node demo capture, tool call demo capture, demo recording, annotations, search, fixture creation, replay, diff, handoff export, support packet creation, portable bundle import/export with conflict handling, and artifact listing.

Run the alpha release-readiness harness:

```bash
python3 scripts/release-readiness.py
python3 scripts/release-readiness.py --strict
python3 scripts/build-release.py
```

The readiness harness runs compile checks, unit tests, shell syntax checks, and
local release artifact checks before `scripts/smoke.sh`, then writes timestamped
JSON and text reports under `.abb-release/`. Its final status is `SHIP`,
`SHIP WITH KNOWN SKIPS`, or `DO NOT SHIP`; use `--strict` when optional skips
such as missing Playwright or Node should fail the release gate.

`scripts/build-release.py` creates `dist/agent_black_box-<version>-py3-none-any.whl`,
`dist/agent-black-box-<version>.tar.gz`,
`dist/agent-black-box-<version>-design-partner.zip`, and
`dist/release-manifest.json` with SHA-256 checksums. The design-partner zip
bundles the wheel, source archive, install script, docs, and examples for a
no-registry handoff. By default the builder verifies the wheel in an isolated
virtualenv; use `--no-verify` for a fast metadata-only packaging gate.

Summarize returned design-partner feedback forms:

```bash
python3 scripts/rank-design-partners.py docs/DESIGN_PARTNER_INTAKE.csv --markdown .abb-send/design-partner-ranking.md
python3 scripts/prepare-design-partner-send.py --owner YOUR_NAME --json
python3 scripts/feedback-summary.py .abb-feedback --output .abb-feedback/summary.json --markdown .abb-feedback/summary.md
```

The ranking script scores candidate names before the first send and writes a
local selection report under `.abb-send/`.
The send-prep script reads `dist/release-manifest.json` and writes
checksum-filled outbound drafts plus tracker rows under `.abb-send/`.
The summary extracts setup status, workflow completion, scores, confusion notes,
privacy concerns, support artifact paths, and suggested next actions.

The HTTP client smoke is available directly:

```bash
python3 scripts/http-client-smoke.py
python3 scripts/http-client-smoke.py --required
```

It starts an in-process localhost daemon on an ephemeral port, runs
`examples/http_agent_client.py` against it with bearer auth, verifies the recorded
run in the local store, and runs `examples/js-agent-client.mjs` too when Node.js
18 or newer is available.

The rendered browser smoke is available directly:

```bash
python3 scripts/browser-smoke.py
ABB_BROWSER_SMOKE_REQUIRED=1 python3 scripts/browser-smoke.py
```

It starts a local daemon, creates a paired-artifact run, and verifies the browser
`Span Inspector` and `Artifact Compare` surfaces when Playwright and a browser
engine are installed. The harness uses stable `data-testid` selectors for the
run detail, span inspector, Agent Kit controls, artifact compare,
compare copy/download controls, compare ingest controls, compare investigation evidence buttons, copy result/fallback surface, and compare panes. Without those optional browser dependencies it prints a clear skip unless
`ABB_BROWSER_SMOKE_REQUIRED=1` or `--required` is used.
The alpha demo uses `.abb-demo/` as an isolated reviewer store and prints a summary of the run IDs and export paths to inspect.

Release preparation lives in `docs/RELEASE_CHECKLIST.md`. First-user, local alpha,
and release note docs live in `docs/FIRST_USER_WORKFLOW.md`,
`docs/LOCAL_ALPHA_CHECKLIST.md`, `docs/ALPHA_RELEASE_NOTES.md`,
`docs/DESIGN_PARTNER_INTAKE.md`, `docs/DESIGN_PARTNER_FIRST_SEND_PACKET.md`,
`docs/DESIGN_PARTNER_OUTREACH.md`, `docs/DESIGN_PARTNER_FEEDBACK_FORM.md`, and
`docs/DESIGN_PARTNER_TRACKER.md`.

## OpenAI-Compatible Wrapper

When an agent already uses the OpenAI Python client shape, swap the import:

```python
from agent_black_box.openai import OpenAI

client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4.1-mini",
    messages=[{"role": "user", "content": "Hello"}],
)

print(response.choices[0].message.content)
print(response.abb_run_id)
```

The wrapper records request/response artifacts locally without starting the daemon.
It also supports `client.responses.create(...)`. Set `OPENAI_API_KEY` or pass
`api_key=...`, and set `ABB_OPENAI_BASE_URL` or `base_url=...` for another
OpenAI-compatible upstream. When the upstream returns token usage, `abb show`,
the browser timeline, and handoff briefings surface `input`, `output`, and `total` token counts.
Streaming is buffered in this first wrapper.

Run the no-network wrapper demo:

```bash
python3 examples/openai_wrapper_agent.py
abb runs
```

The example uses a fake transport, so it records a local model-call trace without
an API key or outbound network access.

## LangChain Callback Adapter

For LangChain-style callback flows, pass the dependency-free handler into your
chain, agent, or runnable:

```python
from agent_black_box.adapters.langchain import AgentBlackBoxCallbackHandler

callbacks = [AgentBlackBoxCallbackHandler(name="my-langchain-agent")]
# chain.invoke({"input": "..."}, config={"callbacks": callbacks})
```

Run the no-dependency callback demo:

```bash
python3 examples/langchain_callback_agent.py
abb runs
```

The demo simulates LangChain callback events and records chain, model, and tool
spans locally without installing LangChain.

## LangGraph Node Adapter

For LangGraph-style node functions, wrap each callable before adding it to the
graph:

```python
from agent_black_box.adapters.langgraph import LangGraphRecorder

recorder = LangGraphRecorder(name="my-langgraph-agent")
wrapped_node = recorder.wrap_node(my_node, name="my_node")
# builder.add_node("my_node", wrapped_node)
# recorder.end_run("ok") after the graph finishes
```

Run the no-dependency node demo:

```bash
python3 examples/langgraph_node_agent.py
abb runs
```

The demo records each node invocation as a `langgraph.node` span with JSON input
and output artifacts, without installing LangGraph.

## Tool Call Recorder

For plain Python tools or MCP-style `tools/call` payloads, use the dependency-free
tool recorder:

```python
from agent_black_box.adapters.tools import ToolCallRecorder

recorder = ToolCallRecorder(name="my-tool-agent")
wrapped_tool = recorder.wrap_tool(my_tool, name="my_tool")
result = wrapped_tool("input")
recorder.record_mcp_tool_call("knowledge.search", {"query": "refund"}, {"matches": []})
recorder.end_run("ok")
```

Run the no-dependency tool demo:

```bash
python3 examples/tool_call_agent.py
abb runs
```

The demo records tool schemas, inputs, outputs, and MCP-shaped arguments/results
as `tool.call` spans and JSON artifacts.

## OpenAI-Compatible Proxy

Start the daemon:

```bash
abb start
```

Point an OpenAI-compatible client at:

```text
http://127.0.0.1:43188/proxy/openai
```

The proxy forwards to `https://api.openai.com` by default and records model request/response artifacts into Agent Black Box. Set `ABB_OPENAI_BASE_URL` to use another OpenAI-compatible upstream. The proxy uses the incoming `Authorization` header or `OPENAI_API_KEY`. When the upstream returns token usage, the trace stores it on the model span and completion event.

This first proxy buffers streaming responses before returning them. It records a warning event when `stream: true` is requested.

## SDK Example

```python
from agent_black_box import annotate, record, span, tool

@tool
def lookup_customer(customer_id):
    return {"customer_id": customer_id, "tier": "pro"}

with record("customer-agent"):
    customer = lookup_customer("cust_123")
    with span("decide next action", type="model.call", attributes={"model": "mock"}):
        annotate("Model chose a support handoff")
```

## Design Intent

This first slice is intentionally dependency-free Python. It is not the final desktop architecture, but it proves the core loop:

1. Capture a run locally.
2. Store structured spans/events/artifacts.
3. Inspect a timeline.
4. Export a portable trace.
5. Generate a compact handoff packet for another agent.
6. Create a replay fixture.
7. Compare two runs.
8. Route OpenAI-compatible model calls through a local recorder.
9. Generate setup guidance for CLI, SDK, and proxy adoption.
10. Capture model calls through a direct OpenAI-compatible import swap.
11. Capture framework-shaped callbacks and graph nodes without forcing framework dependencies.
12. Capture plain and MCP-style tool calls with schemas, inputs, and outputs.
13. Keep agent code working even if capture is unavailable.
