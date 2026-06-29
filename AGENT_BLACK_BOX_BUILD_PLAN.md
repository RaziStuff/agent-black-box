# Agent Black Box Build, Ship, and Adoption Plan

## 1. Product Thesis

Agent Black Box is a local-first flight recorder for AI agents.

The wedge is simple: agents are becoming useful enough to run real work, but still hard to trust, debug, reproduce, compare, audit, and hand off. Developers can inspect normal software with logs, traces, debuggers, profilers, git history, test reports, and crash dumps. Agent systems often leave only a chat transcript, scattered tool logs, provider dashboards, and some vague memory of "it did something weird."

Agent Black Box gives every agent run a durable black box:

- What the agent was asked to do.
- What context it had.
- Which model calls it made.
- Which tools it invoked.
- Which files, browser pages, APIs, terminals, databases, and services it touched.
- What changed.
- What failed.
- What was retried.
- What was hidden from the user.
- How to replay, inspect, diff, export, and learn from the run later.

The product should feel like the missing debugging surface for agents: local by default, private by default, framework-neutral, and useful within minutes.

## 2. The Exact Startup Wedge

The first wedge should be:

> A local-first recorder and replay debugger for developers building AI agents.

This is narrower than "observability for AI" and stronger than "agent logs." The initial buyer/user is the builder who is already running agents locally or inside an internal dev workflow and needs to answer:

- Why did this agent do that?
- What did it see before it made the decision?
- Which tool call caused the bad state?
- Can I replay this failure without spending another hour reconstructing it?
- Can I compare the same task across models, prompts, tools, policies, or code changes?
- Can I share a sanitized run with a teammate?
- Can I create an eval, regression test, or fixture from this real run?

The wedge avoids starting as a generic cloud SaaS observability platform. It wins by being:

- Local-first: the trace stays on the user's machine unless they explicitly export or sync it.
- Agent-native: it understands planning, tool calls, context windows, artifacts, retries, memory, and state changes.
- Reproducible: it can replay agent runs and turn real runs into tests.
- Universal: it works with any agent through SDKs, wrappers, proxies, and an open trace format.

## 3. What "Local-First" Means

Local-first is not a marketing adjective. It must be an architectural constraint.

Agent Black Box should guarantee:

- Runs are recorded to local disk by default.
- The app works without an account.
- The app works without internet, except for the user's own agent/model/tool network usage.
- No run data leaves the machine unless the user explicitly chooses export, share, sync, or cloud backup.
- Secrets are redacted before display and before export.
- Users can inspect, query, export, delete, and migrate their data.
- The local database format and trace export format are documented.
- Teams can self-host sync or use bring-your-own-storage later.

Local-first does not mean single-device forever. It means the source of truth starts local and cloud is optional, visible, and controlled.

## 4. The Product Promise

Agent Black Box should make this promise:

> Add one line or run one proxy, reproduce the next weird agent run, and turn it into a debuggable timeline.

The first user experience must not require a platform migration, a new framework, or a big setup. It should support three adoption paths:

1. Drop-in SDK instrumentation.
2. Model API proxy instrumentation.
3. Tool/MCP proxy instrumentation.

If the user can only add one environment variable, they should still get useful data. If they can install an SDK, they should get richer data. If they can run a local daemon, they should get the full timeline.

## 5. Primary Users

### Solo Agent Builders

These users are building agents in local scripts, notebooks, CLI tools, small apps, or internal prototypes.

They need:

- Fast install.
- Zero cloud requirement.
- Clear run timeline.
- Prompt and tool call visibility.
- Replay and diff.
- Cheap storage.
- Easy export.

### Startup Engineering Teams

These users have agent workflows in product or operations.

They need:

- Shared debugging artifacts.
- Reproducible incidents.
- Run comparison across prompt/model/code changes.
- Redaction.
- Policy checks.
- CI integration.
- Team sync later.

### Enterprise AI Platform Teams

These are later users, not the first wedge.

They need:

- Audit trails.
- Permissioning.
- Retention controls.
- Deployment policies.
- Self-hosted storage.
- SIEM/export integrations.
- Compliance reviews.

Do not design the first version around enterprise bureaucracy. Design the foundations so enterprise needs are possible later.

## 6. Non-Goals For The First Version

The first product should not try to be:

- A full cloud observability platform.
- A model gateway for all production traffic.
- A replacement for LangSmith, Braintrust, OpenTelemetry, Datadog, or provider dashboards.
- A generic note-taking app for AI work.
- A prompt management suite.
- A team governance console.
- A hosted agent runtime.
- An agent marketplace.

Those can become integrations or later modules. The first version needs to be brutally useful for debugging and replaying real agent runs.

## 7. Core Product Surface

Agent Black Box should ship as four pieces:

1. Local daemon.
2. Desktop app.
3. CLI.
4. SDKs and adapters.

### 7.1 Local Daemon

The daemon is the local collector and storage service.

Responsibilities:

- Accept trace events from SDKs, proxies, and adapters.
- Normalize events into the Agent Black Box trace format.
- Persist metadata to SQLite.
- Persist large blobs and artifacts to local object storage.
- Redact secrets.
- Index runs for search.
- Serve the local app API.
- Manage retention policies.
- Manage import/export.
- Provide local health/status.

The daemon should bind to localhost only by default.

Suggested default port:

- `localhost:43188` for ingestion and app API.

The exact port can change, but it should be stable and configurable.

### 7.2 Desktop App

The desktop app is the main inspection surface.

Responsibilities:

- Show all recorded runs.
- Show a compact run summary before the full timeline.
- Show a timeline for each run.
- Show model calls, tool calls, state changes, files touched, browser activity, terminal activity, network requests, errors, retries, and artifacts.
- Support search and filters.
- Support replay.
- Support diff between runs.
- Support export/share.
- Support settings, redaction rules, storage location, and retention.

The desktop shell can be built with Tauri for a smaller local footprint or Electron for broader ecosystem maturity. Start with Tauri if the team is comfortable with Rust. Choose Electron if speed of iteration and Node integration matter more.

### 7.3 CLI

