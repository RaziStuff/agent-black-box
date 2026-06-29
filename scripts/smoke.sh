#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
SMOKE_ID="$(date +%Y%m%d%H%M%S)"
ABB_HOME_DIR="${ABB_SMOKE_HOME:-"$ROOT_DIR/.abb-smoke/$SMOKE_ID"}"

abb() {
  "$PYTHON_BIN" "$ROOT_DIR/abb.py" "$@"
}

printf 'Agent Black Box smoke test\n'
printf 'Root: %s\n' "$ROOT_DIR"
printf 'ABB_HOME: %s\n' "$ABB_HOME_DIR"

mkdir -p "$ABB_HOME_DIR"

export ABB_HOME="$ABB_HOME_DIR"
export PYTHONPYCACHEPREFIX="$ROOT_DIR/.pycache"

cd "$ROOT_DIR"

$PYTHON_BIN -m compileall src examples tests scripts/browser-smoke.py scripts/http-client-smoke.py >/dev/null
$PYTHON_BIN -m unittest discover -s tests
$PYTHON_BIN scripts/browser-smoke.py
$PYTHON_BIN scripts/http-client-smoke.py

abb doctor
abb doctor --json | "$PYTHON_BIN" -c 'import json,sys; report=json.load(sys.stdin); assert report["status"] in ("ok", "warning"), report; assert "checks" in report; assert "api" in report and report["api"]["service"] == "agent-black-box", report; print("Doctor JSON status:", report["status"])'
abb endpoints
abb endpoints --json | "$PYTHON_BIN" -c 'import json,sys; manifest=json.load(sys.stdin); paths=[endpoint["path"] for endpoint in manifest["endpoints"]]; assert "/v1/runs/{run_id}/compare-evidence" in paths, manifest; assert "/v1/endpoints" in paths, manifest; assert "/v1/agent-kit" in paths, manifest; print("Endpoint manifest visible")'
abb endpoints --openapi | "$PYTHON_BIN" -c 'import json,sys; spec=json.load(sys.stdin); paths=spec["paths"]; assert spec["openapi"] == "3.1.0", spec; assert "/v1/openapi.json" in paths, paths; assert "/v1/runs/{run_id}/compare-evidence" in paths, paths; assert "/v1/agent-kit" in paths, paths; print("OpenAPI manifest visible")'
"$PYTHON_BIN" examples/http_agent_client.py --help >/dev/null
[ -f examples/js-agent-client.mjs ]
[ -f docs/AGENT_INTEGRATION_PROMPT.md ]
"$PYTHON_BIN" -c 'from pathlib import Path; texts=[Path("examples/http_agent_client.py").read_text(), Path("examples/js-agent-client.mjs").read_text(), Path("docs/AGENT_INTEGRATION_PROMPT.md").read_text()]; assert all("/v1/openapi.json" in text and "/v1/runs" in text for text in texts); print("HTTP agent examples visible")'
AGENT_KIT_DIR="$(abb agent-kit --output "$ABB_HOME_DIR/agent-kit" --zip --json | "$PYTHON_BIN" -c 'import hashlib,json,pathlib,sys,zipfile; kit=json.load(sys.stdin); files=kit["files"]; assert pathlib.Path(files["openapi"]).exists(), files; assert pathlib.Path(files["endpoints"]).exists(), files; assert pathlib.Path(files["python_client"]).exists(), files; assert pathlib.Path(files["node_client"]).exists(), files; assert pathlib.Path(files["smoke"]).exists(), files; archive=kit["archive"]; zip_path=pathlib.Path(archive["path"]); assert zip_path.exists(), archive; assert kit["sha256"] == hashlib.sha256(zip_path.read_bytes()).hexdigest(), kit; expected={"README.txt","AGENT_BLACK_BOX.md","endpoints.json","openapi.json","python_client.py","node_client.mjs","env.example","smoke.sh","agent-kit.json"}; assert set(zipfile.ZipFile(zip_path).namelist()) == expected, archive; assert kit["api"]["service"] == "agent-black-box", kit; print(pathlib.Path(files["manifest"]).parent)')"
printf 'Created agent kit: %s\n' "$AGENT_KIT_DIR"
sh "$AGENT_KIT_DIR/smoke.sh"
INIT_GUIDE="$(abb init --json | "$PYTHON_BIN" -c 'import json,sys; plan=json.load(sys.stdin); assert plan["init_version"] == "0.1", plan; print(plan["files"]["guide"])')"
printf 'Created init guide: %s\n' "$INIT_GUIDE"
[ -f "$INIT_GUIDE" ]
PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" examples/openai_wrapper_agent.py
OPENAI_RUN_ID="$(abb runs --json | "$PYTHON_BIN" -c 'import json,sys; runs=json.load(sys.stdin); print(next(run["run_id"] for run in runs if run["source"] == "openai-wrapper"))')"
printf 'Recorded OpenAI wrapper run: %s\n' "$OPENAI_RUN_ID"
abb show "$OPENAI_RUN_ID"
abb artifacts "$OPENAI_RUN_ID"
COMPARE_JSON_PATH="$(abb compare-export "$OPENAI_RUN_ID" --format json)"
printf 'Created compare export: %s\n' "$COMPARE_JSON_PATH"
"$PYTHON_BIN" -c 'import json,pathlib,sys; payload=json.loads(pathlib.Path(sys.argv[1]).read_text()); assert payload["kind"] == "agent_black_box.compare_pair", payload; assert payload["pair"]["type"] == "request-response", payload; assert "Captured a local demo response" in payload["artifacts"]["right"]["text"], payload' "$COMPARE_JSON_PATH"
abb compare-export "$OPENAI_RUN_ID" --format markdown
abb compare-export "$OPENAI_RUN_ID" --format json --output - | "$PYTHON_BIN" -c 'import json,sys; payload=json.load(sys.stdin); assert payload["schema_version"] == 1, payload; assert payload["pair"]["label"] == "Request vs Response", payload'
COMPARE_INGESTED_RUN_ID="$(abb compare-ingest "$COMPARE_JSON_PATH" --json | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["run"]["run_id"])')"
printf 'Created compare investigation run: %s\n' "$COMPARE_INGESTED_RUN_ID"
abb show "$COMPARE_INGESTED_RUN_ID"
abb show "$COMPARE_INGESTED_RUN_ID" | "$PYTHON_BIN" -c 'import sys; output=sys.stdin.read(); assert "Compare Investigation:" in output, output; assert "Pair: request-response / Request vs Response" in output, output; assert "compare.packet" in output and "compare.left" in output and "compare.right" in output, output; print("Compare investigation CLI block visible")'
abb compare-evidence "$COMPARE_INGESTED_RUN_ID" | "$PYTHON_BIN" -c 'import sys; output=sys.stdin.read(); assert "Compare Investigation:" in output, output; assert "Use --packet" in output, output; print("Compare evidence summary visible")'
abb compare-evidence "$COMPARE_INGESTED_RUN_ID" --left --output - | "$PYTHON_BIN" -c 'import sys; output=sys.stdin.read(); assert "Explain the trace in one line" in output, output; print("Compare left body visible")'
abb compare-evidence "$COMPARE_INGESTED_RUN_ID" --right --json | "$PYTHON_BIN" -c 'import json,sys; payload=json.load(sys.stdin); assert payload["part"] == "right", payload; assert "Captured a local demo response" in payload["content"], payload; print("Compare right body JSON visible")'
COMPARE_PACKET_COPY="$ABB_HOME_DIR/compare-packet-copy.json"
abb compare-evidence "$COMPARE_INGESTED_RUN_ID" --packet --output "$COMPARE_PACKET_COPY"
"$PYTHON_BIN" -c 'import json,pathlib,sys; payload=json.loads(pathlib.Path(sys.argv[1]).read_text()); assert payload["kind"] == "agent_black_box.compare_pair", payload; print("Compare packet evidence written")' "$COMPARE_PACKET_COPY"
abb show "$OPENAI_RUN_ID" | "$PYTHON_BIN" -c 'import sys; output=sys.stdin.read(); assert "Investigations:" in output, output; print("Compare investigation linked")'
PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" examples/langchain_callback_agent.py
LANGCHAIN_RUN_ID="$(abb runs --json | "$PYTHON_BIN" -c 'import json,sys; runs=json.load(sys.stdin); print(next(run["run_id"] for run in runs if run["source"] == "langchain-adapter"))')"
printf 'Recorded LangChain callback run: %s\n' "$LANGCHAIN_RUN_ID"
abb show "$LANGCHAIN_RUN_ID"
PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" examples/langgraph_node_agent.py
LANGGRAPH_RUN_ID="$(abb runs --json | "$PYTHON_BIN" -c 'import json,sys; runs=json.load(sys.stdin); print(next(run["run_id"] for run in runs if run["source"] == "langgraph-adapter"))')"
printf 'Recorded LangGraph node run: %s\n' "$LANGGRAPH_RUN_ID"
abb show "$LANGGRAPH_RUN_ID"
PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" examples/tool_call_agent.py
TOOL_RUN_ID="$(abb runs --json | "$PYTHON_BIN" -c 'import json,sys; runs=json.load(sys.stdin); print(next(run["run_id"] for run in runs if run["source"] == "tool-adapter"))')"
printf 'Recorded tool call run: %s\n' "$TOOL_RUN_ID"
abb show "$TOOL_RUN_ID"
abb record --name smoke-demo -- "$PYTHON_BIN" examples/basic_agent.py

