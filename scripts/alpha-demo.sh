#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
DEMO_ID="$(date +%Y%m%d%H%M%S)"
ABB_HOME_DIR="${ABB_DEMO_HOME:-"$ROOT_DIR/.abb-demo/$DEMO_ID"}"
IMPORT_HOME="$ABB_HOME_DIR-import"
SUMMARY_PATH="$ABB_HOME_DIR/alpha-demo-summary.txt"

abb() {
  "$PYTHON_BIN" "$ROOT_DIR/abb.py" "$@"
}

print_step() {
  printf '\n== %s ==\n' "$1"
}

mkdir -p "$ABB_HOME_DIR" "$IMPORT_HOME"

export ABB_HOME="$ABB_HOME_DIR"
export PYTHONPYCACHEPREFIX="$ROOT_DIR/.pycache"

cd "$ROOT_DIR"

print_step "Agent Black Box alpha demo"
printf 'Root: %s\n' "$ROOT_DIR"
printf 'Demo store: %s\n' "$ABB_HOME_DIR"
printf 'Import store: %s\n' "$IMPORT_HOME"

print_step "Doctor"
abb doctor
abb endpoints --json | "$PYTHON_BIN" -c 'import json,sys; manifest=json.load(sys.stdin); paths=[endpoint["path"] for endpoint in manifest["endpoints"]]; assert "/v1/endpoints" in paths and "/v1/runs/{run_id}/compare-evidence" in paths, manifest; print("Endpoint manifest routes:", len(paths))'
abb endpoints --openapi | "$PYTHON_BIN" -c 'import json,sys; spec=json.load(sys.stdin); paths=spec["paths"]; assert spec["openapi"] == "3.1.0" and "/v1/openapi.json" in paths and "/v1/runs/{run_id}/compare-evidence" in paths, spec; print("OpenAPI paths:", len(paths))'
"$PYTHON_BIN" examples/http_agent_client.py --help >/dev/null
"$PYTHON_BIN" -c 'from pathlib import Path; assert Path("examples/js-agent-client.mjs").exists(); assert Path("docs/AGENT_INTEGRATION_PROMPT.md").exists(); print("HTTP client examples ready")'
"$PYTHON_BIN" scripts/http-client-smoke.py
INIT_GUIDE="$(abb init --json | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["files"]["guide"])')"
printf 'Init guide: %s\n' "$INIT_GUIDE"

print_step "OpenAI wrapper demo"
PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" examples/openai_wrapper_agent.py
OPENAI_RUN_ID="$(abb runs --json | "$PYTHON_BIN" -c 'import json,sys; runs=json.load(sys.stdin); print(next(run["run_id"] for run in runs if run["source"] == "openai-wrapper"))')"
printf 'OpenAI wrapper run: %s\n' "$OPENAI_RUN_ID"

print_step "Compare packet"
COMPARE_PATH="$(abb compare-export "$OPENAI_RUN_ID" --format json)"
printf 'Compare packet: %s\n' "$COMPARE_PATH"
COMPARE_INVESTIGATION_ID="$(abb compare-ingest "$COMPARE_PATH" --json | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["run"]["run_id"])')"
printf 'Compare investigation run: %s\n' "$COMPARE_INVESTIGATION_ID"
abb show "$COMPARE_INVESTIGATION_ID"

print_step "LangChain callback demo"
PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" examples/langchain_callback_agent.py
LANGCHAIN_RUN_ID="$(abb runs --json | "$PYTHON_BIN" -c 'import json,sys; runs=json.load(sys.stdin); print(next(run["run_id"] for run in runs if run["source"] == "langchain-adapter"))')"
printf 'LangChain callback run: %s\n' "$LANGCHAIN_RUN_ID"

print_step "LangGraph node demo"
PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" examples/langgraph_node_agent.py
LANGGRAPH_RUN_ID="$(abb runs --json | "$PYTHON_BIN" -c 'import json,sys; runs=json.load(sys.stdin); print(next(run["run_id"] for run in runs if run["source"] == "langgraph-adapter"))')"
printf 'LangGraph node run: %s\n' "$LANGGRAPH_RUN_ID"

print_step "Tool call demo"
PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" examples/tool_call_agent.py
TOOL_RUN_ID="$(abb runs --json | "$PYTHON_BIN" -c 'import json,sys; runs=json.load(sys.stdin); print(next(run["run_id"] for run in runs if run["source"] == "tool-adapter"))')"
printf 'Tool call run: %s\n' "$TOOL_RUN_ID"

print_step "Record demo agent"
abb record --name alpha-demo -- "$PYTHON_BIN" examples/basic_agent.py
RUN_ID="$(abb runs --json | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)[0]["run_id"])')"
printf 'Run ID: %s\n' "$RUN_ID"

print_step "Annotate and inspect"
abb annotate "$RUN_ID" "Alpha demo review note"
abb show "$RUN_ID"
abb artifacts "$RUN_ID"

print_step "Fixture and diff"
FIXTURE_ID="$(abb fixture create "$RUN_ID" --name alpha-demo-fixture)"
printf 'Fixture ID: %s\n' "$FIXTURE_ID"
abb replay "$FIXTURE_ID"
abb diff "$RUN_ID" "$RUN_ID"