The CLI makes the product usable in terminal-first workflows.

Core commands:

```bash
abb start
abb status
abb runs
abb open
abb record -- command args
abb export RUN_ID
abb replay RUN_ID
abb diff RUN_A RUN_B
abb redact RUN_ID
abb doctor
```

The CLI must be excellent because agent developers live in terminals.

### 7.4 SDKs And Adapters

SDKs and adapters are the path to "agents everywhere."

Initial SDKs:

- Python SDK.
- TypeScript/JavaScript SDK.

Initial adapters:

- OpenAI-compatible chat/completions/responses wrapper.
- Anthropic-compatible wrapper.
- LangChain callback/tracer adapter.
- LangGraph adapter.
- CrewAI adapter.
- AutoGen adapter.
- MCP proxy adapter.
- Generic HTTP model proxy.

The product should not depend on any one framework winning. The trace format must be framework-neutral.

## 8. The Trace Format

The heart of the product is the trace format. Call it ABB Trace Format.

It should be:

- Append-only during capture.
- JSONL-friendly for streaming and debugging.
- Lossless enough for replay.
- Structured enough for search and diff.
- Stable enough for third-party adapters.
- Extensible without migrations for every new event type.

### 8.1 Top-Level Concepts

Core entities:

- Workspace.
- Project.
- Run.
- Span.
- Event.
- Artifact.
- Secret reference.
- Replay fixture.
- Eval case.

### 8.2 Run

A run is one agent execution session.

Fields:

```json
{
  "run_id": "run_...",
  "trace_version": "0.1",
  "created_at": "2026-06-27T00:00:00.000Z",
  "ended_at": null,
  "status": "running",
  "name": "Fix failing checkout test",
  "workspace_id": "ws_...",
  "project_id": "proj_...",
  "source": "python-sdk",
  "agent": {
    "name": "checkout-fixer",
    "framework": "langgraph",
    "version": "0.3.2"
  },
  "environment": {
    "os": "macos",
    "arch": "arm64",
    "runtime": "python",
    "runtime_version": "3.12.4",
    "git_commit": "abc123",
    "git_branch": "main"
  },
  "tags": ["local", "debug"],
  "metadata": {}
}
```

### 8.3 Span

A span represents a timed operation.

Span types:

- `agent.run`
- `agent.step`
- `model.call`
- `tool.call`
- `mcp.call`
- `browser.action`
- `browser.snapshot`
- `file.read`
- `file.write`
- `file.patch`
- `shell.command`
- `http.request`
- `database.query`
- `memory.read`
- `memory.write`
- `retrieval.query`
- `retrieval.result`
- `human.input`
- `policy.check`
- `error`
- `artifact.create`

Fields:

```json
{
  "span_id": "span_...",
  "run_id": "run_...",
  "parent_span_id": "span_...",
  "type": "model.call",
  "name": "gpt-5 tool decision",
  "started_at": "2026-06-27T00:00:01.000Z",
  "ended_at": "2026-06-27T00:00:03.500Z",
  "status": "ok",
  "input_ref": "blob_...",
  "output_ref": "blob_...",
  "attributes": {
    "provider": "openai",
    "model": "gpt-5",
    "temperature": 0.2,
    "input_tokens": 1234,
    "output_tokens": 456
  }
}
```

### 8.4 Event

An event is an instantaneous record inside a span.

Event types:

- `message.created`
- `token.streamed`
- `tool.requested`
- `tool.completed`
- `file.changed`
- `state.snapshot`
- `retry.scheduled`
- `warning.detected`
- `secret.redacted`
- `user.confirmed`
- `run.annotated`

Events should be cheap to write and safe to drop selectively if storage pressure is high.

### 8.5 Artifact

Artifacts are binary or large structured outputs.

Examples:

- Prompt payload.
- Model response.
- Tool JSON input.
- Tool JSON output.
- Screenshot.
- Browser DOM snapshot.
- File before/after.
- Patch.
- Terminal transcript.
- Retrieved documents.
- Audio/video later.

Artifacts should be content-addressed where possible:

```text
sha256/<hash>
```

This avoids duplicate storage and makes exports verifiable.

## 9. Storage Architecture

Use a local storage layout that is boring, inspectable, and portable.

Default directory:

```text
~/Library/Application Support/Agent Black Box/
```

On Linux:

```text
~/.local/share/agent-black-box/
```

On Windows:

```text
%APPDATA%/Agent Black Box/
```

Suggested structure:

```text
agent-black-box/
  abb.sqlite
  objects/
    sha256/
      ab/
        cd/
          <hash>
  exports/
  logs/
  indexes/
  config.toml
```

### 9.1 SQLite

SQLite should store:

- Runs.
- Spans.
- Events.
- Artifact metadata.
- Tags.
- Annotations.
- Redaction records.
- Replay fixtures.
- Settings.

Use WAL mode. Keep schema migrations explicit and tested.

### 9.2 Blob Store

The local object store should store:

- Raw prompts.
- Raw responses.
- Tool payloads.
- Screenshots.
- File snapshots.
- Diffs.
- Export bundles.

Objects should be immutable after write. If redaction modifies content, create a new redacted object and preserve an audit record locally.

### 9.3 Search Index

For MVP, SQLite FTS5 is enough.

Index:

- Run names.
- Prompt text after redaction.
- Model output after redaction.
- Tool names.
- Error messages.
- File paths.
- Tags.
- Annotations.

Later, add optional local vector search for semantic retrieval across runs.

## 10. Ingestion Architecture

Agent Black Box should support multiple capture levels.

### 10.1 Level 0: CLI Wrapper

The user runs:

```bash
abb record -- python agent.py
```

Capture:

- Process start/end.
- stdout/stderr.
- exit code.
- environment summary.
- git metadata.
- optional file changes before/after.

This requires no SDK integration and gives immediate value.

### 10.2 Level 1: Model API Proxy

The user sets:

```bash
OPENAI_BASE_URL=http://localhost:43188/proxy/openai
ANTHROPIC_BASE_URL=http://localhost:43188/proxy/anthropic
```

