# Agent Black Box First User Workflow

This is the happy path for a local alpha user. It proves the full loop: install,
record, inspect, hand off, ingest, and continue an investigation locally.

## 1. Install Locally

If you received `agent-black-box-0.1.0-design-partner.zip`, unzip it and run:

```bash
sh install.sh
. .venv/bin/activate
abb doctor
abb endpoints --json
abb endpoints --openapi
abb agent-kit --zip
abb init
python3 examples/openai_wrapper_agent.py
python3 examples/langchain_callback_agent.py
python3 examples/langgraph_node_agent.py
python3 examples/tool_call_agent.py
```

If you are using the source checkout instead, run:

```bash
scripts/dev-install.sh
. .venv/bin/activate
abb doctor
abb endpoints --json
abb endpoints --openapi
abb agent-kit --zip
abb init
python3 examples/openai_wrapper_agent.py
python3 examples/langchain_callback_agent.py
python3 examples/langgraph_node_agent.py
python3 examples/tool_call_agent.py
```

Expected result:

- `abb doctor` reports storage as ok.
- `abb init` writes a setup guide under `.abb/init/`.
- The OpenAI wrapper demo records a local `openai-wrapper` run without an API key.
- The LangChain callback demo records a local `langchain-adapter` run without installing LangChain.
- The LangGraph node demo records a local `langgraph-adapter` run without installing LangGraph.
- The tool call demo records a local `tool-adapter` run with schema, input, and output artifacts.
- `abb show` for the wrapper run shows model token usage.
- The daemon may report as not running until you start it.
- `abb doctor --json` is available if a reviewer or agent needs a structured setup report.
- `abb endpoints --json` lists the local HTTP routes another agent or non-Python client can call.
- `abb endpoints --openapi` prints an OpenAPI 3.1 document for client generators and agent tools.
- `abb agent-kit --zip` writes a portable onboarding folder and checksum zip under `.abb/agent-kit/` for another local agent.
- In the design-partner kit, `release-manifest.json` lists SHA-256 checksums for the wheel and source tarball.
- `docs/TROUBLESHOOTING.md` and `docs/KNOWN_LIMITATIONS.md` are available when a local alpha path fails or feels out of scope.
- No account, cloud project, or API key is required for the demo workflow.

## 2. Record The Demo Agent

```bash
abb record --name first-debug-run -- python3 examples/basic_agent.py
abb runs
```

Copy the newest `run_...` value from `abb runs`.

```bash
RUN_ID=run_replace_me
abb show "$RUN_ID"
```

Expected result:

- The run status is `ok`.
- The summary lists counts for model/tool calls, graph nodes, warnings, errors, artifacts, and usage when present.
- The debug path lists the first warning, failure, annotation, or decision point worth inspecting.
- The timeline includes a shell command span.
- The transcript artifact is available.

## 3. Add Debugging Context

```bash
abb annotate "$RUN_ID" "First review note: check warning and transcript"
abb annotations "$RUN_ID"
abb artifacts "$RUN_ID"
```

Expected result:

- The annotation appears in `abb show`.
- The artifact list includes a `terminal.transcript` artifact.

## 4. Create Replay And Diff Evidence

```bash
FIXTURE_ID="$(abb fixture create "$RUN_ID" --name first-regression)"
abb replay "$FIXTURE_ID"
abb diff "$RUN_ID" "$RUN_ID"
```

Expected result:

- Replay prints the run as a numbered sequence.
- Diff reports no normalized divergence when comparing a run to itself.

## 5. Export And Ingest A Compare Pair

```bash
OPENAI_RUN_ID="$(abb runs --json | python3 -c 'import json,sys; runs=json.load(sys.stdin); print(next(run["run_id"] for run in runs if run["source"] == "openai-wrapper"))')"
COMPARE_PATH="$(abb compare-export "$OPENAI_RUN_ID" --format json)"
COMPARE_INVESTIGATION_ID="$(abb compare-ingest "$COMPARE_PATH" --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["run"]["run_id"])')"
abb show "$COMPARE_INVESTIGATION_ID"
abb compare-evidence "$COMPARE_INVESTIGATION_ID" --left
abb compare-evidence "$COMPARE_INVESTIGATION_ID" --right --json
abb show "$OPENAI_RUN_ID"
```

Expected result:

- The compare packet is written as `.abb/exports/RUN_ID.SPAN_ID.PAIR.compare.json`.
- The compare investigation run source is `compare-ingest`.
- The investigation has `compare.packet`, `compare.briefing`, `compare.left`, and `compare.right` artifacts.
- `abb show "$COMPARE_INVESTIGATION_ID"` prints a `Compare Investigation` block with source run/span, pair, and evidence artifact IDs.
- `abb compare-evidence "$COMPARE_INVESTIGATION_ID" --left` prints the original left body without requiring a copied artifact ID.
- The daemon endpoint `/v1/runs/COMPARE_INVESTIGATION_ID/compare-evidence?part=left&format=text` serves the same evidence for HTTP clients.
- The source run lists the linked investigation.

