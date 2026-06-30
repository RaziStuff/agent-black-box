# Agent Black Box Local API Reference

Agent Black Box exposes a localhost HTTP API from `abb start`. The default base
URL is:

```text
http://127.0.0.1:43188
```

The same endpoint map is available as machine-readable JSON:

```bash
abb endpoints --json
abb endpoints --openapi
curl http://127.0.0.1:43188/v1/endpoints
curl http://127.0.0.1:43188/v1/openapi.json
```

Use the compact manifest when an agent wants a simple route list. Use the
OpenAPI 3.1 document when a client generator, tool planner, or HTTP workspace
expects a standard API description.

Dependency-free client examples:

```bash
python3 examples/http_agent_client.py
node examples/js-agent-client.mjs
```

Both examples discover `/v1/openapi.json`, record one run over HTTP, and print
the created run, span, and artifact IDs. `docs/AGENT_INTEGRATION_PROMPT.md` is a
short prompt another agent can read before using the local API.

If the daemon is started with `abb start --token TOKEN` or `ABB_AUTH_TOKEN`, send:

```text
Authorization: Bearer TOKEN
```

## Discovery

| Method | Path | Use |
| --- | --- | --- |
| `GET` | `/` | Open the browser dashboard. |
| `GET` | `/health` | Check daemon reachability and local data directory. |
| `GET` | `/v1/endpoints` | Read the machine-readable API manifest. |
| `GET` | `/v1/openapi.json` | Read the OpenAPI 3.1 document. |
| `POST` | `/v1/agent-kit` | Create a portable integration kit with API contracts and HTTP clients. |

Agent kit body:

```json
{
  "output": ".abb/agent-kit",
  "force": true,
  "zip": true,
  "zip_output": ".abb/agent-kit/agent-kit.zip"
}
```

The response matches `abb agent-kit --json` and includes paths for
`AGENT_BLACK_BOX.md`, `endpoints.json`, `openapi.json`, Python and Node clients,
`env.example`, `smoke.sh`, and `agent-kit.json`. When `zip` is true, the response
also includes `zip_path`, `sha256`, and an `archive` block for `agent-kit.zip`.

## Runs

| Method | Path | CLI equivalent | Use |
| --- | --- | --- | --- |
| `GET` | `/v1/runs?limit=50` | `abb runs --json` | List recent runs. |
| `POST` | `/v1/runs` | `abb record --name NAME -- COMMAND` | Create a run from an SDK, adapter, or non-Python client. |
| `GET` | `/v1/runs/{run_id}` | `abb show RUN_ID --json` | Read one run record. |
| `GET` | `/v1/runs/{run_id}/timeline` | `abb show RUN_ID --json` | Read spans, events, artifacts, annotations, fixtures, and links. |
| `GET` | `/v1/runs/{run_id}/links` | `abb show RUN_ID` | Read source and investigation links. |
| `POST` | `/v1/runs/{run_id}/end` | SDK recorder end | Mark a run complete. |
| `POST` | `/v1/runs/{run_id}/export` | `abb export RUN_ID --format FORMAT` | Export JSONL, Markdown, handoff JSON, or a portable `.abb` bundle. |
| `DELETE` | `/v1/runs/{run_id}?keep_exports=false` | `abb delete RUN_ID --yes` | Delete a run, local artifacts, fixtures, and default export files. |

Minimal run create body:

```json
{
  "name": "agent run",
  "source": "my-agent",
  "tags": ["local"],
  "metadata": {}
}
```

Delete returns a summary of removed trace rows, artifact object files, export
files, and linked investigation runs that were kept. Set `keep_exports=true` to
remove only the live trace and object files while preserving default exports.

## Capture

| Method | Path | Use |
| --- | --- | --- |
| `POST` | `/v1/spans` | Start a span for a model call, tool call, graph node, or agent step. |
| `POST` | `/v1/spans/{span_id}/end` | End a span and attach final attributes or an output artifact ref. |
| `POST` | `/v1/events` | Append an event to a run or span. |
| `POST` | `/v1/artifacts` | Store a local artifact body and receive an artifact ref. |
| `POST` | `/v1/batch` | Create runs, spans, events, and annotations in one local request. |

Typical span body:

```json
{
  "run_id": "run_...",
  "name": "call model",
  "type": "model.call",
  "attributes": {
    "model": "gpt-4.1-mini"
  }
}
```

Typical artifact body:

```json
{
  "run_id": "run_...",
  "span_id": "span_...",
  "kind": "model.request",
  "media_type": "application/json",
  "content": "{\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}"
}
```