Capture:

- Model request.
- Model response.
- streaming chunks.
- timing.
- token usage if provided.
- errors.

The proxy forwards traffic to the real provider. API keys remain in the user's environment and are never stored unless the user explicitly opts into a local key vault.

### 10.3 Level 2: SDK Instrumentation

Python:

```python
from agent_black_box import record

with record("research-agent"):
    agent.run("Find the source of the failing test")
```

TypeScript:

```ts
import { record } from "@agent-black-box/sdk";

await record("research-agent", async () => {
  await agent.run("Find the source of the failing test");
});
```

Capture:

- agent steps.
- model calls.
- tool calls.
- custom spans.
- state snapshots.
- metadata.
- annotations.

### 10.4 Level 3: Framework Adapters

Adapters should auto-instrument popular agent frameworks.

Pattern:

```python
from agent_black_box.adapters.langgraph import instrument

instrument(graph)
graph.invoke(...)
```

Adapters must preserve framework semantics and never change execution behavior.

### 10.5 Level 4: Tool And MCP Proxy

Many agents use tools through MCP or local function registries. Agent Black Box should capture tools as first-class events.

MCP proxy flow:

```text
agent <-> abb mcp proxy <-> actual MCP server
```

Capture:

- tool list.
- tool schema.
- tool call input.
- tool call output.
- duration.
- error.
- resource reads.
- prompts.

This is one of the strongest paths to "agents everywhere" because it records actions regardless of the agent framework.

## 11. Replay Architecture

Replay is the feature that makes Agent Black Box more than logs.

There are three replay modes.

### 11.1 Visual Replay

The app replays the run timeline:

- Messages appear in sequence.
- Tool calls open and close.
- Browser screenshots advance.
- File diffs appear when changes happen.
- Errors and retries show in context.

This is deterministic because it replays recorded data.

### 11.2 Mocked Replay

The original agent code runs again, but external calls are replaced with recorded responses.

Mocked components:

- Model responses.
- Tool responses.
- HTTP responses.
- retrieval results.
- time.
- selected filesystem reads.

This lets users reproduce control flow without paying model costs or hitting live services.

### 11.3 Live Replay

The original task is run again against live models/tools, using the same inputs and optional constraints.

This supports:

- Prompt comparisons.
- Model comparisons.
- Tool version comparisons.
- Regression detection.
- eval generation.

Live replay must clearly show that it can diverge from the original.

## 12. Diff Architecture

Diff is how users learn from agent changes.

Compare:

- Run A vs Run B.
- Model A vs Model B.
- Prompt version A vs Prompt version B.
- Tool version A vs Tool version B.
- Code commit A vs Code commit B.
- Successful run vs failed run.

Diff views:

- Timeline alignment.
- Model call payload diff.
- Tool input/output diff.
- File patch diff.
- Cost and latency diff.
- Error diff.
- final result diff.

The app should summarize likely divergence points:

- First changed model output.
- First changed tool call.
- First error.
- First changed file write.
- First policy warning.

## 13. Redaction And Privacy

Redaction is a core product feature, not an afterthought.

### 13.1 Default Redaction

Automatically detect and redact:

- API keys.
- Bearer tokens.
- OAuth tokens.
- SSH keys.
- private keys.
- passwords.
- cookies.
- database URLs with credentials.
- `.env` values.
- common cloud credentials.
- email addresses if enabled.
- phone numbers if enabled.
- credit card numbers if enabled.
- Social Security numbers if enabled.

### 13.2 Redaction Rules

Users should be able to define rules:

```toml
[[redaction.rules]]
name = "Internal customer IDs"
pattern = "cust_[a-zA-Z0-9]+"
replacement = "cust_[redacted]"
enabled = true
```

### 13.3 Redaction Timing

There are two levels:

- Capture-time redaction: secrets never land in the trace store.
- Export-time redaction: sensitive data can exist locally but is removed before sharing.

Default should favor capture-time redaction for obvious secrets.

### 13.4 Secret Handling

If the product ever stores credentials for proxying, use the OS keychain:

- macOS Keychain.
- Windows Credential Manager.
- Linux Secret Service.

Do not store raw secrets in SQLite.

## 14. Security Model

Agent Black Box runs on localhost and observes sensitive work. Treat it as trusted local infrastructure.

Requirements:

- Bind local API to `127.0.0.1` by default.
- Require a local auth token for app/API access.
- Rotate local auth token on reset.
- Store token in a config file with restricted permissions.
- Use OS-level secure storage for secrets.
- Validate ingestion payload sizes.
- Avoid arbitrary file reads through the app API.
- Sandbox import processing.
- Use signed release artifacts.
- Provide checksums for downloads.
- Keep auto-update visible and controllable.
- Never expose local trace API on LAN unless explicitly configured.

Threats to handle:

- Malicious web page trying to hit localhost API.
- Malicious trace import.
- Oversized payload denial of service.
- Secret leakage in export.
- Cross-project data confusion.
- Unsafe replay executing live destructive tools.

Replay must have safety modes. By default, live replay should require confirmation before tool calls that modify files, call external APIs, run shell commands, or write databases.

## 15. Desktop UX

The desktop app should be built for scanning and debugging, not marketing.

### 15.1 Primary Navigation

Views:

- Runs.
- Projects.
- Search.
- Replays.
- Evals.
- Exports.
- Settings.

### 15.2 Runs Inbox

The default screen shows recent runs.

Columns:

- Status.
- Run name.
- Agent/framework.
- Started.
- Duration.
- Model.
- Cost.
- Tool calls.
- Files changed.
- Errors.
- Tags.

Filters:

- Status.
- Project.
- Agent.
- Model.
- Date.
- Has errors.
- Has file changes.
- Has browser activity.
- Has policy warnings.
- Tags.

### 15.3 Run Detail

The run detail view is the core screen.

Panels:

- Left: timeline.
- Center: selected event inspector.
- Right: context, metadata, artifacts, annotations.

Timeline rows:

- User input.
- Agent step.
- Model call.
- Tool call.
- Browser action.
- File change.
- Shell command.
- Network call.
- Error.
- Human approval.
- Final output.