## 6. Export A Handoff Packet

```bash
HANDOFF_PATH="$(abb export "$RUN_ID" --format handoff)"
abb handoff "$RUN_ID"
abb handoff --file "$HANDOFF_PATH"
```

Expected result:

- The handoff packet is written as `.abb/exports/RUN_ID.handoff.json`.
- The briefing calls out debug path items, attention items, artifacts, fixtures, and next steps.
- The packet is compact JSON and does not embed artifact payloads.

## 7. Ingest The Handoff As A New Investigation

```bash
INVESTIGATION_ID="$(abb handoff --ingest "$HANDOFF_PATH" --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["run"]["run_id"])')"
abb show "$INVESTIGATION_ID"
abb show "$RUN_ID"
```

Expected result:

- The investigation run source is `handoff-ingest`.
- The investigation run points back to the source trace.
- The source run lists the linked investigation.
- The investigation has `handoff.packet` and `handoff.briefing` artifacts.

## 8. Use The Browser Dashboard

```bash
abb start
```

Open:

```text
http://127.0.0.1:43188
```

Verify:

- The Runs view loads the recorded run and investigation run.
- The selected source run shows a `Linked Runs` panel.
- The investigation run shows its source trace.
- Debug-path artifact buttons open referenced artifacts in the preview panel.
- Artifact groups show related blobs for each model/tool/node call.
- The span inspector opens the selected call and lists its related artifacts together.
- The span inspector compares paired artifacts side by side when the selected call has them.
- Copy or download the selected compare pair as Markdown or JSON from the inspector.
- `/v1/endpoints` returns the same endpoint manifest as `abb endpoints --json`.
- `/v1/openapi.json` returns the same OpenAPI document as `abb endpoints --openapi`.
- `abb compare-export "$OPENAI_RUN_ID" --format json` prints or writes the same pair payload for another agent.
- `abb compare-ingest PATH` creates a focused compare investigation with the packet, briefing, and left/right evidence bodies attached.
- Compare investigation runs show a focused panel with source trace, packet, briefing, left body, and right body buttons.
- `Ingest Compare`, `Export Handoff`, `Import ABB`, and `Ingest Handoff` are visible in the Runs surface.

In another terminal, try the dependency-free HTTP clients:

```bash
python3 examples/http_agent_client.py
node examples/js-agent-client.mjs
```

Expected result:

- Each client discovers `/v1/openapi.json`.
- Each client creates a run, span, event, and artifact through HTTP.
- Each client prints the created run ID so you can open it with `abb show RUN_ID`.

Stop the daemon with `Ctrl-C` in the terminal running `abb start`.

## 9. Export A Portable Bundle

```bash
BUNDLE_PATH="$(abb bundle export "$RUN_ID")"
abb --data-dir /tmp/abb-first-import bundle import "$BUNDLE_PATH"
abb --data-dir /tmp/abb-first-import bundle import "$BUNDLE_PATH" --on-conflict skip
abb --data-dir /tmp/abb-first-import bundle import "$BUNDLE_PATH" --on-conflict remap
```

Expected result:

- First import creates the run in the target local store.
- `skip` exits successfully without duplicating the run.
- `remap` creates a new independent run with rewritten IDs.

## 10. Privacy Check

Before sharing anything:

- Share `.handoff.json` when another agent only needs a compact briefing.
- Share `.abb` when another agent needs the full portable trace and artifact payloads.
- Use `abb support "$RUN_ID"` to gather a briefing, handoff packet, timeline metadata, and doctor report.
- Add `--include-bundle` only when the reviewer can receive the full trace archive and artifact payloads.
- Inspect artifacts with `abb artifact ARTIFACT_ID` before sharing.
- Remember that local data lives in `.abb/` by default unless `ABB_HOME` or `--data-dir` is set.
- Use `docs/TROUBLESHOOTING.md` for common local setup and daemon issues.
- Use `docs/KNOWN_LIMITATIONS.md` to confirm whether a missing feature is outside the current alpha scope.

## Fast Verification

The automated version of this workflow is:

```bash
scripts/smoke.sh
python3 scripts/http-client-smoke.py --required
```

For a reviewer-friendly version that leaves an isolated demo store and summary file:

```bash
scripts/alpha-demo.sh
```

## Feedback

After the workflow, fill out [DESIGN_PARTNER_FEEDBACK_FORM.md](DESIGN_PARTNER_FEEDBACK_FORM.md).
If something failed, include the smallest support artifact you can share, such as
`abb doctor --json`, `abb support RUN_ID`, or `.abb/exports/RUN_ID.handoff.json`.
