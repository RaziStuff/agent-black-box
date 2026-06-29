# Agent Black Box Integration Prompt

Use this prompt when another local agent needs to record its work into Agent
Black Box without depending on the Python SDK.

```text
You have access to Agent Black Box, a local-first flight recorder for agent work.
Your goal is to record important steps, artifacts, and decisions locally while
you work, then produce a compact handoff or compare packet if another agent needs
to continue debugging.

Discovery:
- If a generated kit is available, read these files first:
  AGENT_BLACK_BOX.md
  openapi.json
  endpoints.json
- Prefer the OpenAPI contract when you can call tools or generate an HTTP client:
  abb endpoints --openapi
- Use the compact manifest when you only need a route list:
  abb endpoints --json
- If the daemon is running, the same contracts are available at:
  GET http://127.0.0.1:43188/v1/openapi.json
  GET http://127.0.0.1:43188/v1/endpoints

Authentication:
- Most local dev runs need no token.
- If ABB_AUTH_TOKEN is set, send:
  Authorization: Bearer <ABB_AUTH_TOKEN>

Record a run through HTTP:
1. POST /v1/runs with name, source, tags, and metadata.
2. POST /v1/spans for each model call, tool call, graph node, or major step.
3. POST /v1/artifacts for request bodies, responses, tool outputs, notes, and evidence.
4. POST /v1/events for important observations and decisions.
5. POST /v1/spans/{span_id}/end with status and optional output_ref.
6. POST /v1/runs/{run_id}/end when the task is done.

Inspect and hand off:
- GET /v1/runs/{run_id}/timeline to inspect the run.
- Use abb show RUN_ID for a human-readable debug path.
- Use abb export RUN_ID --format handoff for a compact packet.
- Use abb handoff RUN_ID for a readable briefing.
- Use abb support RUN_ID when a reviewer needs a local support folder.

Compare workflow:
- Use abb compare-export RUN_ID --format json when one request/response or
  input/output pair should be reviewed by another agent.
- Use abb compare-ingest PATH to create a focused investigation from that pair.
- Use abb compare-evidence COMPARE_INVESTIGATION_ID --left or --right to read
  evidence without copying artifact IDs.

Privacy:
- Data stays in the configured local store.
- Handoff JSON is compact and does not embed full artifact payloads.
- .abb bundles include local artifact payloads and should be treated as full
  trace archives.
- Obvious API keys, bearer tokens, passwords, and private keys are redacted, but
  inspect sensitive artifacts before sharing them.
```

Copy-paste examples:

```bash
abb agent-kit
abb start
python3 examples/http_agent_client.py
node examples/js-agent-client.mjs
```

After either client runs:

```bash
abb runs
abb show RUN_ID
abb handoff RUN_ID
```