The user should be able to click any row and see:

- Input.
- Output.
- Duration.
- status.
- raw JSON.
- related artifacts.
- parent/child spans.
- redaction status.

### 15.4 Model Call Inspector

Show:

- Provider.
- Model.
- Params.
- System messages.
- Developer messages.
- user messages.
- tool definitions.
- response.
- finish reason.
- token usage.
- latency.
- cost estimate.
- cache information if available.

Must support:

- Collapse long payloads.
- Copy redacted JSON.
- Export payload.
- Convert to fixture.
- Compare with another model call.

### 15.5 Tool Call Inspector

Show:

- Tool name.
- schema.
- input JSON.
- output JSON.
- stdout/stderr if relevant.
- status.
- duration.
- error stack.
- side effects.
- related files/network/database operations.

### 15.6 File Change Viewer

Show:

- Files read.
- files written.
- patches.
- before/after snapshots if captured.
- generated artifacts.

The user should be able to open a patch, copy it, or export it.

### 15.7 Browser Replay

For browser agents:

- Show URL.
- DOM title.
- screenshot.
- action taken.
- selector used.
- console errors.
- network errors.
- page text snapshot if captured.

### 15.8 Annotation And Handoff

Users should be able to annotate a run:

- "This is the first bad decision."
- "Tool returned stale data."
- "Prompt too vague."
- "Regression after commit abc123."

Annotations make runs shareable as debugging artifacts.

### 15.9 Export

Export options:

- `.abb` bundle.
- JSONL trace.
- Markdown report.
- HTML report.
- eval fixture.
- redacted support package.

Every export must show a redaction preview.

## 16. CLI UX

The CLI must be fast, quiet, and scriptable.

### 16.1 Install

Install options:

```bash
brew install agent-black-box
curl -fsSL https://agentblackbox.dev/install.sh | sh
npm install -g @agent-black-box/cli
pipx install agent-black-box
```

Do not require all of these on day one, but design the packaging around them.

### 16.2 First Run

```bash
abb doctor
abb start
abb record -- python examples/basic_agent.py
abb open
```

### 16.3 Scriptability

Every list command should support JSON:

```bash
abb runs --json
abb export run_123 --format jsonl --output trace.jsonl
```

### 16.4 CI

CI mode:

```bash
abb replay fixtures/*.abb --ci
abb diff baseline.abb current.abb --fail-on-regression
```

This helps teams adopt the product without opening the desktop app.

## 17. SDK API Design

SDKs should be tiny at the surface and powerful underneath.

### 17.1 Python SDK

Core:

```python
from agent_black_box import record, span, annotate

with record("invoice-agent", tags=["dev"]):
    with span("load invoice", type="tool.call"):
        invoice = load_invoice()

    result = agent.run(invoice)
    annotate("Result looked correct")
```

Model wrapper:

```python
from agent_black_box.openai import OpenAI

client = OpenAI()
response = client.responses.create(...)
```

Tool wrapper:

```python
from agent_black_box import tool

@tool
def lookup_customer(customer_id: str):
    return db.lookup(customer_id)
```

### 17.2 TypeScript SDK

Core:

```ts
import { record, span, annotate } from "@agent-black-box/sdk";

await record("invoice-agent", async () => {
  await span("load invoice", { type: "tool.call" }, async () => {
    return loadInvoice();
  });

  await agent.run();
  annotate("Result looked correct");
});
```

### 17.3 Design Constraints

SDKs must:

- Fail open if the daemon is unavailable.
- Buffer events locally for short outages.
- Never crash the user's agent because capture failed.
- Add low overhead.
- Support async execution.
- Preserve parent/child spans across async boundaries.
- Provide explicit flush.
- Support custom metadata.
- Support capture disabling by environment variable.

Environment variables:

```text
ABB_ENABLED=true
ABB_DAEMON_URL=http://127.0.0.1:43188
ABB_PROJECT=my-project
ABB_CAPTURE_PAYLOADS=true
ABB_REDACTION_MODE=strict
```

## 18. Framework Adapter Strategy

Do not hand-author every integration deeply at first. Use a layered adapter strategy.

### 18.1 Generic Foundation

Build a generic tracing API:

- start run.
- end run.
- start span.
- end span.
- record event.
- record artifact.
- record error.

Every adapter maps framework concepts onto this API.

### 18.2 Adapter Priorities

Phase 1:

- OpenAI-compatible wrapper: `from agent_black_box.openai import OpenAI` with local request/response artifact capture.
- Model usage extraction for OpenAI-compatible wrappers/proxies, surfaced in CLI and handoff summaries.
- Failure-first debug path: CLI, browser, and handoff surfaces guide users from first warning/failure/annotation to relevant artifacts.
- Browser artifact preview upgrades: debug-path cards open referenced artifacts directly with metadata and formatted JSON.
- Artifact relationship view: group request/response/schema/input/output blobs by model/tool/node span.
- Browser span inspector: open one grouped span as a focused debugging unit and switch it from timeline or group cards.
- Browser artifact compare: render request/response, input/output, and schema/input pairs side by side inside the span inspector.
- Anthropic-compatible wrapper.
- generic HTTP proxy.
- MCP proxy.
- LangChain callbacks: `AgentBlackBoxCallbackHandler` for chain/model/tool capture without a hard LangChain dependency.
- LangGraph node wrapper: `LangGraphRecorder.wrap_node` for state transition capture without a hard LangGraph dependency.
- Generic tool call recorder: `ToolCallRecorder` for plain Python and MCP-shaped tool inputs, outputs, schemas, and failures.

Phase 2:

- CrewAI.
- AutoGen.
- LlamaIndex.
- browser automation adapters.
- retrieval/vector DB adapters.

Phase 3:

- IDE agent adapters.
- CI agents.
- internal enterprise frameworks.
- hosted agent runtime exporters.

### 18.3 Adapter Quality Bar

Each adapter needs:

- Minimal install docs.
- Working example.
- Snapshot test for emitted trace.
- Version compatibility matrix.
- Graceful failure.
- No monkeypatching unless isolated and documented.

