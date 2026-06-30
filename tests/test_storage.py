import contextlib
import importlib.util
import io
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_black_box.cli import (
    _build_doctor_report,
    _compare_investigation_lines,
    _create_agent_kit,
    _create_init_plan,
    _create_support_packet,
    _debug_path_lines,
    _run_provenance_label,
    _run_provenance_lines,
    _run_summary_lines,
    _timeline_item_line,
    main as cli_main,
)
from agent_black_box.api_manifest import api_manifest, format_api_manifest, openapi_spec
from agent_black_box.adapters.langchain import AgentBlackBoxCallbackHandler
from agent_black_box.adapters.langgraph import LangGraphRecorder
from agent_black_box.adapters.tools import ToolCallRecorder
from agent_black_box.handoff import format_handoff_briefing
from agent_black_box.openai import OpenAI, OpenAIMissingCredentialError
from agent_black_box.redaction import redact_payload
from agent_black_box.daemon import HTML_APP
from agent_black_box.diff import compare_runs
from agent_black_box.proxy import proxy_openai_request
from agent_black_box.replay import visual_replay_lines
from agent_black_box.storage import (
    ABBStore,
    compare_evidence_artifacts,
    decode_compare_evidence_content,
    format_compare_briefing,
    format_compare_export,
)


def _load_module_from_path(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class StoreBackedHttpClient:
    base_url = "http://agent-black-box.test"

    def __init__(self, store: ABBStore):
        self.store = store

    def get(self, path: str):
        if path == "/v1/openapi.json":
            return openapi_spec(self.base_url)
        if path.startswith("/v1/runs/") and path.endswith("/timeline"):
            run_id = path.split("/")[3]
            return self.store.get_timeline(run_id)
        raise AssertionError(f"Unexpected GET path: {path}")

    def post(self, path: str, payload):
        if path == "/v1/runs":
            return self.store.create_run(payload)
        if path == "/v1/spans":
            return self.store.start_span(payload)
        if path == "/v1/artifacts":
            return self.store.add_artifact(
                payload.get("run_id"),
                payload.get("span_id"),
                payload.get("kind", "artifact"),
                payload.get("content", ""),
                media_type=payload.get("media_type", "text/plain"),
            )
        if path == "/v1/events":
            return self.store.add_event(payload)
        if path.startswith("/v1/spans/") and path.endswith("/end"):
            span_id = path.split("/")[3]
            return self.store.end_span(
                span_id,
                payload.get("status", "ok"),
                attributes=payload.get("attributes"),
                output_ref=payload.get("output_ref"),
            )
        if path.startswith("/v1/runs/") and path.endswith("/end"):
            run_id = path.split("/")[3]
            return self.store.end_run(run_id, payload.get("status", "ok"))
        raise AssertionError(f"Unexpected POST path: {path}")


class RedactionTests(unittest.TestCase):
    def test_redacts_sensitive_keys_and_text(self):
        payload, hits = redact_payload(
            {
                "api_key": "sk-secret1234567890",
                "message": "Authorization: Bearer abcdefghijklmnop",
            }
        )
        self.assertEqual(payload["api_key"], "[redacted]")
        self.assertIn("Bearer [redacted]", payload["message"])
        self.assertGreaterEqual(len(hits), 2)


class BrowserUiTests(unittest.TestCase):
    def test_embedded_ui_exposes_debugger_surfaces(self):
        for text in [
            "Runs",
            "Fixtures",
            "Diff",
            "Search runs",
            "/v1/search?q=",
            "Add Annotation",
            "Export ABB",
            "Export Handoff",
            "artifactPreview",
            "data-testid",
            "run-list",
            "run-row",
            "run-detail",
            "loadDiff",
            "provenanceBlock",
            "Imported bundle",
            "Remapped import",
            "Agent Kit",
            "agentKitSummary",
            "createAgentKit",
            "agent-kit-output",
            "agent-kit-zip-output",
            "agent-kit-button",
            "agent-kit-status",
            "agent-kit-summary",
            "agent-kit-zip",
            "/v1/agent-kit",
            "Import ABB",
            "importBundle",
            "/v1/bundles/import",
            "on_conflict",
            "Ingest Handoff",
            "ingestHandoff",
            "/v1/handoffs/ingest",
            "Ingest Compare",
            "comparePath",
            "compareName",
            "compareStatus",
            "compare-ingest-path",
            "compare-ingest-name",
            "compare-ingest-button",
            "compare-ingest-status",
            "ingestCompare",
            "/v1/compare/ingest",
            "Linked Runs",
            "linkedRunsPanel",
            "/v1/runs/${runId}/links",
            "usagePills",
            "usage-row",
            "tokens ${escapeHtml(part)}",
            "Run Summary",
            "summaryPanel",
            "Debug Path",
            "debug-path-panel",
            "debugPathPanel",
            "artifactRefButtons",
            "ref-buttons",
            "artifactPreviewBody",
            "Artifact Groups",
            "artifactGroupsPanel",
            "artifactGroupItem",
            "artifact-groups-panel",
            "artifact-group",
            "Span Inspector",
            "span-inspector",
            "spanInspectorPanel",
            "spanInspectorArtifact",
            "span-artifact-row",
            "selectSpanGroup",
            "renderSpanInspector",
            "Inspect Span",
            "Artifact Compare",
            "artifact-compare",
            "Compare Investigation",
            "compareInvestigationPanel",
            "compare-investigation-panel",
            "compareEvidenceButton",
            "compare-evidence-buttons",
            "compare-source-run-button",
            "compare-evidence-packet",
            "compare-evidence-briefing",
            "compare-evidence-left",
            "compare-evidence-right",
            "Open Source Trace",
            "spanArtifactCompare",
            "compare-pane",
            "compare-pair-request-response",
            "compare-copy-markdown",
            "compare-copy-json",
            "compare-download-markdown",
            "compare-download-json",
            "compare-export-status",
            "compare-export-text",
            "comparePairsForGroup",
            "selectComparePair",
            "copySelectedCompare",
            "downloadSelectedCompare",
            "showCompareExportText",
            "hideCompareExportText",
            "delete-run-button",
            "deleteRun",
            "DELETE",
            "delete-run-result",
            "fetchCompareExport",
            "/compare-export",
            "URLSearchParams",
            "loadSelectedSpanCompare",
            "Request vs Response",
            "Input vs Output",
            "suggested_action",
            "Model Calls",
            "Graph Nodes",
            "Tokens",
        ]:
            self.assertIn(text, HTML_APP)


class CliDisplayTests(unittest.TestCase):
    def test_run_provenance_display_helpers(self):
        imported = {"metadata": {"imported_from_bundle": "/tmp/run.abb"}}
        remapped = {
            "metadata": {
                "imported_from_bundle": "/tmp/run.abb",
                "remapped_from_run_id": "run_original",
            }
        }

        self.assertEqual(_run_provenance_label({}), "")
        self.assertEqual(_run_provenance_label(imported), "imported bundle")
        self.assertEqual(_run_provenance_label(remapped), "remapped import")
        self.assertEqual(_run_provenance_lines(imported), ["Imported bundle: /tmp/run.abb"])
        self.assertEqual(
            _run_provenance_lines(remapped),
            ["Remapped from: run_original", "Imported bundle: /tmp/run.abb"],
        )

    def test_doctor_report_is_machine_readable_without_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_key = os.environ.get("OPENAI_API_KEY")
            os.environ["OPENAI_API_KEY"] = "sk-secret-do-not-print"
            try:
                report = _build_doctor_report(Path(tmp), daemon_url=None)
            finally:
                if old_key is None:
                    os.environ.pop("OPENAI_API_KEY", None)
                else:
                    os.environ["OPENAI_API_KEY"] = old_key

            self.assertEqual(report["doctor_version"], "0.1")
            self.assertEqual(report["status"], "ok")
            self.assertTrue(report["environment"]["OPENAI_API_KEY_present"])
            self.assertEqual(report["api"]["service"], "agent-black-box")
            self.assertIn(
                "/v1/runs/{run_id}/compare-evidence",
                [endpoint["path"] for endpoint in report["api"]["endpoints"]],
            )
            self.assertIn("checks", report)
            self.assertIn("next_steps", report)
            self.assertNotIn("sk-secret-do-not-print", json.dumps(report))
            next_steps = " ".join(report["next_steps"])
            self.assertIn("abb endpoints --json", next_steps)
            self.assertIn("examples/http_agent_client.py", next_steps)
            self.assertIn("docs/TROUBLESHOOTING.md", next_steps)
            storage_check = next(check for check in report["checks"] if check["name"] == "storage")
            self.assertEqual(storage_check["status"], "ok")

    def test_api_manifest_lists_agent_integration_routes(self):
        manifest = api_manifest("http://127.0.0.1:9999/")
        endpoints = {(endpoint["method"], endpoint["path"]): endpoint for endpoint in manifest["endpoints"]}

        self.assertEqual(manifest["manifest_version"], "0.1")
        self.assertEqual(manifest["base_url"], "http://127.0.0.1:9999")
        self.assertIn(("GET", "/v1/endpoints"), endpoints)
        self.assertIn(("GET", "/v1/openapi.json"), endpoints)
        self.assertIn(("POST", "/v1/agent-kit"), endpoints)
        self.assertIn(("GET", "/v1/runs/{run_id}/compare-export"), endpoints)
        self.assertIn(("GET", "/v1/runs/{run_id}/compare-evidence"), endpoints)
        self.assertIn(("DELETE", "/v1/runs/{run_id}"), endpoints)
        self.assertIn(("POST", "/v1/compare/ingest"), endpoints)
        self.assertIn(("POST", "/v1/handoffs/ingest"), endpoints)
        self.assertIn("ABB_AUTH_TOKEN", manifest["authentication"]["header"])

        text = format_api_manifest(manifest)
        self.assertIn("DELETE /v1/runs/{run_id}", text)
        self.assertIn("abb delete RUN_ID --yes", text)
        self.assertIn("GET /v1/runs/{run_id}/compare-evidence", text)
        self.assertIn("GET /v1/openapi.json", text)
        self.assertIn("POST /v1/agent-kit", text)
        self.assertIn("abb endpoints --json", text)
        self.assertIn("Compare", text)

    def test_openapi_spec_covers_agent_routes(self):
        spec = openapi_spec("http://127.0.0.1:9999/")
        paths = spec["paths"]

        self.assertEqual(spec["openapi"], "3.1.0")
        self.assertEqual(spec["servers"][0]["url"], "http://127.0.0.1:9999")
        self.assertIn("/v1/openapi.json", paths)
        self.assertIn("/v1/agent-kit", paths)
        self.assertIn("/v1/runs/{run_id}", paths)
        self.assertIn("delete", paths["/v1/runs/{run_id}"])
        self.assertIn("/v1/runs/{run_id}/timeline", paths)
        self.assertIn("/v1/runs/{run_id}/artifacts", paths)
        self.assertIn("/v1/artifacts/{artifact_id}", paths)
        self.assertIn("/v1/runs/{run_id}/compare-export", paths)
        self.assertIn("/v1/runs/{run_id}/compare-evidence", paths)
        self.assertIn("/v1/compare/ingest", paths)
        self.assertIn("/v1/handoffs/ingest", paths)
        self.assertIn("/v1/bundles/import", paths)
        self.assertIn("/proxy/openai/{path}", paths)
        self.assertIn("200", paths["/v1/batch"]["post"]["responses"])
        self.assertIn("200", paths["/v1/bundles/import"]["post"]["responses"])
        self.assertIn("201", paths["/v1/bundles/import"]["post"]["responses"])
        self.assertEqual(paths["/v1/agent-kit"]["post"]["operationId"], "agentKitCreate")
        self.assertEqual(paths["/v1/runs/{run_id}"]["delete"]["operationId"], "runsDelete")
        self.assertEqual(
            paths["/v1/runs/{run_id}/compare-evidence"]["get"]["operationId"],
            "compareEvidence",
        )
        self.assertEqual(
            paths["/v1/compare/ingest"]["post"]["requestBody"]["content"]["application/json"]["schema"]["$ref"],
            "#/components/schemas/JsonObject",
        )
        self.assertEqual(paths["/v1/artifacts/{artifact_id}"]["get"]["parameters"][0]["name"], "artifact_id")
        self.assertIn("BearerAuth", spec["components"]["securitySchemes"])

    def test_http_agent_examples_document_openapi_flow(self):
        python_example = ROOT / "examples" / "http_agent_client.py"
        js_example = ROOT / "examples" / "js-agent-client.mjs"
        prompt_doc = ROOT / "docs" / "AGENT_INTEGRATION_PROMPT.md"
        smoke_script = ROOT / "scripts" / "http-client-smoke.py"

        python_text = python_example.read_text()
        js_text = js_example.read_text()
        prompt_text = prompt_doc.read_text()
        smoke_text = smoke_script.read_text()
        compile(python_text, str(python_example), "exec")
        compile(smoke_text, str(smoke_script), "exec")

        for text in [python_text, js_text, prompt_text]:
            self.assertIn("/v1/openapi.json", text)
            self.assertIn("/v1/runs", text)
            self.assertIn("/v1/spans", text)
            self.assertIn("/v1/artifacts", text)
            self.assertIn("/v1/events", text)
        self.assertIn("urllib", python_text)
        self.assertIn("fetch(", js_text)
        self.assertIn("ABB_AUTH_TOKEN", prompt_text)
        self.assertIn("serve_in_thread", smoke_text)
        self.assertIn("/v1/agent-kit", smoke_text)
        self.assertIn("http-python-example", smoke_text)

    def test_alpha_support_docs_are_discoverable(self):
        troubleshooting = (ROOT / "docs" / "TROUBLESHOOTING.md").read_text()
        limitations = (ROOT / "docs" / "KNOWN_LIMITATIONS.md").read_text()
        intake = (ROOT / "docs" / "DESIGN_PARTNER_INTAKE.md").read_text()
        intake_csv = (ROOT / "docs" / "DESIGN_PARTNER_INTAKE.csv").read_text()
        first_send = (ROOT / "docs" / "DESIGN_PARTNER_FIRST_SEND_PACKET.md").read_text()
        design_partner = (ROOT / "docs" / "DESIGN_PARTNER_HANDOFF.md").read_text()
        outreach = (ROOT / "docs" / "DESIGN_PARTNER_OUTREACH.md").read_text()
        feedback = (ROOT / "docs" / "DESIGN_PARTNER_FEEDBACK_FORM.md").read_text()
        tracker = (ROOT / "docs" / "DESIGN_PARTNER_TRACKER.md").read_text()
        tracker_csv = (ROOT / "docs" / "DESIGN_PARTNER_TRACKER.csv").read_text()
        api_reference = (ROOT / "docs" / "API_REFERENCE.md").read_text()
        readme = (ROOT / "README.md").read_text()
        release_notes = (ROOT / "docs" / "ALPHA_RELEASE_NOTES.md").read_text()

        self.assertIn("KNOWN_LIMITATIONS.md", troubleshooting)
        self.assertIn("TROUBLESHOOTING.md", limitations)
        self.assertIn("Score Fields", intake)
        self.assertIn("Dealbreakers", intake)
        self.assertIn("Selection Rule", intake)
        self.assertIn("scripts/rank-design-partners.py", intake)
        self.assertIn("active_agent_workflow", intake)
        self.assertIn("candidate_id,contact,segment", intake_csv)
        self.assertIn("debugging_pain", intake_csv)
        self.assertIn("privacy_fit", intake_csv)
        self.assertIn("AGENT_FOUNDER_NAME", intake_csv)
        self.assertIn("Partner Selection", first_send)
        self.assertIn("Follow-Up Schedule", first_send)
        self.assertIn("Partner-Level Rubric", first_send)
        self.assertIn("Cohort Decision Rubric", first_send)
        self.assertIn("Support Artifact Order", first_send)
        self.assertIn("DESIGN_PARTNER_INTAKE.csv", first_send)
        self.assertIn("scripts/rank-design-partners.py", first_send)
        self.assertIn("scripts/prepare-design-partner-send.py", first_send)
        self.assertIn(".abb-send/", first_send)
        self.assertIn("dp-001", first_send)
        self.assertIn("ready_next_partner", first_send)
        self.assertIn("ship_next_alpha", first_send)
        self.assertIn("FIRST_USER_WORKFLOW.md", design_partner)
        self.assertIn("TROUBLESHOOTING.md", design_partner)
        self.assertIn("KNOWN_LIMITATIONS.md", design_partner)
        self.assertIn("abb support RUN_ID", design_partner)
        self.assertIn("Privacy Reminder", design_partner)
        self.assertIn("Stop Conditions", design_partner)
        self.assertIn("DESIGN_PARTNER_OUTREACH.md", design_partner)
        self.assertIn("DESIGN_PARTNER_FEEDBACK_FORM.md", design_partner)
        self.assertIn("DESIGN_PARTNER_TRACKER.md", design_partner)
        self.assertIn("DESIGN_PARTNER_INTAKE.md", design_partner)
        self.assertIn("DESIGN_PARTNER_FIRST_SEND_PACKET.md", design_partner)
        self.assertIn("scripts/feedback-summary.py", design_partner)
        self.assertIn("Subject:", outreach)
        self.assertIn("Internal Send Checklist", outreach)
        self.assertIn("DESIGN_PARTNER_INTAKE.md", outreach)
        self.assertIn("scripts/rank-design-partners.py", outreach)
        self.assertIn("DESIGN_PARTNER_FIRST_SEND_PACKET.md", outreach)
        self.assertIn("DESIGN_PARTNER_TRACKER.csv", outreach)
        self.assertIn("scripts/feedback-summary.py", outreach)
        self.assertIn("Workflow Completion", feedback)
        self.assertIn("Privacy And Sharing", feedback)
        self.assertIn("Support Artifacts", feedback)
        self.assertIn("Status Values", tracker)
        self.assertIn("artifact_sha256", tracker)
        self.assertIn("support_packet_path", tracker)
        self.assertIn("next_follow_up_at", tracker)
        self.assertIn("DESIGN_PARTNER_INTAKE.md", tracker)
        self.assertIn("DESIGN_PARTNER_FIRST_SEND_PACKET.md", tracker)
        self.assertIn("partner_id,contact,segment", tracker_csv)
        self.assertIn("AGENT_FOUNDER_NAME", tracker_csv)
        self.assertIn("AGENT_INFRA_NAME", tracker_csv)
        self.assertIn("LOCAL_AUTOMATION_NAME", tracker_csv)
        self.assertIn("SHA256_FROM_RELEASE_MANIFEST", tracker_csv)
        self.assertIn("decision", tracker_csv)
        self.assertIn("DELETE", api_reference)
        self.assertIn("/v1/runs/{run_id}", api_reference)
        self.assertIn("keep_exports", api_reference)
        self.assertIn("TROUBLESHOOTING.md", readme)
        self.assertIn("KNOWN_LIMITATIONS.md", readme)
        self.assertIn("abb delete RUN_ID --yes", readme)
        self.assertIn("DELETE /v1/runs/RUN_ID", readme)
        self.assertIn("DESIGN_PARTNER_INTAKE.md", readme)
        self.assertIn("DESIGN_PARTNER_FIRST_SEND_PACKET.md", readme)
        self.assertIn("DESIGN_PARTNER_HANDOFF.md", readme)
        self.assertIn("DESIGN_PARTNER_OUTREACH.md", readme)
        self.assertIn("DESIGN_PARTNER_FEEDBACK_FORM.md", readme)
        self.assertIn("DESIGN_PARTNER_TRACKER.md", readme)
        self.assertIn("scripts/rank-design-partners.py", readme)
        self.assertIn("scripts/prepare-design-partner-send.py", readme)
        self.assertIn("scripts/feedback-summary.py", readme)
        self.assertIn("DESIGN_PARTNER_INTAKE.md", release_notes)
        self.assertIn("DESIGN_PARTNER_FIRST_SEND_PACKET.md", release_notes)
        self.assertIn("DESIGN_PARTNER_HANDOFF.md", release_notes)
        self.assertIn("DESIGN_PARTNER_OUTREACH.md", release_notes)
        self.assertIn("DESIGN_PARTNER_FEEDBACK_FORM.md", release_notes)
        self.assertIn("DESIGN_PARTNER_TRACKER.md", release_notes)
        self.assertIn("scripts/prepare-design-partner-send.py", release_notes)
        self.assertIn("scripts/feedback-summary.py", release_notes)
        self.assertIn("abb delete RUN_ID --yes", release_notes)
        self.assertIn("TROUBLESHOOTING.md", release_notes)
        self.assertIn("KNOWN_LIMITATIONS.md", release_notes)
        self.assertIn("Daemon Is Not Running", troubleshooting)
        self.assertIn("Localhost Probe Is Blocked", troubleshooting)
        self.assertIn("Auth Token Fails", troubleshooting)
        self.assertIn("Browser UI", limitations)
        self.assertIn("abb delete RUN_ID --yes", limitations)
        self.assertIn("OpenAPI", limitations)

    def test_rank_design_partners_selects_high_signal_candidates(self):
        module = _load_module_from_path(
            "abb_rank_design_partners",
            ROOT / "scripts" / "rank-design-partners.py",
        )
        sample = """candidate_id,contact,segment,source,active_agent_workflow,debugging_pain,terminal_comfort,local_first_need,feedback_availability,wedge_fit,privacy_fit,relationship_strength,notes
cand-001,Founder A,agent founder,warm,3,3,3,2,3,3,3,2,strong founder
cand-002,Infra B,agent infra engineer,warm,3,2,3,3,2,3,3,2,strong infra
cand-003,Automation C,local automation builder,warm,2,2,3,2,2,2,3,3,strong local builder
cand-004,No Terminal,agent founder,warm,3,3,0,3,3,3,3,3,dealbreaker
cand-005,Low Signal,other,cold,1,1,2,1,1,1,2,1,later
"""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            csv_path = tmp_path / "intake.csv"
            markdown_path = tmp_path / "ranking.md"
            json_path = tmp_path / "ranking.json"
            csv_path.write_text(sample, encoding="utf-8")

            candidates = module.read_candidates(csv_path)
            report = module.build_report(candidates)
            self.assertEqual(report["candidate_count"], 5)
            self.assertEqual(report["qualified_count"], 3)
            self.assertEqual([item["candidate_id"] for item in report["selected"]], ["cand-001", "cand-002", "cand-003"])
            self.assertEqual(next(item for item in report["ranked"] if item["candidate_id"] == "cand-004")["status"], "disqualified")
            self.assertIn("terminal_dealbreaker", next(item for item in report["ranked"] if item["candidate_id"] == "cand-004")["flags"])
            self.assertEqual(next(item for item in report["ranked"] if item["candidate_id"] == "cand-005")["status"], "low_signal")

            with contextlib.redirect_stdout(io.StringIO()):
                rc = module.main(
                    [
                        str(csv_path),
                        "--markdown",
                        str(markdown_path),
                        "--json-output",
                        str(json_path),
                    ]
                )
            self.assertEqual(rc, 0)
            markdown = markdown_path.read_text(encoding="utf-8")
            written_json = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertIn("Design Partner Candidate Ranking", markdown)
            self.assertIn("Founder A", markdown)
            self.assertEqual(written_json["selected"][0]["candidate_id"], "cand-001")

    def test_prepare_design_partner_send_uses_release_manifest(self):
        module = _load_module_from_path(
            "abb_prepare_design_partner_send",
            ROOT / "scripts" / "prepare-design-partner-send.py",
        )
        fake_sha = "a" * 64
        manifest = {
            "artifacts": [
                {
                    "kind": "design_partner_kit",
                    "filename": "agent-black-box-0.1.0-design-partner.zip",
                    "sha256": fake_sha,
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "release-manifest.json"
            output_path = tmp_path / "send-queue.md"
            tracker_path = tmp_path / "tracker.csv"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            self.assertEqual(module.next_business_day(module.date(2026, 7, 3)).isoformat(), "2026-07-06")
            artifact = module.load_design_partner_artifact(manifest_path)
            tracker_csv = module.format_tracker_csv(
                artifact,
                module.date(2026, 6, 29),
                "Ahmed",
                mark_sent=True,
            )
            self.assertIn(fake_sha, tracker_csv)
            self.assertIn("2026-06-29,sent", tracker_csv)
            self.assertIn("2026-06-30,Ahmed", tracker_csv)

            with contextlib.redirect_stdout(io.StringIO()):
                rc = module.main(
                    [
                        "--manifest",
                        str(manifest_path),
                        "--date",
                        "2026-06-29",
                        "--owner",
                        "Ahmed",
                        "--output",
                        str(output_path),
                        "--tracker-output",
                        str(tracker_path),
                        "--json",
                    ]
                )
            self.assertEqual(rc, 0)
            markdown = output_path.read_text(encoding="utf-8")
            written_csv = tracker_path.read_text(encoding="utf-8")
            self.assertIn("Design Partner Send Queue", markdown)
            self.assertIn(fake_sha, markdown)
            self.assertIn("AGENT_FOUNDER_NAME", markdown)
            self.assertIn("LOCAL_AUTOMATION_NAME", written_csv)
            self.assertIn("candidate", written_csv)
            self.assertNotIn("SHA256_FROM_RELEASE_MANIFEST", written_csv)

    def test_feedback_summary_parses_design_partner_forms(self):
        module = _load_module_from_path("abb_feedback_summary", ROOT / "scripts" / "feedback-summary.py")
        sample = """# Design Partner Feedback Form

## Reviewer

- Name: Ada
- Date: 2026-06-29
- OS: macOS
- Python version: 3.11
- Did you use the design-partner zip or source checkout?: design-partner zip
- Did you set `ABB_HOME`, `ABB_DAEMON_URL`, or `ABB_AUTH_TOKEN`?: no

## Setup

- Did `sh install.sh` work?: yes
- Did `. .venv/bin/activate` work?: yes
- Did `abb doctor` work?: yes
- Doctor status: warning
- First confusing setup step: daemon warning

Paste any setup error:

```text
Daemon warning was expected but felt scary.
```

## Workflow Completion

- [x] Ran `abb endpoints --json`
- [x] Ran `abb endpoints --openapi`
- [ ] Ran `abb agent-kit --zip`
- [x] Ran `abb init`

## Scores

- Install clarity: 2
- First-run clarity: 4
- `abb show` usefulness: 5
- Debug Path usefulness: 2
- Privacy/local-first clarity: 3

## Most Useful Moment

```text
The debug path made the first warning obvious.
```

## First Confusing Moment

```text
I did not know whether the daemon warning was safe.
```

## Debugging Value

- Did `abb show RUN_ID` tell you what happened?: yes
- Did the Debug Path point to the right thing first?: mostly

## Privacy And Sharing

- Did the local storage boundary feel clear?: yes
- Did you see any secret or sensitive value that should have been redacted?: yes

## Support Artifacts

Support packet path:

```text
.abb/support/run_123-support
```

## Open Notes

```text
Make the warning less alarming.
```
"""
        with tempfile.TemporaryDirectory() as tmp:
            feedback_path = Path(tmp) / "feedback.md"
            json_path = Path(tmp) / "summary.json"
            markdown_path = Path(tmp) / "summary.md"
            feedback_path.write_text(sample)

            report = module.summarize_feedback([feedback_path])
            self.assertEqual(report["form_count"], 1)
            self.assertEqual(report["forms"][0]["reviewer"]["name"], "Ada")
            self.assertEqual(report["forms"][0]["workflow"]["completed"], 3)
            self.assertEqual(report["forms"][0]["workflow"]["total"], 4)
            self.assertIn("low_score:install_clarity=2", report["forms"][0]["flags"])
            self.assertIn("low_score:debug_path_usefulness=2", report["forms"][0]["flags"])
            self.assertIn("possible_redaction_issue", report["forms"][0]["flags"])
            self.assertIn("has_confusion_note", report["forms"][0]["flags"])
            self.assertIn("Daemon warning was expected", report["forms"][0]["notes"]["setup_error"])
            markdown = module.format_markdown_report(report)
            self.assertIn("Design Partner Feedback Summary", markdown)
            self.assertIn("Improve Debug Path", markdown)

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = module.main([str(feedback_path), "--output", str(json_path), "--markdown", str(markdown_path)])
            self.assertEqual(exit_code, 0)
            self.assertTrue(json_path.exists())
            self.assertTrue(markdown_path.exists())
            written = json.loads(json_path.read_text())
            self.assertEqual(written["triage"]["flags"]["possible_redaction_issue"], 1)
            discovered = module.discover_feedback_paths([tmp])
            self.assertEqual(discovered, [feedback_path])

    def test_release_readiness_script_documents_ship_gate(self):
        script = ROOT / "scripts" / "release-readiness.py"
        text = script.read_text()
        compile(text, str(script), "exec")
        readiness = _load_module_from_path("abb_release_readiness", script)

        self.assertIn("scripts/smoke.sh", text)
        self.assertIn("scripts/build-release.py", text)
        self.assertIn("SHIP WITH KNOWN SKIPS", text)
        self.assertIn("DO NOT SHIP", text)

        checks = readiness.collect_static_checks(ROOT)
        self.assertTrue(all(check["status"] == "ok" for check in checks), checks)

        ok_step = readiness.StepResult(
            name="ok",
            status="ok",
            command=["true"],
            returncode=0,
            started_at="2026-01-01T00:00:00Z",
            ended_at="2026-01-01T00:00:00Z",
            duration_seconds=0.0,
            stdout="",
            stderr="",
        )
        error_step = readiness.StepResult(
            name="error",
            status="error",
            command=["false"],
            returncode=1,
            started_at="2026-01-01T00:00:00Z",
            ended_at="2026-01-01T00:00:00Z",
            duration_seconds=0.0,
            stdout="",
            stderr="boom",
        )

        self.assertEqual(readiness.derive_final_status([ok_step], checks, [], []), readiness.SHIP)
        self.assertEqual(
            readiness.derive_final_status([ok_step], checks, ["full smoke: SKIP Node"], []),
            readiness.SHIP_WITH_KNOWN_SKIPS,
        )
        self.assertEqual(readiness.derive_final_status([error_step], checks, [], []), readiness.DO_NOT_SHIP)

    def test_build_release_script_creates_local_artifacts(self):
        module = _load_module_from_path("abb_build_release", ROOT / "scripts" / "build-release.py")
        with tempfile.TemporaryDirectory() as tmp:
            manifest = module.build_release(Path(tmp) / "dist", verify=False)
            self.assertEqual(manifest["package"], "agent-black-box")
            self.assertEqual(manifest["version"], "0.1.0")
            self.assertEqual(manifest["verification"]["status"], "skipped")

            artifacts = {artifact["kind"]: artifact for artifact in manifest["artifacts"]}
            wheel_path = Path(artifacts["wheel"]["path"])
            sdist_path = Path(artifacts["sdist"]["path"])
            partner_path = Path(artifacts["design_partner_kit"]["path"])
            manifest_path = Path(manifest["manifest_path"])
            self.assertTrue(wheel_path.exists(), manifest)
            self.assertTrue(sdist_path.exists(), manifest)
            self.assertTrue(partner_path.exists(), manifest)
            self.assertTrue(manifest_path.exists(), manifest)
            self.assertEqual(artifacts["wheel"]["sha256"], hashlib.sha256(wheel_path.read_bytes()).hexdigest())
            self.assertEqual(artifacts["sdist"]["sha256"], hashlib.sha256(sdist_path.read_bytes()).hexdigest())
            self.assertEqual(
                artifacts["design_partner_kit"]["sha256"],
                hashlib.sha256(partner_path.read_bytes()).hexdigest(),
            )

            with zipfile.ZipFile(wheel_path) as wheel:
                names = set(wheel.namelist())
                self.assertIn("agent_black_box/cli.py", names)
                self.assertIn("agent_black_box-0.1.0.dist-info/METADATA", names)
                self.assertIn("agent_black_box-0.1.0.dist-info/WHEEL", names)
                self.assertIn("agent_black_box-0.1.0.dist-info/entry_points.txt", names)
                self.assertIn("agent_black_box-0.1.0.dist-info/RECORD", names)
                metadata = wheel.read("agent_black_box-0.1.0.dist-info/METADATA").decode("utf-8")
                entry_points = wheel.read("agent_black_box-0.1.0.dist-info/entry_points.txt").decode("utf-8")
            self.assertIn("Name: agent-black-box", metadata)
            self.assertIn("Requires-Python: >=3.9", metadata)
            self.assertIn("abb = agent_black_box.cli:main", entry_points)

            with tarfile.open(sdist_path) as sdist:
                names = set(sdist.getnames())
            self.assertIn("agent-black-box-0.1.0/pyproject.toml", names)
            self.assertIn("agent-black-box-0.1.0/scripts/build-release.py", names)
            self.assertIn("agent-black-box-0.1.0/scripts/prepare-design-partner-send.py", names)
            self.assertIn("agent-black-box-0.1.0/scripts/rank-design-partners.py", names)
            self.assertIn("agent-black-box-0.1.0/src/agent_black_box/cli.py", names)

            with zipfile.ZipFile(partner_path) as kit:
                names = set(kit.namelist())
                self.assertIn(
                    "agent-black-box-0.1.0-design-partner/artifacts/agent_black_box-0.1.0-py3-none-any.whl",
                    names,
                )
                self.assertIn(
                    "agent-black-box-0.1.0-design-partner/artifacts/agent-black-box-0.1.0.tar.gz",
                    names,
                )
                self.assertIn("agent-black-box-0.1.0-design-partner/QUICKSTART.md", names)
                self.assertIn("agent-black-box-0.1.0-design-partner/install.sh", names)
                self.assertIn("agent-black-box-0.1.0-design-partner/docs/FIRST_USER_WORKFLOW.md", names)
                self.assertIn("agent-black-box-0.1.0-design-partner/docs/DESIGN_PARTNER_INTAKE.md", names)
                self.assertIn("agent-black-box-0.1.0-design-partner/docs/DESIGN_PARTNER_INTAKE.csv", names)
                self.assertIn("agent-black-box-0.1.0-design-partner/docs/DESIGN_PARTNER_FIRST_SEND_PACKET.md", names)
                self.assertIn("agent-black-box-0.1.0-design-partner/docs/DESIGN_PARTNER_OUTREACH.md", names)
                self.assertIn("agent-black-box-0.1.0-design-partner/docs/DESIGN_PARTNER_FEEDBACK_FORM.md", names)
                self.assertIn("agent-black-box-0.1.0-design-partner/docs/DESIGN_PARTNER_TRACKER.md", names)
                self.assertIn("agent-black-box-0.1.0-design-partner/docs/DESIGN_PARTNER_TRACKER.csv", names)
                self.assertIn("agent-black-box-0.1.0-design-partner/examples/basic_agent.py", names)
                self.assertIn("agent-black-box-0.1.0-design-partner/scripts/feedback-summary.py", names)
                self.assertTrue(
                    (kit.getinfo("agent-black-box-0.1.0-design-partner/install.sh").external_attr >> 16)
                    & 0o111
                )
                self.assertTrue(
                    (kit.getinfo("agent-black-box-0.1.0-design-partner/scripts/feedback-summary.py").external_attr >> 16)
                    & 0o111
                )

            written_manifest = json.loads(manifest_path.read_text())
            self.assertEqual(written_manifest["artifacts"][0]["sha256"], artifacts["wheel"]["sha256"])
            self.assertEqual(written_manifest["artifacts"][2]["kind"], "design_partner_kit")

    def test_agent_kit_exports_portable_integration_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ABBStore(tmp)
            try:
                kit = _create_agent_kit(
                    store,
                    daemon_url="http://127.0.0.1:43188",
                    output=str(Path(tmp) / "agent-kit"),
                    zip_archive=True,
                )
            finally:
                store.close()

            files = {key: Path(value) for key, value in kit["files"].items()}
            for path in files.values():
                self.assertTrue(path.exists(), path)

            endpoints = json.loads(files["endpoints"].read_text())
            openapi = json.loads(files["openapi"].read_text())
            manifest = json.loads(files["manifest"].read_text())
            self.assertEqual(manifest["agent_kit_version"], "0.1")
            self.assertTrue(Path(manifest["zip_path"]).exists())
            self.assertEqual(
                manifest["sha256"],
                hashlib.sha256(Path(manifest["zip_path"]).read_bytes()).hexdigest(),
            )
            self.assertEqual(endpoints["service"], "agent-black-box")
            self.assertIn("/v1/openapi.json", openapi["paths"])
            self.assertIn("/v1/runs", openapi["paths"])
            self.assertIn("/v1/spans", files["python_client"].read_text())
            self.assertIn("/v1/openapi.json", files["node_client"].read_text())
            self.assertIn("ABB_AUTH_TOKEN", files["env"].read_text())
            self.assertIn("abb support RUN_ID", files["guide"].read_text())
            self.assertIn("sh smoke.sh", files["readme"].read_text())
            with zipfile.ZipFile(manifest["zip_path"]) as archive:
                self.assertEqual(
                    set(archive.namelist()),
                    {
                        "README.txt",
                        "AGENT_BLACK_BOX.md",
                        "endpoints.json",
                        "openapi.json",
                        "python_client.py",
                        "node_client.mjs",
                        "env.example",
                        "smoke.sh",
                        "agent-kit.json",
                    },
                )
                self.assertTrue((archive.getinfo("smoke.sh").external_attr >> 16) & 0o111)
            subprocess.run(["sh", "-n", str(files["smoke"])], check=True)

    def test_agent_kit_cli_zip_json_reports_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous_home = os.environ.get("ABB_HOME")
            os.environ["ABB_HOME"] = str(Path(tmp) / "home")
            output = io.StringIO()
            try:
                with contextlib.redirect_stdout(output):
                    exit_code = cli_main(
                        [
                            "agent-kit",
                            "--output",
                            str(Path(tmp) / "agent-kit"),
                            "--zip",
                            "--json",
                        ]
                    )
            finally:
                if previous_home is None:
                    os.environ.pop("ABB_HOME", None)
                else:
                    os.environ["ABB_HOME"] = previous_home

            self.assertEqual(exit_code, 0)

            payload = json.loads(output.getvalue())
            zip_path = Path(payload["zip_path"])
            self.assertTrue(zip_path.exists(), payload)
            self.assertEqual(payload["archive"]["path"], payload["zip_path"])
            self.assertEqual(payload["sha256"], hashlib.sha256(zip_path.read_bytes()).hexdigest())

    def test_http_python_example_records_against_store_backed_contract(self):
        module = _load_module_from_path("abb_http_agent_client_example", ROOT / "examples" / "http_agent_client.py")
        with tempfile.TemporaryDirectory() as tmp:
            store = ABBStore(tmp)
            try:
                result = module.record_example_run(StoreBackedHttpClient(store))
                timeline = store.get_timeline(result["run_id"])
                artifact_content = store.read_artifact(result["artifact_id"]) or b""
            finally:
                store.close()

        self.assertEqual(timeline["run"]["source"], "http-python-example")
        self.assertEqual(timeline["run"]["status"], "ok")
        self.assertEqual(result["timeline_counts"], {"spans": 1, "events": 1, "artifacts": 1})
        self.assertEqual(timeline["spans"][0]["span_id"], result["span_id"])
        self.assertEqual(timeline["spans"][0]["output_ref"], result["artifact_id"])
        self.assertEqual(timeline["events"][0]["type"], "agent.observation")
        self.assertEqual(timeline["artifacts"][0]["kind"], "agent.note")
        self.assertIn('"client": "python"', artifact_content.decode("utf-8"))
        self.assertEqual(result["dashboard_url"], "http://agent-black-box.test/")

    def test_init_plan_writes_agent_setup_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ABBStore(tmp)
            try:
                plan = _create_init_plan(store, mode="sdk", daemon_url="http://127.0.0.1:43188")
            finally:
                store.close()

            self.assertEqual(plan["init_version"], "0.1")
            self.assertEqual(plan["modes"], ["sdk"])
            self.assertIn("doctor", plan)
            self.assertTrue(any(command["name"] == "api_manifest" for command in plan["commands"]))
            self.assertTrue(any(command["name"] == "openapi_manifest" for command in plan["commands"]))
            self.assertIn("sdk", plan["snippets"])
            self.assertIn("openai_wrapper", plan["snippets"])
            self.assertIn("langchain_callback", plan["snippets"])
            self.assertIn("langgraph_node", plan["snippets"])
            self.assertIn("tool_recorder", plan["snippets"])
            self.assertTrue(Path(plan["files"]["guide"]).exists())
            self.assertTrue(Path(plan["files"]["env"]).exists())
            self.assertTrue(Path(plan["files"]["plan"]).exists())
            written = json.loads(Path(plan["files"]["plan"]).read_text())
            self.assertEqual(written["init_id"], plan["init_id"])
            env_text = Path(plan["files"]["env"]).read_text()
            self.assertIn("ABB_HOME", env_text)
            self.assertIn("OPENAI_API_KEY=...", env_text)

    def test_init_cli_json_writes_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous_home = os.environ.get("ABB_HOME")
            os.environ["ABB_HOME"] = str(Path(tmp) / "home")
            output = io.StringIO()
            try:
                with contextlib.redirect_stdout(output):
                    exit_code = cli_main(["init", "--output", str(Path(tmp) / "init"), "--json"])
            finally:
                if previous_home is None:
                    os.environ.pop("ABB_HOME", None)
                else:
                    os.environ["ABB_HOME"] = previous_home

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertEqual(payload["init_version"], "0.1")
            self.assertTrue(Path(payload["files"]["plan"]).exists())
            env_text = Path(payload["files"]["env"]).read_text()
            self.assertIn("ABB_HOME", env_text)
            self.assertIn("OPENAI_API_KEY=...", env_text)


class StorageTests(unittest.TestCase):
    def test_run_span_event_export_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ABBStore(tmp)
            run = store.create_run({"name": "test run", "source": "unit-test", "tags": ["test"]})
            span = store.start_span({"run_id": run["run_id"], "type": "tool.call", "name": "lookup"})
            store.add_event(
                {
                    "run_id": run["run_id"],
                    "span_id": span["span_id"],
                    "type": "tool.completed",
                    "message": "lookup finished",
                }
            )
            store.end_span(span["span_id"])
            store.end_run(run["run_id"])

            timeline = store.get_timeline(run["run_id"])
            self.assertEqual(timeline["run"]["status"], "ok")
            self.assertEqual(len(timeline["spans"]), 1)
            self.assertEqual(len(timeline["events"]), 1)

            output = store.export_run(run["run_id"], fmt="jsonl")
            rows = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual(rows[0]["type"], "run")
            self.assertEqual(rows[1]["type"], "span")
            self.assertEqual(rows[2]["type"], "event")
            store.close()

    def test_compare_export_builds_agent_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ABBStore(tmp)
            run = store.create_run({"name": "compare run", "source": "unit-test"})
            span = store.start_span({"run_id": run["run_id"], "type": "model.call", "name": "chat"})
            request_artifact = store.add_artifact(
                run["run_id"],
                span["span_id"],
                "model.request",
                json.dumps({"messages": [{"role": "user", "content": "Explain the trace"}]}),
                media_type="application/json",
            )
            response_artifact = store.add_artifact(
                run["run_id"],
                span["span_id"],
                "model.response",
                json.dumps({"choices": [{"message": {"content": "Trace captured."}}]}),
                media_type="application/json",
            )
            store.add_event(
                {
                    "run_id": run["run_id"],
                    "span_id": span["span_id"],
                    "type": "model.completed",
                    "message": "chat completed",
                    "attributes": {
                        "request_ref": request_artifact["artifact_id"],
                        "response_ref": response_artifact["artifact_id"],
                    },
                }
            )
            store.end_span(span["span_id"], output_ref=response_artifact["artifact_id"])
            store.end_run(run["run_id"])

            payload = store.build_compare_export(run["run_id"])
            self.assertEqual(payload["kind"], "agent_black_box.compare_pair")
            self.assertEqual(payload["run_id"], run["run_id"])
            self.assertEqual(payload["span"]["span_id"], span["span_id"])
            self.assertEqual(payload["pair"]["type"], "request-response")
            self.assertEqual(payload["pair"]["label"], "Request vs Response")
            self.assertEqual(payload["artifacts"]["left"]["artifact_id"], request_artifact["artifact_id"])
            self.assertIn("Explain the trace", payload["artifacts"]["left"]["text"])
            self.assertIn("Trace captured.", payload["artifacts"]["right"]["text"])

            markdown = format_compare_export(payload, "markdown")
            self.assertIn("# Agent Black Box Compare Export", markdown)
            self.assertIn("Trace captured.", markdown)
            briefing = format_compare_briefing(payload)
            self.assertIn("Agent Compare Investigation: Request vs Response", briefing)
            self.assertIn("Suggested Next Steps:", briefing)

            json_path = store.export_compare_pair(
                run["run_id"],
                span_id=span["span_id"],
                pair="request-response",
                fmt="json",
            )
            exported = json.loads(json_path.read_text())
            self.assertEqual(exported["pair"]["type"], "request-response")

            with self.assertRaisesRegex(ValueError, "input-output"):
                store.build_compare_export(run["run_id"], span_id=span["span_id"], pair="input-output")

            ingested = store.ingest_compare_packet(payload, name="Investigate compare")
            investigation = store.get_timeline(ingested["run"]["run_id"])
            self.assertEqual(investigation["run"]["name"], "Investigate compare")
            self.assertEqual(investigation["run"]["status"], "running")
            self.assertEqual(investigation["run"]["source"], "compare-ingest")
            self.assertEqual(
                investigation["run"]["metadata"]["source_compare_run_id"],
                run["run_id"],
            )
            self.assertEqual(
                investigation["run"]["metadata"]["source_compare_span_id"],
                span["span_id"],
            )
            self.assertEqual(
                investigation["run"]["metadata"]["source_compare_pair_type"],
                "request-response",
            )
            self.assertEqual(len(investigation["spans"]), 1)
            self.assertEqual(investigation["spans"][0]["type"], "compare.ingest")
            self.assertEqual(
                investigation["spans"][0]["output_ref"],
                ingested["briefing_artifact"]["artifact_id"],
            )
            self.assertEqual(
                {"compare.packet", "compare.briefing", "compare.left", "compare.right"},
                {artifact["kind"] for artifact in investigation["artifacts"]},
            )
            self.assertIn(
                "compare.ingested",
                [event["type"] for event in investigation["events"]],
            )
            left_body = json.loads(store.read_artifact(ingested["left_artifact"]["artifact_id"]).decode("utf-8"))
            self.assertEqual(left_body["source_artifact"]["artifact_id"], request_artifact["artifact_id"])
            self.assertIn("Explain the trace", left_body["text"])
            self.assertEqual(ingested["source_run_id"], run["run_id"])
            self.assertEqual(ingested["source_span_id"], span["span_id"])
            source_links = store.get_run_links(run["run_id"])
            self.assertEqual(source_links["investigations"][0]["run_id"], ingested["run"]["run_id"])
            investigation_links = store.get_run_links(ingested["run"]["run_id"])
            self.assertEqual(investigation_links["source"]["run_id"], run["run_id"])
            compare_lines = _compare_investigation_lines(investigation)
            compare_text = "\n".join(compare_lines)
            self.assertIn("Compare Investigation:", compare_text)
            self.assertIn(f"Source run: {run['run_id']}", compare_text)
            self.assertIn(f"Source span: chat ({span['span_id']})", compare_text)
            self.assertIn("Pair: request-response / Request vs Response", compare_text)
            self.assertIn(f"- packet: {ingested['packet_artifact']['artifact_id']} (compare.packet)", compare_text)
            self.assertIn(f"- briefing: {ingested['briefing_artifact']['artifact_id']} (compare.briefing)", compare_text)
            self.assertIn(f"- left body: {ingested['left_artifact']['artifact_id']} (compare.left)", compare_text)
            self.assertIn(f"- right body: {ingested['right_artifact']['artifact_id']} (compare.right)", compare_text)
            evidence = compare_evidence_artifacts(investigation)
            self.assertEqual(evidence["packet"]["artifact_id"], ingested["packet_artifact"]["artifact_id"])
            self.assertEqual(evidence["left"]["artifact_id"], ingested["left_artifact"]["artifact_id"])
            evidence_summary = store.compare_evidence_summary(ingested["run"]["run_id"])
            self.assertEqual(evidence_summary["source_run_id"], run["run_id"])
            self.assertEqual(evidence_summary["pair_type"], "request-response")
            evidence_result = store.get_compare_evidence(ingested["run"]["run_id"], "left")
            self.assertEqual(evidence_result["part"], "left")
            self.assertIn("Explain the trace", evidence_result["content"])
            raw_evidence_result = store.get_compare_evidence(ingested["run"]["run_id"], "left", raw=True)
            self.assertIn('"side": "left"', raw_evidence_result["content"])
            left_content = store.read_artifact(ingested["left_artifact"]["artifact_id"])
            self.assertIn(
                "Explain the trace",
                decode_compare_evidence_content("left", left_content),
            )
            self.assertIn(
                '"side": "left"',
                decode_compare_evidence_content("left", left_content, raw=True),
            )
            store.close()

    def test_annotations_can_be_listed_and_searched(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ABBStore(tmp)
            run = store.create_run({"name": "annotation search", "source": "unit-test"})
            annotation = store.add_annotation(run["run_id"], "first bad model decision")
            annotations = store.list_annotations(run["run_id"])
            self.assertEqual(annotations[0]["annotation_id"], annotation["annotation_id"])

            matches = store.search("bad model")
            self.assertEqual(matches[0]["run_id"], run["run_id"])
            store.close()

    def test_delete_run_removes_local_trace_files_and_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ABBStore(tmp)
            run = store.create_run({"name": "delete me", "source": "unit-test"})
            span = store.start_span({"run_id": run["run_id"], "type": "tool.call", "name": "write artifact"})
            artifact = store.add_artifact(run["run_id"], span["span_id"], "test.artifact", "delete payload")
            store.add_event(
                {
                    "run_id": run["run_id"],
                    "span_id": span["span_id"],
                    "type": "tool.completed",
                    "message": "done",
                    "attributes": {"artifact_ref": artifact["artifact_id"]},
                }
            )
            store.end_span(span["span_id"], output_ref=artifact["artifact_id"])
            store.end_run(run["run_id"])
            store.add_annotation(run["run_id"], "delete annotation")
            store.create_fixture(run["run_id"], name="delete fixture")
            artifact_path = Path(tmp) / artifact["path"]
            markdown_export = store.export_run(run["run_id"], fmt="markdown")
            handoff_export = store.export_run(run["run_id"], fmt="handoff")
            bundle_export = store.export_bundle(run["run_id"])
            handoff = store.build_handoff_packet(run["run_id"])
            ingested = store.ingest_handoff_packet(handoff, format_handoff_briefing(handoff))
            investigation_id = ingested["run"]["run_id"]
            store.close()

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(cli_main(["--data-dir", tmp, "delete", run["run_id"]]), 2)
            self.assertIn("--yes", stderr.getvalue())

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                rc = cli_main(["--data-dir", tmp, "delete", run["run_id"], "--yes", "--json"])
            self.assertEqual(rc, 0)
            result = json.loads(stdout.getvalue())
            self.assertTrue(result["deleted"])
            self.assertEqual(result["run_id"], run["run_id"])
            self.assertEqual(result["counts"]["runs"], 1)
            self.assertEqual(result["counts"]["spans"], 1)
            self.assertGreaterEqual(result["counts"]["events"], 2)
            self.assertEqual(result["counts"]["artifacts"], 1)
            self.assertEqual(result["counts"]["fixtures"], 1)
            self.assertEqual(result["counts"]["artifact_objects"], 1)
            self.assertEqual(result["counts"]["export_files"], 3)
            self.assertEqual(result["linked_investigations"], [investigation_id])
            self.assertFalse(artifact_path.exists())
            self.assertFalse(markdown_export.exists())
            self.assertFalse(handoff_export.exists())
            self.assertFalse(bundle_export.exists())

            verify = ABBStore(tmp)
            self.assertIsNone(verify.get_run(run["run_id"]))
            self.assertIsNotNone(verify.get_run(investigation_id))
            self.assertEqual(verify.list_fixtures_for_run(run["run_id"]), [])
            verify.close()

    def test_delete_run_can_keep_default_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ABBStore(tmp)
            run = store.create_run({"name": "keep exports", "source": "unit-test"})
            span = store.start_span({"run_id": run["run_id"], "type": "tool.call", "name": "write artifact"})
            artifact = store.add_artifact(run["run_id"], span["span_id"], "test.artifact", "keep export payload")
            store.end_span(span["span_id"], output_ref=artifact["artifact_id"])
            store.end_run(run["run_id"])
            export_path = store.export_run(run["run_id"], fmt="markdown")
            result = store.delete_run(run["run_id"], include_exports=False)
            self.assertEqual(result["counts"]["export_files"], 0)
            self.assertTrue(export_path.exists())
            self.assertIsNone(store.get_run(run["run_id"]))
            store.close()

    def test_bundle_export_import_round_trip(self):
        with tempfile.TemporaryDirectory() as source_tmp, tempfile.TemporaryDirectory() as target_tmp:
            source = ABBStore(source_tmp)
            run = source.create_run({"name": "bundle run", "source": "unit-test"})
            span = source.start_span({"run_id": run["run_id"], "type": "tool.call", "name": "write artifact"})
            artifact = source.add_artifact(
                run["run_id"],
                span["span_id"],
                "test.artifact",
                "portable payload",
                media_type="text/plain",
            )
            source.add_event(
                {
                    "run_id": run["run_id"],
                    "span_id": span["span_id"],
                    "type": "tool.completed",
                    "message": "artifact written",
                    "attributes": {"artifact_ref": artifact["artifact_id"]},
                }
            )
            source.end_span(span["span_id"], output_ref=artifact["artifact_id"])
            source.end_run(run["run_id"])
            source.add_annotation(run["run_id"], "bundle annotation")
            source.create_fixture(run["run_id"], name="bundle fixture")
            live_handoff = source.build_handoff_packet(run["run_id"])
            self.assertEqual(live_handoff["run"]["run_id"], run["run_id"])
            handoff = json.loads(source.export_run(run["run_id"], fmt="handoff").read_text())
            self.assertEqual(handoff["handoff_version"], "0.1")
            self.assertEqual(handoff["run"]["run_id"], run["run_id"])
            self.assertEqual(handoff["counts"]["artifacts"], 1)
            self.assertEqual(handoff["counts"]["annotations"], 1)
            self.assertEqual(handoff["counts"]["fixtures"], 1)
            self.assertEqual(handoff["artifacts"][0]["artifact_id"], artifact["artifact_id"])
            self.assertEqual(handoff["fixtures"][0]["name"], "bundle fixture")
            self.assertIn("bundle annotation", [item["title"] for item in handoff["attention"]])
            self.assertIn("output_ref", handoff["timeline"][0]["refs"])
            self.assertIn("Export the .abb bundle", " ".join(handoff["suggested_next_steps"]))
            briefing = format_handoff_briefing(handoff, timeline_limit=1)
            self.assertIn("Agent Handoff: bundle run", briefing)
            self.assertIn("Attention:", briefing)
            self.assertIn("Artifacts:", briefing)
            self.assertIn("Suggested Next Steps:", briefing)
            ingested = source.ingest_handoff_packet(handoff, briefing, name="Investigate bundle")
            investigation = source.get_timeline(ingested["run"]["run_id"])
            self.assertEqual(investigation["run"]["name"], "Investigate bundle")
            self.assertEqual(investigation["run"]["status"], "running")
            self.assertEqual(investigation["run"]["source"], "handoff-ingest")
            self.assertEqual(
                investigation["run"]["metadata"]["source_handoff_run_id"],
                run["run_id"],
            )
            self.assertEqual(len(investigation["spans"]), 1)
            self.assertEqual(investigation["spans"][0]["type"], "handoff.ingest")
            self.assertEqual(
                investigation["spans"][0]["output_ref"],
                ingested["briefing_artifact"]["artifact_id"],
            )
            self.assertEqual(len(investigation["artifacts"]), 2)
            self.assertIn(
                "handoff.ingested",
                [event["type"] for event in investigation["events"]],
            )
            self.assertIn(
                ingested["packet_artifact"]["artifact_id"],
                [artifact["artifact_id"] for artifact in investigation["artifacts"]],
            )
            self.assertEqual(ingested["source_run_id"], run["run_id"])
            source_links = source.get_run_links(run["run_id"])
            self.assertEqual(source_links["investigations"][0]["run_id"], ingested["run"]["run_id"])
            investigation_links = source.get_run_links(ingested["run"]["run_id"])
            self.assertEqual(investigation_links["source"]["run_id"], run["run_id"])
            support = _create_support_packet(
                source,
                run["run_id"],
                output=str(Path(source_tmp) / "support-packet"),
                include_bundle=True,
                daemon_url=None,
            )
            self.assertTrue(Path(support["paths"]["briefing"]).exists())
            self.assertTrue(Path(support["paths"]["handoff"]).exists())
            self.assertTrue(Path(support["paths"]["timeline"]).exists())
            self.assertTrue(Path(support["paths"]["doctor"]).exists())
            self.assertTrue(Path(support["paths"]["troubleshooting"]).exists())
            self.assertTrue(Path(support["paths"]["known_limitations"]).exists())
            self.assertTrue(Path(support["paths"]["bundle"]).exists())
            support_readme = Path(support["paths"]["readme"]).read_text()
            self.assertIn("When reporting a bug, include:", support_readme)
            self.assertIn("The command you ran and the exact error text.", support_readme)
            self.assertIn(f"abb show {run['run_id']}", support_readme)
            self.assertIn("TROUBLESHOOTING.txt", support_readme)
            self.assertIn("KNOWN_LIMITATIONS.txt", support_readme)
            self.assertIn("docs/TROUBLESHOOTING.md", support_readme)
            self.assertIn("docs/KNOWN_LIMITATIONS.md", support_readme)
            troubleshooting = Path(support["paths"]["troubleshooting"]).read_text()
            known_limitations = Path(support["paths"]["known_limitations"]).read_text()
            self.assertIn("Troubleshooting", troubleshooting)
            self.assertIn("Known Limitations", known_limitations)
            manifest = json.loads(Path(support["paths"]["manifest"]).read_text())
            self.assertTrue(manifest["contains_full_bundle"])
            self.assertFalse(manifest["privacy"]["handoff_embeds_artifact_payloads"])
            self.assertEqual(
                Path(manifest["paths"]["troubleshooting"]).name,
                "TROUBLESHOOTING.txt",
            )
            self.assertEqual(
                Path(manifest["paths"]["known_limitations"]).name,
                "KNOWN_LIMITATIONS.txt",
            )
            bundle = source.export_bundle(run["run_id"])
            source.close()

            target = ABBStore(target_tmp)
            result = target.import_bundle(bundle)
            self.assertEqual(result["run_id"], run["run_id"])
            imported = target.get_timeline(run["run_id"])
            self.assertEqual(imported["run"]["name"], "bundle run")
            self.assertEqual(len(imported["spans"]), 1)
            self.assertEqual(len(imported["events"]), 2)
            self.assertEqual(len(imported["annotations"]), 1)
            self.assertEqual(len(imported["artifacts"]), 1)
            self.assertEqual(target.read_artifact(artifact["artifact_id"]).decode("utf-8"), "portable payload")
            self.assertEqual(target.list_fixtures_for_run(run["run_id"])[0]["name"], "bundle fixture")
            with self.assertRaises(ValueError):
                target.import_bundle(bundle)
            with self.assertRaises(ValueError):
                target.import_bundle(bundle, on_conflict="replace")

            skipped = target.import_bundle(bundle, on_conflict="skip")
            self.assertTrue(skipped["skipped"])
            self.assertEqual(len(target.list_runs()), 1)

            remapped = target.import_bundle(bundle, on_conflict="remap")
            self.assertTrue(remapped["remapped"])
            self.assertEqual(remapped["original_run_id"], run["run_id"])
            self.assertNotEqual(remapped["run_id"], run["run_id"])
            self.assertEqual(remapped["id_map"]["runs"][run["run_id"]], remapped["run_id"])
            self.assertEqual(len(target.list_runs()), 2)

            remapped_timeline = target.get_timeline(remapped["run_id"])
            self.assertEqual(remapped_timeline["run"]["metadata"]["remapped_from_run_id"], run["run_id"])
            self.assertEqual(len(remapped_timeline["spans"]), 1)
            self.assertEqual(len(remapped_timeline["events"]), 2)
            self.assertEqual(len(remapped_timeline["annotations"]), 1)
            remapped_artifacts = remapped_timeline["artifacts"]
            self.assertEqual(len(remapped_artifacts), 1)
            remapped_artifact_id = remapped_artifacts[0]["artifact_id"]
            self.assertNotEqual(remapped_artifact_id, artifact["artifact_id"])
            self.assertEqual(target.read_artifact(remapped_artifact_id).decode("utf-8"), "portable payload")
            self.assertEqual(remapped_timeline["spans"][0]["output_ref"], remapped_artifact_id)
            artifact_refs = [
                event["attributes"].get("artifact_ref")
                for event in remapped_timeline["events"]
                if event["attributes"].get("artifact_ref")
            ]
            self.assertEqual(artifact_refs, [remapped_artifact_id])
            remapped_fixture = target.list_fixtures_for_run(remapped["run_id"])[0]
            self.assertEqual(remapped_fixture["name"], "bundle fixture")
            self.assertEqual(remapped_fixture["fixture"]["run_id"], remapped["run_id"])
            self.assertEqual(
                remapped_fixture["fixture"]["artifacts"][0]["artifact_id"],
                remapped_artifact_id,
            )
            target.close()

    def test_openai_wrapper_records_chat_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ABBStore(tmp)
            captured = {}

            def transport(method, url, headers, body, timeout):
                captured["method"] = method
                captured["url"] = url
                captured["headers"] = headers
                captured["body"] = json.loads(body.decode("utf-8"))
                return (
                    200,
                    {"content-type": "application/json"},
                    (
                        b'{"id":"chatcmpl_test","choices":[{"message":{"content":"hello"}}],'
                        b'"usage":{"prompt_tokens":12,"completion_tokens":7,"total_tokens":19}}'
                    ),
                )

            try:
                client = OpenAI(
                    api_key="test-key",
                    base_url="https://example.test/v1",
                    store=store,
                    transport=transport,
                )
                response = client.chat.completions.create(
                    model="demo-model",
                    messages=[{"role": "user", "content": "Say hello"}],
                )

                self.assertEqual(response.choices[0].message.content, "hello")
                self.assertEqual(response["choices"][0]["message"]["content"], "hello")
                self.assertEqual(response.abb_status_code, 200)
                self.assertEqual(captured["url"], "https://example.test/v1/chat/completions")
                self.assertEqual(captured["headers"]["Authorization"], "Bearer test-key")
                self.assertEqual(captured["body"]["model"], "demo-model")

                timeline = store.get_timeline(response.abb_run_id)
                self.assertEqual(timeline["run"]["source"], "openai-wrapper")
                self.assertEqual(timeline["run"]["status"], "ok")
                self.assertEqual(timeline["spans"][0]["type"], "model.call")
                self.assertEqual(timeline["spans"][0]["attributes"]["resource"], "chat.completions")
                self.assertEqual(
                    timeline["spans"][0]["attributes"]["usage"],
                    {"input_tokens": 12, "output_tokens": 7, "total_tokens": 19},
                )
                self.assertEqual(timeline["summary"]["model_calls"], 1)
                self.assertEqual(timeline["summary"]["usage"]["total_tokens"], 19)
                self.assertEqual(timeline["summary"]["warnings"], 0)
                self.assertEqual(timeline["summary"]["errors"], 0)
                self.assertEqual(timeline["debug_path"][0]["label"], "First decision point")
                self.assertEqual(
                    [ref["ref"] for ref in timeline["debug_path"][0]["artifact_refs"]],
                    ["input_ref", "output_ref"],
                )
                self.assertEqual(len(timeline["artifact_groups"]), 1)
                self.assertEqual(timeline["artifact_groups"][0]["name"], "OpenAI chat.completions demo-model")
                self.assertEqual(
                    [artifact["role"] for artifact in timeline["artifact_groups"][0]["artifacts"]],
                    ["request", "response"],
                )
                self.assertIn("1 model calls", _run_summary_lines(timeline["summary"])[0])
                self.assertIn("tokens in=12, out=7, total=19", "\n".join(_run_summary_lines(timeline["summary"])))
                self.assertEqual(len(timeline["artifacts"]), 2)
                completed = next(event for event in timeline["events"] if event["type"] == "model.completed")
                self.assertEqual(completed["attributes"]["usage"]["total_tokens"], 19)
                self.assertIn("tokens in=12, out=7, total=19", _timeline_item_line(timeline["spans"][0]))
                handoff = store.build_handoff_packet(response.abb_run_id)
                self.assertEqual(handoff["summary"]["usage"]["total_tokens"], 19)
                self.assertEqual(handoff["timeline"][0]["usage"]["total_tokens"], 19)
                self.assertEqual(handoff["debug_path"][0]["artifact_refs"][0]["kind"], "model.request")
                self.assertEqual(handoff["artifact_groups"][0]["artifacts"][0]["role"], "request")
                briefing = format_handoff_briefing(handoff)
                self.assertIn("Run Summary:", briefing)
                self.assertIn("Artifact Groups:", briefing)
                self.assertIn("artifacts: input_ref=", briefing)
                self.assertIn("tokens in=12, out=7, total=19", briefing)
            finally:
                store.close()

    def test_openai_wrapper_records_missing_credential_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_key = os.environ.pop("OPENAI_API_KEY", None)
            store = ABBStore(tmp)
            try:
                client = OpenAI(api_key=None, store=store, transport=lambda *args: self.fail("transport called"))
                with self.assertRaises(OpenAIMissingCredentialError):
                    client.responses.create(model="demo-model", input="hello")

                runs = store.list_runs()
                self.assertEqual(len(runs), 1)
                self.assertEqual(runs[0]["source"], "openai-wrapper")
                self.assertEqual(runs[0]["status"], "error")
                timeline = store.get_timeline(runs[0]["run_id"])
                self.assertEqual(timeline["spans"][0]["status"], "error")
                self.assertIn("model.failed", [event["type"] for event in timeline["events"]])
            finally:
                store.close()
                if old_key is not None:
                    os.environ["OPENAI_API_KEY"] = old_key

    def test_langchain_callback_handler_records_model_and_tool_spans(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ABBStore(tmp)
            try:
                handler = AgentBlackBoxCallbackHandler(store=store, name="langchain demo")
                handler.on_chain_start({"name": "AgentExecutor"}, {"input": "find customer"}, run_id="chain-1")
                handler.on_llm_start(
                    {"name": "ChatOpenAI", "kwargs": {"model_name": "demo-model"}},
                    ["Find the customer record"],
                    run_id="llm-1",
                    parent_run_id="chain-1",
                )
                handler.on_llm_end(
                    {
                        "generations": [[{"text": "Use the lookup tool"}]],
                        "llm_output": {
                            "token_usage": {
                                "prompt_tokens": 10,
                                "completion_tokens": 6,
                                "total_tokens": 16,
                            }
                        },
                    },
                    run_id="llm-1",
                )
                handler.on_tool_start({"name": "lookup_customer"}, "cust_123", run_id="tool-1", parent_run_id="chain-1")
                handler.on_tool_end({"customer": "Ada"}, run_id="tool-1")
                handler.on_chain_end({"output": "done"}, run_id="chain-1")

                self.assertIsNotNone(handler.abb_run_id)
                timeline = store.get_timeline(handler.abb_run_id)
                self.assertEqual(timeline["run"]["source"], "langchain-adapter")
                self.assertEqual(timeline["run"]["status"], "ok")
                self.assertEqual(timeline["summary"]["model_calls"], 1)
                self.assertEqual(timeline["summary"]["tool_calls"], 1)
                self.assertEqual(timeline["summary"]["usage"]["total_tokens"], 16)
                span_types = [span["type"] for span in timeline["spans"]]
                self.assertEqual(span_types, ["chain.run", "model.call", "tool.call"])
                model_span = next(span for span in timeline["spans"] if span["type"] == "model.call")
                tool_span = next(span for span in timeline["spans"] if span["type"] == "tool.call")
                chain_span = next(span for span in timeline["spans"] if span["type"] == "chain.run")
                self.assertEqual(model_span["parent_span_id"], chain_span["span_id"])
                self.assertEqual(tool_span["parent_span_id"], chain_span["span_id"])
                self.assertEqual(model_span["attributes"]["usage"]["total_tokens"], 16)
                self.assertIn("tokens in=10, out=6, total=16", _timeline_item_line(model_span))
                event_types = [event["type"] for event in timeline["events"]]
                self.assertIn("model.completed", event_types)
                self.assertIn("tool.completed", event_types)
                handoff = store.build_handoff_packet(handler.abb_run_id)
                self.assertEqual(handoff["summary"]["usage"]["total_tokens"], 16)
            finally:
                store.close()

    def test_langgraph_recorder_wraps_node_functions(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ABBStore(tmp)

            def load_customer(state):
                return {**state, "customer": {"tier": "pro", "balance": 42}}

            def decide_next(state):
                return {**state, "decision": "manual_review"}

            try:
                recorder = LangGraphRecorder(store=store, name="langgraph demo")
                load = recorder.wrap_node(load_customer)
                decide = recorder.wrap_node(decide_next, name="decide_next")
                state = load({"ticket_id": "tkt_123"})
                state = decide(state)
                recorder.end_run("ok")

                self.assertEqual(state["decision"], "manual_review")
                self.assertIsNotNone(recorder.abb_run_id)
                timeline = store.get_timeline(recorder.abb_run_id)
                self.assertEqual(timeline["run"]["source"], "langgraph-adapter")
                self.assertEqual(timeline["run"]["status"], "ok")
                self.assertEqual([span["type"] for span in timeline["spans"]], ["langgraph.node", "langgraph.node"])
                self.assertEqual(timeline["spans"][0]["name"], "load_customer")
                self.assertEqual(timeline["spans"][1]["name"], "decide_next")
                self.assertEqual(timeline["spans"][0]["attributes"]["framework"], "langgraph")
                self.assertEqual(timeline["summary"]["graph_nodes"], 2)
                self.assertEqual(timeline["summary"]["artifacts"], 4)
                self.assertEqual(timeline["summary"]["errors"], 0)
                self.assertIn("2 graph nodes", "\n".join(_run_summary_lines(timeline["summary"])))
                self.assertEqual(
                    [event["type"] for event in timeline["events"]],
                    ["langgraph.node.completed", "langgraph.node.completed"],
                )
                handoff = store.build_handoff_packet(recorder.abb_run_id)
                self.assertEqual(handoff["summary"]["graph_nodes"], 2)
            finally:
                store.close()

    def test_tool_call_recorder_records_schema_calls_and_mcp_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ABBStore(tmp)

            def lookup_policy(topic: str, amount: int):
                return {"topic": topic, "requires_review": amount > 100}

            try:
                recorder = ToolCallRecorder(store=store, name="tool demo")
                lookup = recorder.wrap_tool(lookup_policy)
                result = lookup("refund", amount=199)
                recorder.record_mcp_tool_call(
                    "knowledge.search",
                    {"query": "refund policy"},
                    {"matches": 1},
                    request_id="req-1",
                    schema={
                        "name": "knowledge.search",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                        },
                    },
                )
                recorder.end_run("ok")

                self.assertTrue(result["requires_review"])
                self.assertIsNotNone(recorder.abb_run_id)
                timeline = store.get_timeline(recorder.abb_run_id)
                self.assertEqual(timeline["run"]["source"], "tool-adapter")
                self.assertEqual(timeline["run"]["status"], "ok")
                self.assertEqual(timeline["summary"]["tool_calls"], 2)
                self.assertEqual(timeline["summary"]["errors"], 0)
                self.assertIn("2 tool calls", "\n".join(_run_summary_lines(timeline["summary"])))
                span_names = [span["name"] for span in timeline["spans"]]
                self.assertEqual(span_names, ["lookup_policy", "knowledge.search"])
                self.assertEqual(timeline["spans"][1]["attributes"]["protocol"], "mcp")
                self.assertEqual(timeline["spans"][1]["attributes"]["request_id"], "req-1")
                schema_events = [event for event in timeline["events"] if event["type"] == "tool.schema.recorded"]
                self.assertEqual(len(schema_events), 2)
                self.assertEqual(
                    [event["type"] for event in timeline["events"] if event["type"].startswith("tool.")],
                    [
                        "tool.schema.recorded",
                        "tool.completed",
                        "tool.schema.recorded",
                        "tool.completed",
                    ],
                )
                self.assertEqual(len([artifact for artifact in timeline["artifacts"] if artifact["kind"] == "tool.schema"]), 2)
                self.assertEqual(len([artifact for artifact in timeline["artifacts"] if artifact["kind"] == "tool.input"]), 2)
                self.assertEqual(len([artifact for artifact in timeline["artifacts"] if artifact["kind"] == "tool.output"]), 2)
                self.assertEqual(
                    [artifact["role"] for artifact in timeline["artifact_groups"][0]["artifacts"]],
                    ["schema", "input", "output"],
                )
                handoff = store.build_handoff_packet(recorder.abb_run_id)
                self.assertEqual(handoff["summary"]["tool_calls"], 2)
                self.assertEqual(handoff["artifact_groups"][0]["artifact_count"], 3)
            finally:
                store.close()

    def test_fixture_replay_and_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ABBStore(tmp)
            run_a = store.create_run({"name": "first", "source": "unit-test"})
            span_a = store.start_span({"run_id": run_a["run_id"], "type": "tool.call", "name": "lookup"})
            store.add_event({"run_id": run_a["run_id"], "span_id": span_a["span_id"], "type": "tool.completed"})
            store.end_span(span_a["span_id"])
            store.end_run(run_a["run_id"])

            run_b = store.create_run({"name": "second", "source": "unit-test"})
            span_b = store.start_span({"run_id": run_b["run_id"], "type": "tool.call", "name": "lookup"})
            store.add_event({"run_id": run_b["run_id"], "span_id": span_b["span_id"], "type": "tool.failed"})
            store.end_span(span_b["span_id"], status="error")
            store.end_run(run_b["run_id"], status="error")

            fixture = store.create_fixture(run_a["run_id"], name="first fixture")
            loaded = store.get_fixture(fixture["fixture_id"])
            self.assertEqual(loaded["name"], "first fixture")
            self.assertIn("Replay fixture: first fixture", "\n".join(visual_replay_lines(loaded)))

            diff = compare_runs(store, run_a["run_id"], run_b["run_id"])
            self.assertIsNotNone(diff["first_divergence"])
            self.assertEqual(diff["event_types"]["tool.completed"]["a"], 1)
            self.assertEqual(diff["event_types"]["tool.failed"]["b"], 1)
            timeline_b = store.get_timeline(run_b["run_id"])
            self.assertEqual(timeline_b["summary"]["first_failure"]["type"], "tool.call")
            self.assertEqual(timeline_b["debug_path"][0]["label"], "Failed tool")
            self.assertEqual(timeline_b["debug_path"][0]["priority"], "critical")
            self.assertIn("Open the tool input/output artifacts", timeline_b["debug_path"][0]["suggested_action"])
            self.assertIn("Debug Path:", "\n".join(_debug_path_lines(timeline_b["debug_path"])))
            handoff = store.build_handoff_packet(run_b["run_id"])
            self.assertEqual(handoff["debug_path"][0]["label"], "Failed tool")
            briefing = format_handoff_briefing(handoff)
            self.assertIn("Debug Path:", briefing)
            self.assertIn("Failed tool", briefing)
            store.close()

    def test_openai_proxy_records_missing_credential_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_key = os.environ.pop("OPENAI_API_KEY", None)
            store = ABBStore(tmp)
            try:
                status, headers, body = proxy_openai_request(
                    store,
                    "POST",
                    "/proxy/openai/v1/chat/completions",
                    "",
                    {"Content-Type": "application/json"},
                    b'{"model":"demo-model","messages":[]}',
                )
                self.assertEqual(status, 401)
                self.assertIn("x-abb-run-id", headers)
                timeline = store.get_timeline(headers["x-abb-run-id"])
                self.assertEqual(timeline["run"]["status"], "error")
                self.assertGreaterEqual(len(timeline["artifacts"]), 2)
                self.assertIn("Missing Authorization", body.decode("utf-8"))
            finally:
                store.close()
                if old_key is not None:
                    os.environ["OPENAI_API_KEY"] = old_key


if __name__ == "__main__":
    unittest.main()