print_step "Handoff"
HANDOFF_PATH="$(abb export "$RUN_ID" --format handoff)"
printf 'Handoff packet: %s\n' "$HANDOFF_PATH"
abb handoff "$RUN_ID"
INVESTIGATION_ID="$(abb handoff --ingest "$HANDOFF_PATH" --json | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["run"]["run_id"])')"
printf 'Investigation run: %s\n' "$INVESTIGATION_ID"
abb show "$INVESTIGATION_ID"

print_step "Portable bundle"
BUNDLE_PATH="$(abb bundle export "$RUN_ID")"
printf 'Bundle: %s\n' "$BUNDLE_PATH"
SUPPORT_DIR="$(abb support "$RUN_ID" --include-bundle --json | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["directory"])')"
printf 'Support packet: %s\n' "$SUPPORT_DIR"
ABB_HOME="$IMPORT_HOME"
export ABB_HOME
abb bundle import "$BUNDLE_PATH"
abb bundle import "$BUNDLE_PATH" --on-conflict skip
abb bundle import "$BUNDLE_PATH" --on-conflict remap
IMPORT_RUN_COUNT="$(abb runs --json | "$PYTHON_BIN" -c 'import json,sys; print(len(json.load(sys.stdin)))')"
printf 'Import store run count: %s\n' "$IMPORT_RUN_COUNT"

ABB_HOME="$ABB_HOME_DIR"
export ABB_HOME

cat > "$SUMMARY_PATH" <<EOF
Agent Black Box alpha demo

Root: $ROOT_DIR
Demo store: $ABB_HOME_DIR
Import store: $IMPORT_HOME
Dashboard URL: http://127.0.0.1:43188

Run ID: $RUN_ID
OpenAI wrapper run ID: $OPENAI_RUN_ID
Compare investigation run ID: $COMPARE_INVESTIGATION_ID
LangChain callback run ID: $LANGCHAIN_RUN_ID
LangGraph node run ID: $LANGGRAPH_RUN_ID
Tool call run ID: $TOOL_RUN_ID
Investigation run ID: $INVESTIGATION_ID
Fixture ID: $FIXTURE_ID
Init guide: $INIT_GUIDE
Compare packet: $COMPARE_PATH
Handoff packet: $HANDOFF_PATH
Bundle: $BUNDLE_PATH
Support packet: $SUPPORT_DIR

Open dashboard:
  ABB_HOME="$ABB_HOME_DIR" "$PYTHON_BIN" "$ROOT_DIR/abb.py" start

Inspect from CLI:
  ABB_HOME="$ABB_HOME_DIR" "$PYTHON_BIN" "$ROOT_DIR/abb.py" endpoints --json
  ABB_HOME="$ABB_HOME_DIR" "$PYTHON_BIN" "$ROOT_DIR/abb.py" endpoints --openapi
  ABB_HOME="$ABB_HOME_DIR" "$PYTHON_BIN" "$ROOT_DIR/examples/http_agent_client.py"
  ABB_HOME="$ABB_HOME_DIR" node "$ROOT_DIR/examples/js-agent-client.mjs"
  ABB_HOME="$ABB_HOME_DIR" "$PYTHON_BIN" "$ROOT_DIR/abb.py" show "$RUN_ID"
  ABB_HOME="$ABB_HOME_DIR" "$PYTHON_BIN" "$ROOT_DIR/abb.py" show "$OPENAI_RUN_ID"
  ABB_HOME="$ABB_HOME_DIR" "$PYTHON_BIN" "$ROOT_DIR/abb.py" show "$COMPARE_INVESTIGATION_ID"
  ABB_HOME="$ABB_HOME_DIR" "$PYTHON_BIN" "$ROOT_DIR/abb.py" compare-evidence "$COMPARE_INVESTIGATION_ID" --left
  ABB_HOME="$ABB_HOME_DIR" "$PYTHON_BIN" "$ROOT_DIR/abb.py" compare-evidence "$COMPARE_INVESTIGATION_ID" --right --json
  ABB_HOME="$ABB_HOME_DIR" "$PYTHON_BIN" "$ROOT_DIR/abb.py" show "$LANGCHAIN_RUN_ID"
  ABB_HOME="$ABB_HOME_DIR" "$PYTHON_BIN" "$ROOT_DIR/abb.py" show "$LANGGRAPH_RUN_ID"
  ABB_HOME="$ABB_HOME_DIR" "$PYTHON_BIN" "$ROOT_DIR/abb.py" show "$TOOL_RUN_ID"
  ABB_HOME="$ABB_HOME_DIR" "$PYTHON_BIN" "$ROOT_DIR/abb.py" show "$INVESTIGATION_ID"
  ABB_HOME="$ABB_HOME_DIR" "$PYTHON_BIN" "$ROOT_DIR/abb.py" compare-export "$OPENAI_RUN_ID" --format markdown --output -
  ABB_HOME="$ABB_HOME_DIR" "$PYTHON_BIN" "$ROOT_DIR/abb.py" handoff "$RUN_ID"
EOF

print_step "Reviewer summary"
cat "$SUMMARY_PATH"

printf '\nAlpha demo complete.\n'