## 19. MCP Strategy

MCP should be treated as a major distribution channel.

Agent Black Box should provide:

- MCP proxy recorder.
- MCP server exposing recorded runs.
- MCP tools for agents to inspect previous runs.

### 19.1 MCP Proxy Recorder

Command:

```bash
abb mcp proxy --server "python my_server.py"
```

It records:

- server capabilities.
- tool schemas.
- resource reads.
- prompts.
- tool calls.
- tool results.
- errors.

### 19.2 MCP Server For Agent Memory

Expose tools:

- `abb_search_runs`
- `abb_get_run`
- `abb_get_span`
- `abb_get_artifact`
- `abb_create_annotation`
- `abb_create_eval_from_run`

This makes Agent Black Box useful to agents themselves. An agent can ask: "Have I failed at this before? What happened last time?"

### 19.3 Safety

The MCP server should default to read-only access. Write actions like annotation creation can be enabled separately. Destructive actions should not exist.

## 20. Making It Usable For Agents Everywhere

"Agents everywhere" requires both technical reach and conceptual simplicity.

### 20.1 Universal Capture Paths

Support five capture paths:

1. SDK instrumentation.
2. API proxy.
3. CLI process wrapper.
4. MCP proxy.
5. Import/export format.

This means any agent can be recorded even if it is:

- A Python script.
- A Node app.
- A desktop agent.
- A CLI coding agent.
- A browser agent.
- A no-code platform calling local tools.
- A hosted agent that can export logs.
- A custom internal framework.

### 20.2 Open Trace Format

Publish the trace schema early.

Repository:

```text
agent-black-box/spec
```

Contents:

- JSON schema.
- examples.
- validator CLI.
- versioning policy.
- adapter author guide.
- sample exports.

The format is the standardization wedge. If people can emit ABB traces without using the app, the app becomes more valuable.

### 20.3 Importers

Build importers for:

- OpenTelemetry traces.
- JSONL logs.
- LangSmith exports if available from users.
- Braintrust eval logs if exported.
- provider request logs if exported.
- custom CSV/JSON run logs.

Do not chase every platform API first. Make import easy.

### 20.4 Exporters

Build exporters to:

- JSONL.
- OpenTelemetry.
- Markdown.
- HTML.
- JUnit-style CI report.
- eval fixture.

Export is trust. Users need to know they are not trapped.

### 20.5 Agent-Readable Runs

Agents should be able to consume prior runs.

Use cases:

- "Find similar failures."
- "Summarize why this run failed."
- "Generate a regression test."
- "Suggest better tool descriptions."
- "Identify flaky steps."
- "Compare this run to the best prior run."

This should be implemented through:

- local MCP server.
- CLI JSON output.
- local REST API.

## 21. MVP Scope

The MVP should prove:

- A user can install Agent Black Box.
- Record a real agent run.
- Inspect a useful timeline.
- See model calls and tool calls.
- See errors.
- Export a redacted trace.
- Replay visually.

### 21.1 MVP Must-Have Features

Daemon:

- local ingestion API.
- SQLite storage.
- object storage.
- run/span/event schema.
- redaction for obvious secrets.
- local auth token.

CLI:

- `abb start`
- `abb status`
- `abb record -- ...`
- `abb runs`
- `abb open`
- `abb export`
- `abb doctor`

Desktop app:

- runs list.
- run detail timeline.
- model call inspector.
- tool call inspector.
- raw JSON viewer.
- search.
- settings.

SDKs:

- Python core SDK.
- TypeScript core SDK.
- OpenAI-compatible wrapper.
- generic custom span API.

Proxy:

- OpenAI-compatible proxy.
- basic streaming support.

Export:

- JSONL.
- HTML or Markdown report.
- `.abb` bundle.

Docs:

- 5-minute quickstart.
- Python example.
- TypeScript example.
- proxy example.
- privacy/security page.
- trace format page.

### 21.2 MVP Deliberately Excluded

Exclude from first MVP:

- Team cloud sync.
- billing.
- complex permissions.
- full eval dashboard.
- hosted run storage.
- deep browser replay.
- deep framework support for every library.
- enterprise SSO.
- vector search.

## 22. Technical Stack

Recommended stack:

### 22.1 Daemon

Use Rust or Go.

Rust advantages:

- Works well with Tauri.
- Strong performance.
- Good local binary distribution.
- memory safety.
- excellent SQLite crates.

Go advantages:

- Faster team ramp for many backend engineers.
- simple concurrency.
- easy static binaries.
- strong HTTP server ergonomics.

Recommendation:

- If choosing Tauri, use Rust daemon/library.
- If choosing Electron, use Go daemon.

### 22.2 Desktop

Frontend:

- TypeScript.
- React.
- Vite.
- TanStack Query.
- Zustand or Jotai for local UI state.
- Monaco or CodeMirror for JSON/diff views.
- a virtualized timeline list.

Shell:

- Tauri for small footprint.
- Electron if deeper Node integration is needed.

### 22.3 Local Database

- SQLite.
- sqlc or Diesel depending on daemon language.
- WAL enabled.
- migrations with explicit version table.
- FTS5 for search.

### 22.4 SDKs

Python:

- `httpx`.
- `pydantic`.
- contextvars for active run/span.
- pytest snapshots.

TypeScript:

- fetch-compatible client.
- async local storage for active run/span.
- zod for validation.
- vitest.

### 22.5 Packaging

CLI:

- Homebrew tap.
- npm package wrapper.
- Python package for SDK and optional CLI.
- direct binaries from GitHub releases.

Desktop:

- signed macOS app.
- Windows installer.
- Linux AppImage/deb/rpm later.

## 23. Local API

Expose a local API used by SDKs, CLI, desktop, and MCP server.

### 23.1 Ingestion Endpoints

```http
POST /v1/runs
POST /v1/runs/{run_id}/end
POST /v1/spans
POST /v1/spans/{span_id}/end
POST /v1/events
POST /v1/artifacts
POST /v1/batch
```

Use `/v1/batch` as the main high-throughput path.