RUN_ID="$(abb runs --json | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)[0]["run_id"])')"
printf 'Recorded smoke run: %s\n' "$RUN_ID"

abb annotate "$RUN_ID" "Smoke annotation"
abb search Smoke

FIXTURE_ID="$(abb fixture create "$RUN_ID" --name smoke-fixture)"
printf 'Created smoke fixture: %s\n' "$FIXTURE_ID"

abb replay "$FIXTURE_ID"
abb diff "$RUN_ID" "$RUN_ID"
abb export "$RUN_ID" --format jsonl
abb export "$RUN_ID" --format markdown
HANDOFF_PATH="$(abb export "$RUN_ID" --format handoff)"
printf 'Created handoff packet: %s\n' "$HANDOFF_PATH"
abb handoff "$RUN_ID"
abb handoff --file "$HANDOFF_PATH"
INGESTED_RUN_ID="$(abb handoff --ingest "$HANDOFF_PATH" --json | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["run"]["run_id"])')"
printf 'Created investigation run: %s\n' "$INGESTED_RUN_ID"
abb show "$INGESTED_RUN_ID"
abb show "$RUN_ID" | "$PYTHON_BIN" -c 'import sys; data=sys.stdin.read(); assert "Investigations:" in data, data; print("Linked investigation visible")'
SUPPORT_DIR="$(abb support "$RUN_ID" --json | "$PYTHON_BIN" -c 'import json,sys; print(json.load(sys.stdin)["directory"])')"
printf 'Created support packet: %s\n' "$SUPPORT_DIR"
[ -f "$SUPPORT_DIR/briefing.txt" ]
[ -f "$SUPPORT_DIR/doctor.json" ]
[ -f "$SUPPORT_DIR/TROUBLESHOOTING.txt" ]
[ -f "$SUPPORT_DIR/KNOWN_LIMITATIONS.txt" ]
BUNDLE_PATH="$(abb bundle export "$RUN_ID")"
IMPORT_HOME="$ABB_HOME_DIR-import"
mkdir -p "$IMPORT_HOME"
SMOKE_HOME="$ABB_HOME"
ABB_HOME="$IMPORT_HOME"
export ABB_HOME
abb bundle import "$BUNDLE_PATH"
abb bundle import "$BUNDLE_PATH" --on-conflict skip
abb bundle import "$BUNDLE_PATH" --on-conflict remap
IMPORT_RUN_COUNT="$(abb runs --json | "$PYTHON_BIN" -c 'import json,sys; print(len(json.load(sys.stdin)))')"
[ "$IMPORT_RUN_COUNT" -eq 2 ]
abb show "$RUN_ID"
ABB_HOME="$SMOKE_HOME"
export ABB_HOME
abb artifacts "$RUN_ID"

printf '\nSmoke test complete.\n'