## Artifacts And Annotations

| Method | Path | CLI equivalent | Use |
| --- | --- | --- | --- |
| `GET` | `/v1/runs/{run_id}/artifacts` | `abb artifacts RUN_ID --json` | List artifact metadata for a run. |
| `GET` | `/v1/artifacts/{artifact_id}` | `abb artifact ARTIFACT_ID` | Read one artifact payload. |
| `GET` | `/v1/runs/{run_id}/annotations` | `abb annotations RUN_ID --json` | List annotations for a run. |
| `POST` | `/v1/annotations` | `abb annotate RUN_ID MESSAGE` | Add an annotation to a run or span. |

## Search, Diff, And Fixtures

| Method | Path | CLI equivalent | Use |
| --- | --- | --- | --- |
| `GET` | `/v1/search?q=refund` | `abb search refund --json` | Search runs and timeline text. |
| `GET` | `/v1/diff?run_a=RUN_A&run_b=RUN_B` | `abb diff RUN_A RUN_B --json` | Compare two runs. |
| `GET` | `/v1/fixtures?limit=50` | `abb fixture list --json` | List replay fixtures. |
| `POST` | `/v1/runs/{run_id}/fixture` | `abb fixture create RUN_ID --name NAME` | Create a replay fixture. |
| `GET` | `/v1/fixtures/{fixture_id}` | `abb fixture show FIXTURE_ID --json` | Read one replay fixture. |

## Compare Workflows

Compare endpoints are the main agent-to-agent debugging wedge. A source agent can
export one natural pair, such as model request vs response. A second agent can
ingest that packet as a focused investigation and read the packet, briefing, and
left/right evidence bodies without copying artifact IDs.

| Method | Path | CLI equivalent | Use |
| --- | --- | --- | --- |
| `GET` | `/v1/runs/{run_id}/compare-export?pair=request-response&format=json` | `abb compare-export RUN_ID --format json` | Export one comparable artifact pair. |
| `POST` | `/v1/compare/ingest` | `abb compare-ingest PATH --json` | Create a focused compare investigation from a compare JSON file. |
| `GET` | `/v1/runs/{run_id}/compare-evidence` | `abb compare-evidence RUN_ID` | Read the evidence summary for a compare investigation. |
| `GET` | `/v1/runs/{run_id}/compare-evidence?part=left&format=text` | `abb compare-evidence RUN_ID --left` | Read unwrapped left evidence text. |
| `GET` | `/v1/runs/{run_id}/compare-evidence?part=right` | `abb compare-evidence RUN_ID --right --json` | Read right evidence as JSON. |

Supported compare export query values:

- `pair`: `auto`, `request-response`, or `input-output`.
- `format`: `json`, `markdown`, or `md`.
- `span` or `span_id`: optional span selector.

Supported compare evidence query values:

- `part`: `packet`, `briefing`, `left`, or `right`.
- `format`: `json`, `text`, or `txt`.
- `raw=1`: return the stored evidence wrapper instead of unwrapped left/right body text.

Compare ingest body:

```json
{
  "path": ".abb/exports/run_...span_...request-response.compare.json",
  "name": "Investigate model response"
}
```

## Handoffs And Bundles

| Method | Path | CLI equivalent | Use |
| --- | --- | --- | --- |
| `POST` | `/v1/handoffs/ingest` | `abb handoff --ingest PATH --json` | Create a follow-up investigation from a handoff JSON file. |
| `POST` | `/v1/bundles/import` | `abb bundle import PATH --on-conflict remap` | Import a portable `.abb` trace archive. |

Handoff ingest body:

```json
{
  "path": ".abb/exports/run_....handoff.json",
  "name": "Continue investigation"
}
```

Bundle import body:

```json
{
  "path": ".abb/exports/run_....abb",
  "on_conflict": "remap"
}
```

`on_conflict` can be `fail`, `skip`, or `remap`.

## OpenAI-Compatible Proxy

| Method | Path | Use |
| --- | --- | --- |
| `POST` | `/proxy/openai/{path}` | Forward an OpenAI-compatible request to the configured upstream while recording local trace artifacts. |

Start the daemon, then point an OpenAI-compatible client at:

```bash
export OPENAI_BASE_URL=http://127.0.0.1:43188/proxy/openai
```

The proxy uses the incoming `Authorization` header or `OPENAI_API_KEY` for the
upstream. Trace data remains in the configured local Agent Black Box store.