### 23.2 Query Endpoints

```http
GET /v1/runs
GET /v1/runs/{run_id}
GET /v1/runs/{run_id}/timeline
GET /v1/spans/{span_id}
GET /v1/artifacts/{artifact_id}
GET /v1/search
GET /v1/settings
PATCH /v1/settings
```

### 23.3 Export Endpoints

```http
POST /v1/runs/{run_id}/export
GET /v1/exports/{export_id}
```

### 23.4 Auth

Use a local bearer token:

```http
Authorization: Bearer <local-token>
```

SDKs discover the token from:

- environment variable.
- config file.
- explicit SDK option.

## 24. Data Model

SQLite tables:

- `schema_migrations`
- `workspaces`
- `projects`
- `runs`
- `spans`
- `events`
- `artifacts`
- `artifact_links`
- `tags`
- `run_tags`
- `annotations`
- `redaction_rules`
- `redaction_hits`
- `exports`
- `replay_fixtures`
- `settings`

Indexes:

- `runs(created_at)`
- `runs(project_id, created_at)`
- `runs(status)`
- `spans(run_id, started_at)`
- `spans(parent_span_id)`
- `spans(type)`
- `events(run_id, ts)`
- `events(span_id, ts)`
- `artifacts(hash)`
- FTS index over searchable text.

## 25. Performance Requirements

The recorder must not make agents feel slow.

Targets:

- SDK overhead under 5 ms per span in normal local operation.
- Batch ingestion for high-volume events.
- UI can open a run with 10,000 events within 2 seconds.
- Timeline virtualization for large runs.
- Streaming writes for large artifacts.
- Backpressure when daemon is overloaded.
- SDK drops noncritical events before blocking user code.
- Hard per-run storage limit configurable.

Storage retention:

- Default keep all runs until 10 GB.
- Warn before pruning.
- Allow retention by days, size, project, or tags.

## 26. Reliability Requirements

Capture must be reliable but never at the expense of the user's agent completing work.

Rules:

- If daemon unavailable, SDK buffers briefly then degrades.
- If disk full, daemon marks runs incomplete and stops accepting large artifacts.
- If payload invalid, daemon stores an error event if possible.
- If redaction fails, export should block rather than leak secrets.
- If app crashes, daemon continues.
- If daemon crashes, app shows recovery status.
- If migration fails, preserve old database and create diagnostic bundle.

## 27. Replay Safety

Replay can be dangerous if it repeats real actions.

Classify tools:

- Read-only.
- local write.
- external write.
- shell command.
- payment/financial.
- email/message send.
- unknown.

Default replay policy:

- Visual replay: always allowed.
- Mocked replay: allowed by default.
- Live replay with read-only tools: allowed with notice.
- Live replay with writes or unknown tools: require confirmation per tool class.

Provide dry-run adapters where possible.

## 28. Eval And Regression Path

Agent Black Box should turn real failures into tests.

MVP:

- "Create fixture from run."
- Fixture captures task input, model/tool mocks, expected final state, and annotations.
- CLI can replay fixture.

Later:

- eval suites.
- scoring functions.
- model/prompt matrix.
- CI regression gates.
- flaky run detection.

This is important because debugging alone is reactive. Evals make the product part of the build loop.

## 29. Documentation Plan

Docs must be part of the product.

Pages:

- Quickstart.
- Install.
- Record your first run.
- Python SDK.
- TypeScript SDK.
- API proxy setup.
- MCP proxy setup.
- CLI reference.
- Desktop app guide.
- Trace format.
- Redaction and privacy.
- Replay modes.
- Export and sharing.
- Adapter author guide.
- Troubleshooting.

Examples:

- basic Python agent.
- OpenAI wrapper no-network demo.
- basic TypeScript agent.
- LangGraph example.
- MCP tool example.
- browser agent example.
- CI replay example.

Tone:

- Practical.
- Short examples first.
- Security details explicit.
- No vague "observability platform" language.

## 30. Developer Experience

The product must win on first 10 minutes.

### 30.1 First 10 Minutes

Goal:

- Install.
- generate setup guide.
- start daemon.
- record one run.
- open UI.
- inspect timeline.
- export report.

The quickstart must be copy-pasteable.

### 30.2 `abb init`

`abb init` should make the right setup path obvious without editing user code.

It should support:

```bash
abb init
abb init --mode cli
abb init --mode sdk
abb init --mode proxy
abb init --json
```

The command should create local files under `.abb/init/`:

- markdown setup guide.
- shell env helper.
- machine-readable JSON init plan.

The JSON plan is for agents and scripts. It should include the chosen mode,
data directory, daemon URL, setup commands, snippets, doctor report, and next
steps. It must not include secret values.

### 30.3 `abb doctor`

`abb doctor` should check:

- Python version and executable.
- Agent Black Box CLI version and entrypoint.
- database writable.
- storage path writable.
- local object/export directories writable.
- local API reachable.
- auth token presence without printing secret values.
- proxy configuration and API-key presence without printing secret values.
- common env vars.
- SDK versions.
- redaction rules valid.
- app installed.

The command should support:

```bash
abb doctor
abb doctor --json
abb doctor --strict
```

The JSON report is the shared contract for agents, scripts, CI, and support
packets. It should include `doctor_version`, `status`, `summary`, `checks`,
`next_steps`, environment presence flags, and no secret values.

### 30.4 Examples Repository

Create:

```text
agent-black-box/examples
  python-basic/
  python-openai-proxy/
  typescript-basic/
  langgraph/
  mcp-proxy/
  ci-replay/
```

Every example should have:

- README.
- one command to run.
- expected screenshot or output.
- sample trace.

## 31. Shipping Plan

### 31.1 Phase 0: Product Skeleton

Duration:

- 1 to 2 weeks.

Deliverables:

- Product spec.
- trace schema v0.1.
- storage schema.
- local API shape.
- CLI command list.
- UI wireframes.
- example traces.
- redaction policy.

Success:

- A developer can look at the spec and understand exactly what gets recorded.

### 31.2 Phase 1: Thin End-To-End Slice

Duration:

- 2 to 4 weeks.

Deliverables:

- daemon accepts runs/spans/events.
- SQLite persistence.
- CLI starts daemon and lists runs.
- Python SDK records custom spans.
- desktop app lists runs and shows simple timeline.
- JSONL export.

Success:

- Record a toy Python script and inspect it in UI.

### 31.3 Phase 2: Real Agent MVP

Duration:

- 4 to 6 weeks.

Deliverables:

- OpenAI-compatible wrapper/proxy.
- model call inspector.
- tool call inspector.
- basic redaction.
- timeline virtualization.
- run search.
- `.abb` export bundle.
- Markdown/HTML report.
- docs quickstart.

Success:

- Record a real local agent using a model and tools.
- Debug a failed run from the UI.

### 31.4 Phase 3: Replay And Diff

Duration:

- 4 to 6 weeks.

Deliverables:

- visual replay.
- mocked replay for model calls.
- run diff.
- fixture creation.
- CLI replay.
- CI mode.

Success:

- Turn a real failure into a replayable fixture and compare a fixed run against it.

### 31.5 Phase 4: Adapters And Distribution

Duration:

- 4 to 8 weeks.

Deliverables:

- TypeScript SDK.
- MCP proxy.
- LangChain adapter.
- LangGraph adapter.
- Homebrew package.
- npm package.
- signed desktop app alpha.
- examples repo.

Success:

- 10 external developers record runs from 3 or more frameworks.

### 31.6 Phase 5: Private Beta

Duration:

- 6 to 8 weeks.

Deliverables:

- onboarding flow.
- crash reporting with opt-in and local redaction.
- storage management.
- better redaction UI.
- import/export hardening.
- performance work.
- adapter docs.
- feedback loop.

Success:

- 25 to 50 active users.
- 5 teams using it weekly.
- at least 3 bug reports where ABB made diagnosis faster.
- at least 5 exported traces shared by users.

### 31.7 Phase 6: Public Launch

Duration:

- after private beta metrics show retention.

Deliverables:

- polished landing site.
- public docs.
- public trace spec.
- release signing.
- install scripts.
- launch examples.
- security/privacy page.
- roadmap.

Success:

- Users can install without handholding.
- community adapters begin appearing.
- product is associated with "agent flight recorder."

## 32. Team And Ownership

Minimum team:

- 1 systems/backend engineer for daemon, storage, CLI.
- 1 frontend/product engineer for desktop UI.
- 1 SDK/integrations engineer.
- 1 product/design founder or lead.

Part-time needs:

- security review.
- packaging/release engineering.
- technical writing.

Ownership:

- Daemon and schema: one clear owner.
- SDKs and adapters: one owner per language.
- Desktop UX: one owner.
- Docs/examples: explicit owner, not leftover work.

## 33. Repository Structure

Recommended monorepo:

```text
agent-black-box/
  apps/
    desktop/
  crates/ or services/
    daemon/
    trace/
    redaction/
  cli/
  sdks/
    python/
    typescript/
  adapters/
    langchain/
    langgraph/
    mcp/
  spec/
    trace-format/
    schemas/
    examples/
  docs/
  examples/
  tests/
    fixtures/
    e2e/
```

Keep the trace format package independent so adapters can depend on it without pulling in the daemon or app.

## 34. Testing Strategy

### 34.1 Unit Tests

Cover:

- schema validation.
- redaction rules.
- SQLite migrations.
- event normalization.
- span nesting.
- artifact hashing.
- export/import.
- SDK buffering.

### 34.2 Integration Tests

Cover:

- SDK to daemon.
- CLI to daemon.
- proxy to provider mock.
- desktop to local API.
- MCP proxy to fake MCP server.
- replay fixture.

### 34.3 Golden Trace Tests

Maintain golden traces for:

- simple run.
- model call.
- tool call.
- error run.
- streaming model response.
- file change.
- MCP tool call.

Every adapter should emit traces matching expected schema snapshots.

### 34.4 E2E Tests

Use Playwright for the desktop/web UI.

Test:

- runs list loads.
- run detail opens.
- timeline renders.
- inspector shows payload.
- search works.
- export flow shows redaction preview.

### 34.5 Performance Tests

Generate runs with:

- 1,000 events.
- 10,000 events.
- 100,000 events.
- large artifacts.
- many small spans.

Ensure the app stays responsive.

## 35. Release Engineering

Release channels:

- nightly.
- alpha.
- beta.
- stable.

Artifacts:

- macOS app.
- Windows installer.
- Linux package.
- CLI binaries.
- Python package.
- npm package.
- checksums.
- signatures.

Release checklist:

- tests pass.
- migrations tested from previous version.
- app update tested.
- daemon compatibility tested.
- SDK compatibility tested.
- docs updated.
- changelog updated.
- checksums published.
- rollback plan ready.

## 36. Telemetry Policy

Because the product is local-first, telemetry must be opt-in and narrow.

Default:

- no product telemetry.
- no run data upload.
- no prompt upload.
- no tool payload upload.

Optional telemetry:

- app version.
- OS.
- crash reports.
- feature usage counts.
- performance metrics.

Crash reports must:

- strip traces.
- strip paths where possible.
- show preview before sending if feasible.

This policy is part of the brand.

## 37. Monetization Path

Start free for local use.

Potential paid tiers:

### 37.1 Pro Local

- advanced replay.
- advanced diff.
- larger local indexes.
- local semantic search.
- premium adapters.
- priority support.

### 37.2 Team Sync

- shared projects.
- encrypted sync.
- role-based access.
- shared annotations.
- team eval suites.
- retention policies.

### 37.3 Enterprise

- self-hosted sync.
- SSO.
- audit exports.
- compliance controls.
- SIEM integration.
- custom adapters.
- support SLAs.

Do not block the basic black box behind a paywall. The standard needs adoption.

## 38. Go-To-Market

Positioning:

> The local-first flight recorder for AI agents.

Audience:

- developers building agents.
- AI engineering teams.
- startup founders shipping agentic products.
- platform teams later.

Launch channels:

- GitHub.
- Hacker News.
- X/LinkedIn demos.
- technical blog posts.
- agent framework communities.
- MCP community.
- examples with real failure debugging.
- podcasts/newsletters focused on AI engineering.

Content that will work:

- "We replayed a failed agent run and found the exact bad tool call."
- "Turn any agent failure into a regression test."
- "Local-first tracing for agents."
- "Why chat transcripts are not enough for agent debugging."
- "The open black box format for AI agents."

Avoid vague observability language. Show concrete timelines, diffs, and replay.

## 39. Community Strategy

Make the format and adapter ecosystem open.

Open source candidates:

- trace spec.
- SDKs.
- CLI.
- adapters.
- examples.

Keep proprietary if needed:

- polished desktop app.
- advanced replay/diff.
- team sync.
- enterprise controls.

Community contributions:

- adapter templates.
- good first issues.
- trace samples.
- framework compatibility matrix.
- plugin examples.

The adoption loop:

1. Developers emit ABB traces.
2. More tools can read ABB traces.
3. ABB desktop becomes the best local viewer.
4. Teams standardize on the format.
5. Paid collaboration/sync becomes natural.

## 40. Key Risks

### 40.1 Too Much Surface Area

Risk:

- Trying to support every framework badly.

Mitigation:

- Build generic capture paths first.
- Pick 2 to 3 excellent adapters.
- Publish adapter authoring guide.

### 40.2 Privacy Trust Failure

Risk:

- Users fear the recorder leaks sensitive prompts or data.

Mitigation:

- local-first by default.
- visible storage.
- no account required.
- explicit exports.
- redaction preview.
- open trace spec.

### 40.3 Replay Complexity

Risk:

- deterministic replay is hard across tools and external systems.

Mitigation:

- ship visual replay first.
- then mocked model replay.
- then tool mocking.
- be honest about live replay divergence.

### 40.4 UI Overload

Risk:

- timelines become unreadable.

Mitigation:

- filters.
- grouping.
- severity markers.
- "first divergence" summaries.
- progressive detail.

### 40.5 Performance And Storage

Risk:

- recording everything creates huge traces.

Mitigation:

- configurable capture levels.
- blob deduplication.
- retention policies.
- payload sampling.
- artifact size limits.

## 41. Product Metrics

Local-first makes telemetry tricky, so use opt-in metrics and qualitative signals.

Track where possible:

- installs.
- first run recorded.
- run detail opened.
- export created.
- replay used.
- diff used.
- fixture created.
- adapter used.
- weekly active local projects.

Qualitative metrics:

- "Did ABB help you find the issue?"
- "What did you still need to inspect manually?"
- "What framework were you using?"
- "What data was missing?"
- "Would you share a redacted run with a teammate?"

North star:

- Replayed or inspected agent failures per active developer per week.

## 42. First 90 Days

### Days 1-15

- Finalize trace schema v0.1.
- Implement daemon skeleton.
- Implement SQLite schema.
- Implement Python SDK basics.
- Implement CLI start/status/record/runs.
- Build sample traces.

### Days 16-30

- Build desktop runs list and timeline.
- Implement artifact store.
- Add redaction basics.
- Add JSONL export.
- Record first real agent script.
- Write quickstart.

### Days 31-45

- Add OpenAI-compatible wrapper/proxy.
- Add model call inspector.
- Add tool call inspector.
- Add search.
- Add Markdown/HTML export.
- Improve `abb doctor`.

### Days 46-60

- Add visual replay.
- Add mocked model replay.
- Add fixture creation.
- Add CLI replay.
- Add golden trace tests.

### Days 61-75

- Add TypeScript SDK.
- Add MCP proxy.
- Add LangGraph and LangChain adapters.
- Package CLI.
- Create examples repo.
- Start design partner onboarding.

### Days 76-90

- Harden install/update.
- Improve redaction UI.
- Add diff v1.
- performance pass.
- private beta.
- write launch demos.

## 43. The First Demo

The first public demo should be extremely concrete.

Scenario:

- A local agent is asked to fix a failing test.
- It reads files.
- It calls a model.
- It runs a shell command.
- It edits a file.
- It fails because it used stale context or picked the wrong file.
- Agent Black Box shows the timeline.
- The user clicks the first bad model decision.
- The user creates a replay fixture.
- The user changes the prompt or tool description.
- The fixed run is compared against the failed run.

This demo explains the product better than any landing page.

## 44. Concrete Build Order

Build in this exact order:

1. Trace schema.
2. daemon ingestion API.
3. SQLite persistence.
4. artifact store.
5. CLI record wrapper.
6. Python SDK.
7. desktop runs list.
8. run timeline.
9. model call wrapper.
10. model call inspector.
11. tool span API.
12. tool call inspector.
13. redaction.
14. export.
15. visual replay.
16. mocked replay.
17. diff.
18. TypeScript SDK.
19. MCP proxy.
20. framework adapters.
21. packaging.
22. docs/examples.
23. private beta.
24. public launch.

This order keeps the product end-to-end at every stage.

## 45. Definition Of Done For V1

V1 is done when:

- A developer can install it in under 5 minutes.
- It records a Python or TypeScript agent run.
- It captures model calls and tool calls.
- It shows a useful timeline.
- It redacts obvious secrets.
- It exports a redacted report.
- It visually replays a run.
- It can create a fixture from a run.
- It can compare two runs.
- It works without an account.
- It does not upload data by default.
- It has clear docs.
- At least 10 real users have used it on their own agents.

## 46. The Long-Term Vision

If Agent Black Box works, it becomes the local memory and debugging substrate for agentic software.

Short term:

- Debug individual runs.

Medium term:

- Turn failures into tests.
- compare prompts/models/tools.
- share sanitized traces.
- standardize an open trace format.

Long term:

- Agents can inspect their own history.
- Teams can build institutional memory around agent behavior.
- Agent incidents become reproducible instead of mysterious.
- The ABB trace becomes a portable artifact across tools, frameworks, and organizations.

The durable opportunity is not just "logs for agents." It is the record layer for agentic work.
