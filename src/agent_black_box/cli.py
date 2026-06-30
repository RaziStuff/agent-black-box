from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional
from urllib import request
from urllib.error import HTTPError, URLError
import webbrowser
import zipfile

from .agent_kit import create_agent_kit
from .api_manifest import api_manifest, format_api_manifest, openapi_spec
from .daemon import serve, serve_in_thread
from .diff import compare_runs, format_diff
from .handoff import format_handoff_briefing
from . import __version__
from .ids import new_id, utc_now
from .replay import visual_replay_lines
from .storage import (
    ABBStore,
    COMPARE_EVIDENCE_PARTS,
    COMPARE_PAIR_TYPES,
    default_data_dir,
    format_compare_briefing,
    format_compare_export,
)
from .usage import format_usage, usage_from_attributes


DEFAULT_URL = "http://127.0.0.1:43188"
REPO_ROOT = Path(__file__).resolve().parents[2]


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "handler"):
        parser.print_help()
        return 2
    return args.handler(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="abb", description="Agent Black Box local-first recorder")
    parser.add_argument("--data-dir", default=None, help="Agent Black Box data directory")

    sub = parser.add_subparsers(dest="command")

    p_start = sub.add_parser("start", help="Start the local daemon and browser UI")
    p_start.add_argument("--host", default="127.0.0.1")
    p_start.add_argument("--port", default=43188, type=int)
    p_start.add_argument("--token", default=os.environ.get("ABB_AUTH_TOKEN"))
    p_start.set_defaults(handler=cmd_start)

    p_status = sub.add_parser("status", help="Check the local daemon")
    p_status.add_argument("--url", default=os.environ.get("ABB_DAEMON_URL", DEFAULT_URL))
    p_status.set_defaults(handler=cmd_status)

    p_endpoints = sub.add_parser("endpoints", help="Print the local daemon API manifest")
    p_endpoints.add_argument("--url", default=os.environ.get("ABB_DAEMON_URL", DEFAULT_URL))
    endpoints_format = p_endpoints.add_mutually_exclusive_group()
    endpoints_format.add_argument("--json", action="store_true", help="Print a machine-readable endpoint manifest")
    endpoints_format.add_argument("--openapi", action="store_true", help="Print the OpenAPI 3.1 document")
    p_endpoints.set_defaults(handler=cmd_endpoints)

    p_doctor = sub.add_parser("doctor", help="Check local setup")
    p_doctor.add_argument("--url", default=os.environ.get("ABB_DAEMON_URL", DEFAULT_URL))
    p_doctor.add_argument("--json", action="store_true", help="Print a machine-readable readiness report")
    p_doctor.add_argument("--strict", action="store_true", help="Return non-zero when warnings are present")
    p_doctor.set_defaults(handler=cmd_doctor)

    p_init = sub.add_parser("init", help="Create a local setup guide for an agent project")
    p_init.add_argument("--mode", choices=["all", "cli", "sdk", "proxy"], default="all")
    p_init.add_argument("--output", default=None, help="Output directory for generated init files")
    p_init.add_argument("--force", action="store_true", help="Overwrite files in an explicit output directory")
    p_init.add_argument("--json", action="store_true", help="Print a machine-readable init plan")
    p_init.add_argument("--url", default=os.environ.get("ABB_DAEMON_URL", DEFAULT_URL))
    p_init.set_defaults(handler=cmd_init)

    p_agent_kit = sub.add_parser("agent-kit", help="Create a portable integration kit for local agents")
    p_agent_kit.add_argument("--output", default=None, help="Output directory for the generated kit")
    p_agent_kit.add_argument("--force", action="store_true", help="Overwrite an existing kit output directory")
    p_agent_kit.add_argument("--zip", dest="zip_archive", action="store_true", help="Also write an agent-kit.zip archive")
    p_agent_kit.add_argument("--zip-output", default=None, help="Output path for --zip")
    p_agent_kit.add_argument("--json", action="store_true", help="Print a machine-readable kit manifest")
    p_agent_kit.add_argument("--url", default=os.environ.get("ABB_DAEMON_URL", DEFAULT_URL))
    p_agent_kit.set_defaults(handler=cmd_agent_kit)

    p_record = sub.add_parser("record", help="Record a command as an Agent Black Box run")
    p_record.add_argument("--name", default=None)
    p_record.add_argument("--tag", dest="tags", action="append", default=[])
    p_record.add_argument("command", nargs=argparse.REMAINDER)
    p_record.set_defaults(handler=cmd_record)

    p_runs = sub.add_parser("runs", help="List recorded runs")
    p_runs.add_argument("--limit", default=20, type=int)
    p_runs.add_argument("--json", action="store_true")
    p_runs.set_defaults(handler=cmd_runs)

    p_show = sub.add_parser("show", help="Show one run timeline")
    p_show.add_argument("run_id")
    p_show.add_argument("--json", action="store_true")
    p_show.set_defaults(handler=cmd_show)

    p_delete = sub.add_parser("delete", help="Delete a run, its local artifacts, fixtures, and default exports")
    p_delete.add_argument("run_id")
    p_delete.add_argument("--yes", action="store_true", help="Confirm deletion without an interactive prompt")
    p_delete.add_argument("--keep-exports", action="store_true", help="Keep default files under .abb/exports for this run")
    p_delete.add_argument("--json", action="store_true", help="Print a machine-readable deletion summary")
    p_delete.set_defaults(handler=cmd_delete)

    p_search = sub.add_parser("search", help="Search recorded runs")
    p_search.add_argument("query")
    p_search.add_argument("--json", action="store_true")
    p_search.set_defaults(handler=cmd_search)

    p_annotate = sub.add_parser("annotate", help="Add an annotation to a run")
    p_annotate.add_argument("run_id")
    p_annotate.add_argument("message")
    p_annotate.add_argument("--span-id", default=None)
    p_annotate.set_defaults(handler=cmd_annotate)

    p_annotations = sub.add_parser("annotations", help="List annotations for a run")
    p_annotations.add_argument("run_id")
    p_annotations.add_argument("--json", action="store_true")
    p_annotations.set_defaults(handler=cmd_annotations)

    p_diff = sub.add_parser("diff", help="Compare two recorded runs")
    p_diff.add_argument("run_a")
    p_diff.add_argument("run_b")
    p_diff.add_argument("--json", action="store_true")
    p_diff.set_defaults(handler=cmd_diff)

    p_artifacts = sub.add_parser("artifacts", help="List artifacts for a run")
    p_artifacts.add_argument("run_id")
    p_artifacts.add_argument("--json", action="store_true")
    p_artifacts.set_defaults(handler=cmd_artifacts)

    p_artifact = sub.add_parser("artifact", help="Read one artifact")
    p_artifact.add_argument("artifact_id")
    p_artifact.add_argument("--output", default=None)
    p_artifact.set_defaults(handler=cmd_artifact)

    p_fixture = sub.add_parser("fixture", help="Create and inspect replay fixtures")
    fixture_sub = p_fixture.add_subparsers(dest="fixture_command")
    p_fixture_create = fixture_sub.add_parser("create", help="Create a replay fixture from a run")
    p_fixture_create.add_argument("run_id")
    p_fixture_create.add_argument("--name", default=None)
    p_fixture_create.set_defaults(handler=cmd_fixture_create)
    p_fixture_list = fixture_sub.add_parser("list", help="List replay fixtures")
    p_fixture_list.add_argument("--limit", default=20, type=int)
    p_fixture_list.add_argument("--json", action="store_true")
    p_fixture_list.set_defaults(handler=cmd_fixture_list)
    p_fixture_show = fixture_sub.add_parser("show", help="Show one replay fixture")
    p_fixture_show.add_argument("fixture_id")
    p_fixture_show.add_argument("--json", action="store_true")
    p_fixture_show.set_defaults(handler=cmd_fixture_show)

    p_replay = sub.add_parser("replay", help="Visually replay a fixture in the terminal")
    p_replay.add_argument("fixture_id")
    p_replay.set_defaults(handler=cmd_replay)

    p_export = sub.add_parser("export", help="Export a run")
    p_export.add_argument("run_id")
    p_export.add_argument("--format", choices=["jsonl", "markdown", "md", "handoff"], default="jsonl")
    p_export.add_argument("--output", default=None)
    p_export.set_defaults(handler=cmd_export)

    p_compare_export = sub.add_parser("compare-export", help="Export one comparable artifact pair for an agent")
    p_compare_export.add_argument("run_id")
    p_compare_export.add_argument("--span", dest="span_id", default=None, help="Span ID to export from")
    p_compare_export.add_argument(
        "--pair",
        choices=["auto", *COMPARE_PAIR_TYPES],
        default="auto",
        help="Artifact pair to export",
    )
    p_compare_export.add_argument("--format", choices=["markdown", "md", "json"], default="markdown")
    p_compare_export.add_argument("--output", default=None, help="Output path, or '-' for stdout")
    p_compare_export.set_defaults(handler=cmd_compare_export)

    p_compare_ingest = sub.add_parser("compare-ingest", help="Create an investigation run from a compare-pair JSON")
    p_compare_ingest.add_argument("path", help="Path to an agent_black_box.compare_pair JSON export")
    p_compare_ingest.add_argument("--name", default=None, help="Name for the investigation run")
    p_compare_ingest.add_argument("--json", action="store_true", help="Print JSON output")
    p_compare_ingest.set_defaults(handler=cmd_compare_ingest)

    p_compare_evidence = sub.add_parser("compare-evidence", help="Read evidence from a compare investigation")
    p_compare_evidence.add_argument("run_id", help="Compare investigation run ID")
    evidence_part = p_compare_evidence.add_mutually_exclusive_group()
    evidence_part.add_argument("--part", choices=list(COMPARE_EVIDENCE_PARTS), default=None)
    evidence_part.add_argument("--packet", dest="part", action="store_const", const="packet", help="Print compare packet JSON")
    evidence_part.add_argument("--briefing", dest="part", action="store_const", const="briefing", help="Print compare briefing")
    evidence_part.add_argument("--left", dest="part", action="store_const", const="left", help="Print left evidence body")
    evidence_part.add_argument("--right", dest="part", action="store_const", const="right", help="Print right evidence body")
    p_compare_evidence.add_argument("--raw", action="store_true", help="Print raw artifact content instead of unwrapped body text")
    p_compare_evidence.add_argument("--json", action="store_true", help="Print JSON output")
    p_compare_evidence.add_argument("--output", default=None, help="Write selected evidence to a path, or '-' for stdout")
    p_compare_evidence.set_defaults(handler=cmd_compare_evidence)

    p_handoff = sub.add_parser("handoff", help="Print an agent-ready handoff briefing")
    p_handoff.add_argument("run_id", nargs="?")
    p_handoff.add_argument("--file", dest="file", default=None, help="Read an existing .handoff.json packet")
    p_handoff.add_argument("--ingest", dest="ingest_file", default=None, help="Create an investigation run from a .handoff.json packet")
    p_handoff.add_argument("--name", default=None, help="Name for an ingested investigation run")
    p_handoff.add_argument("--json", action="store_true", help="Print JSON output")
    p_handoff.add_argument("--timeline-limit", default=12, type=int)
    p_handoff.set_defaults(handler=cmd_handoff)

    p_support = sub.add_parser("support", help="Create a local support packet for a run")
    p_support.add_argument("run_id")
    p_support.add_argument("--output", default=None, help="Output directory for the support packet")
    p_support.add_argument("--include-bundle", action="store_true", help="Include the full .abb trace archive")
    p_support.add_argument("--json", action="store_true")
    p_support.add_argument("--url", default=os.environ.get("ABB_DAEMON_URL", DEFAULT_URL))
    p_support.set_defaults(handler=cmd_support)

    p_bundle = sub.add_parser("bundle", help="Export and import portable .abb bundles")
    bundle_sub = p_bundle.add_subparsers(dest="bundle_command")
    p_bundle_export = bundle_sub.add_parser("export", help="Export a run as a portable .abb bundle")
    p_bundle_export.add_argument("run_id")
    p_bundle_export.add_argument("--output", default=None)
    p_bundle_export.set_defaults(handler=cmd_bundle_export)
    p_bundle_import = bundle_sub.add_parser("import", help="Import a portable .abb bundle")
    p_bundle_import.add_argument("path")
    p_bundle_import.add_argument(
        "--on-conflict",
        choices=["fail", "skip", "remap"],
        default="fail",
        help="How to handle a bundle whose run ID already exists",
    )
    p_bundle_import.set_defaults(handler=cmd_bundle_import)

    p_open = sub.add_parser("open", help="Open the local browser UI")
    p_open.add_argument("--url", default=os.environ.get("ABB_DAEMON_URL", DEFAULT_URL))
    p_open.set_defaults(handler=cmd_open)

    return parser


def cmd_start(args: argparse.Namespace) -> int:
    serve(data_dir=args.data_dir, host=args.host, port=args.port, auth_token=args.token)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    payload = http_get(args.url + "/health")
    if not payload:
        print("Agent Black Box daemon is not reachable")
        return 1
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def cmd_endpoints(args: argparse.Namespace) -> int:
    if args.openapi:
        print(json.dumps(openapi_spec(args.url), indent=2, sort_keys=True))
        return 0
    manifest = api_manifest(args.url)
    if args.json:
        print(json.dumps(manifest, indent=2, sort_keys=True))
    else:
        print(format_api_manifest(manifest), end="")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir).expanduser() if args.data_dir else default_data_dir()
    report = _build_doctor_report(data_dir, args.url)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_doctor_report(report)
    if report["status"] == "error":
        return 1
    if args.strict and report["status"] != "ok":
        return 1
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir).expanduser() if args.data_dir else default_data_dir()
    try:
        store = ABBStore(data_dir)
        try:
            plan = _create_init_plan(
                store,
                mode=args.mode,
                daemon_url=args.url,
                output=args.output,
                force=args.force,
            )
        finally:
            store.close()
    except (OSError, ValueError) as exc:
        print(f"Init failed: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    _print_init_plan(plan)
    return 0


def cmd_agent_kit(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir).expanduser() if args.data_dir else default_data_dir()
    try:
        store = ABBStore(data_dir)
        try:
            kit = _create_agent_kit(
                store,
                daemon_url=args.url,
                output=args.output,
                force=args.force,
                zip_archive=args.zip_archive,
                zip_output=args.zip_output,
            )
        finally:
            store.close()
    except (OSError, ValueError) as exc:
        print(f"Agent kit failed: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(kit, indent=2, sort_keys=True))
        return 0
    _print_agent_kit(kit)
    return 0


def _create_init_plan(
    store: ABBStore,
    mode: str = "all",
    daemon_url: str = DEFAULT_URL,
    output: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    modes = ["cli", "sdk", "proxy"] if mode == "all" else [mode]
    init_id = new_id("init")
    output_dir = Path(output) if output else store.root / "init" / init_id
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "guide": output_dir / "AGENT_BLACK_BOX_INIT.md",
        "env": output_dir / "agent-black-box.env",
        "plan": output_dir / "agent-black-box-init.json",
    }
    if output and not force:
        existing = [path for path in paths.values() if path.exists()]
        if existing:
            raise ValueError(
                "init output already exists; pass --force or choose a new --output: "
                + ", ".join(str(path) for path in existing)
            )

    doctor = _build_doctor_report(store.root, daemon_url, store=store)
    snippets = _init_snippets(store.root, daemon_url)
    commands = _init_commands(modes, daemon_url)
    plan = {
        "init_version": "0.1",
        "init_id": init_id,
        "created_at": utc_now(),
        "project": {
            "name": Path.cwd().name,
            "cwd": os.getcwd(),
        },
        "mode": mode,
        "modes": modes,
        "data_dir": str(store.root.resolve()),
        "daemon_url": daemon_url,
        "commands": commands,
        "snippets": {
            key: snippets[key]
            for key in [
                "cli",
                "sdk",
                "openai_wrapper",
                "langchain_callback",
                "langgraph_node",
                "tool_recorder",
                "proxy",
                "support",
            ]
            if key in snippets
        },
        "files": {key: str(path) for key, path in paths.items()},
        "doctor": doctor,
        "next_steps": _init_next_steps(modes),
    }
    paths["guide"].write_text(_init_markdown(plan), encoding="utf-8")
    paths["env"].write_text(_init_env_text(store.root, daemon_url), encoding="utf-8")
    _write_json(paths["plan"], plan)
    return plan


def _init_commands(modes: List[str], daemon_url: str) -> List[Dict[str, str]]:
    commands = [
        {
            "name": "verify",
            "purpose": "Check local readiness before recording a real agent run.",
            "command": "abb doctor",
        },
        {
            "name": "verify_json",
            "purpose": "Give another agent or script a structured setup report.",
            "command": "abb doctor --json",
        },
        {
            "name": "api_manifest",
            "purpose": "List local daemon endpoints for agents and non-Python clients.",
            "command": "abb endpoints --json",
        },
        {
            "name": "openapi_manifest",
            "purpose": "Give agent tools and client generators an OpenAPI 3.1 route description.",
            "command": "abb endpoints --openapi",
        },
    ]
    if "cli" in modes:
        commands.append(
            {
                "name": "record_cli",
                "purpose": "Record an existing command without changing agent code.",
                "command": "abb record --name first-agent-run -- python3 path/to/agent.py",
            }
        )
    if "sdk" in modes:
        commands.append(
            {
                "name": "record_sdk",
                "purpose": "Use the Python SDK when you can add instrumentation.",
                "command": "python3 path/to/instrumented_agent.py",
            }
        )
    if "proxy" in modes:
        commands.extend(
            [
                {
                    "name": "start_proxy",
                    "purpose": "Start the local dashboard and OpenAI-compatible proxy.",
                    "command": "abb start",
                },
                {
                    "name": "proxy_client_base_url",
                    "purpose": "Point an OpenAI-compatible client at the local recorder.",
                    "command": f"export OPENAI_BASE_URL={shlex.quote(daemon_url + '/proxy/openai')}",
                },
            ]
        )
    commands.append(
        {
            "name": "support_packet",
            "purpose": "Create a compact local folder for review after a run exists.",
            "command": "abb support RUN_ID",
        }
    )
    return commands


def _init_snippets(data_dir: Path, daemon_url: str) -> Dict[str, str]:
    return {
        "cli": "abb record --name first-agent-run -- python3 path/to/agent.py",
        "sdk": "\n".join(
            [
                "from agent_black_box import annotate, record, span",
                "",
                "with record(\"my-agent-run\"):",
                "    with span(\"run agent\", type=\"agent.step\"):",
                "        result = run_agent()",
                "        annotate(\"Captured first Agent Black Box run\")",
            ]
        ),
        "openai_wrapper": "\n".join(
            [
                "from agent_black_box.openai import OpenAI",
                "",
                "client = OpenAI()",
                "response = client.chat.completions.create(",
                "    model=\"gpt-4.1-mini\",",
                "    messages=[{\"role\": \"user\", \"content\": \"Hello\"}],",
                ")",
                "print(response.choices[0].message.content)",
                "print(\"ABB run:\", response.abb_run_id)",
            ]
        ),
        "langchain_callback": "\n".join(
            [
                "from agent_black_box.adapters.langchain import AgentBlackBoxCallbackHandler",
                "",
                "callbacks = [AgentBlackBoxCallbackHandler(name=\"my-langchain-agent\")]",
                "# Pass callbacks=callbacks into your LangChain chain, agent, or runnable.",
                "# Example: chain.invoke({\"input\": \"...\"}, config={\"callbacks\": callbacks})",
            ]
        ),
        "langgraph_node": "\n".join(
            [
                "from agent_black_box.adapters.langgraph import LangGraphRecorder",
                "",
                "recorder = LangGraphRecorder(name=\"my-langgraph-agent\")",
                "wrapped_node = recorder.wrap_node(my_node, name=\"my_node\")",
                "# Add wrapped_node to your graph builder, or call it directly in local workflows.",
                "# End the run after the graph finishes: recorder.end_run(\"ok\")",
            ]
        ),
        "tool_recorder": "\n".join(
            [
                "from agent_black_box.adapters.tools import ToolCallRecorder",
                "",
                "recorder = ToolCallRecorder(name=\"my-tool-agent\")",
                "wrapped_tool = recorder.wrap_tool(my_tool, name=\"my_tool\")",
                "# Use wrapped_tool anywhere the agent would call my_tool.",
                "# For MCP-style calls: recorder.record_mcp_tool_call(\"tool_name\", arguments, result)",
            ]
        ),
        "proxy": "\n".join(
            [
                "abb start",
                f"export OPENAI_BASE_URL={shlex.quote(daemon_url + '/proxy/openai')}",
                "python3 path/to/agent.py",
            ]
        ),
        "support": "\n".join(
            [
                "abb handoff RUN_ID",
                "abb support RUN_ID",
                "abb support RUN_ID --include-bundle",
            ]
        ),
        "env": _init_env_text(data_dir, daemon_url),
    }


def _init_next_steps(modes: List[str]) -> List[str]:
    steps = ["Run `abb doctor` and resolve any errors before recording production-like traces."]
    if "cli" in modes:
        steps.append("Use CLI capture first when you want zero code changes.")
    if "sdk" in modes:
        steps.append("Add SDK spans around model calls, tool calls, and decision points for richer timelines.")
        steps.append("Use `from agent_black_box.openai import OpenAI` when an OpenAI import swap is enough.")
        steps.append("Use `AgentBlackBoxCallbackHandler` when the agent already supports LangChain callbacks.")
        steps.append("Wrap LangGraph-style node functions with `LangGraphRecorder.wrap_node` when the graph is built from Python callables.")
        steps.append("Wrap plain or MCP-style tools with `ToolCallRecorder` when tool inputs, outputs, and schemas matter.")
    if "proxy" in modes:
        steps.append("Start `abb start` before routing OpenAI-compatible traffic through the local proxy.")
    steps.append("After recording, run `abb handoff RUN_ID` or `abb support RUN_ID` for agent-to-agent review.")
    return steps


def _init_markdown(plan: Dict[str, Any]) -> str:
    lines = [
        "# Agent Black Box Init",
        "",
        f"Generated: {plan['created_at']}",
        f"Project: {plan['project']['name']}",
        f"Data dir: {plan['data_dir']}",
        f"Mode: {plan['mode']}",
        "",
        "## Verify",
        "",
        "```bash",
        "abb doctor",
        "abb doctor --json",
        "abb endpoints --json",
        "abb endpoints --openapi",
        "```",
        "",
    ]
    if "cli" in plan["modes"]:
        lines.extend(
            [
                "## CLI Capture",
                "",
                "Use this path when you cannot or do not want to edit agent code.",
                "",
                "```bash",
                plan["snippets"]["cli"],
                "```",
                "",
            ]
        )
    if "sdk" in plan["modes"]:
        lines.extend(
            [
                "## Python SDK",
                "",
                "Use this path when you can add instrumentation around agent work.",
                "",
                "```python",
                plan["snippets"]["sdk"],
                "```",
                "",
                "## OpenAI Import Swap",
                "",
                "Use this path when your agent already calls the OpenAI Python client shape.",
                "",
                "```python",
                plan["snippets"]["openai_wrapper"],
                "```",
                "",
                "## LangChain Callback",
                "",
                "Use this path when your agent already accepts LangChain callbacks.",
                "",
                "```python",
                plan["snippets"]["langchain_callback"],
                "```",
                "",
                "## LangGraph Node Wrapper",
                "",
                "Use this path when your graph is built from Python node functions.",
                "",
                "```python",
                plan["snippets"]["langgraph_node"],
                "```",
                "",
                "## Tool Call Recorder",
                "",
                "Use this path when your agent calls plain Python tools or MCP-style tools/call payloads.",
                "",
                "```python",
                plan["snippets"]["tool_recorder"],
                "```",
                "",
            ]
        )
    if "proxy" in plan["modes"]:
        lines.extend(
            [
                "## OpenAI-Compatible Proxy",
                "",
                "Use this path when the agent already calls an OpenAI-compatible API.",
                "",
                "```bash",
                plan["snippets"]["proxy"],
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## Handoff And Support",
            "",
            "After recording a run, use these commands to make it reviewable by another agent or person.",
            "",
            "```bash",
            plan["snippets"]["support"],
            "```",
            "",
            "## Next Steps",
            "",
        ]
    )
    lines.extend(f"- {step}" for step in plan["next_steps"])
    lines.append("")
    return "\n".join(lines)


def _init_env_text(data_dir: Path, daemon_url: str) -> str:
    return "\n".join(
        [
            "# Agent Black Box local environment helper",
            "# Source with: . path/to/agent-black-box.env",
            f"export ABB_HOME={shlex.quote(str(data_dir.resolve()))}",
            f"export ABB_DAEMON_URL={shlex.quote(daemon_url)}",
            "",
            "# For OpenAI-compatible clients, start `abb start` first, then uncomment:",
            f"# export OPENAI_BASE_URL={shlex.quote(daemon_url + '/proxy/openai')}",
            "",
            "# Keep secrets in your shell or secret manager; do not write them into this file.",
            "# export OPENAI_API_KEY=...",
            "",
        ]
    )


def _print_init_plan(plan: Dict[str, Any]) -> None:
    print("Agent Black Box init")
    print(f"Mode: {plan['mode']}")
    print(f"Data dir: {plan['data_dir']}")
    print(f"Guide: {plan['files']['guide']}")
    print(f"Env: {plan['files']['env']}")
    print(f"JSON: {plan['files']['plan']}")
    print()
    print("Next steps:")
    for step in plan["next_steps"]:
        print(f"- {step}")


def _create_agent_kit(
    store: ABBStore,
    daemon_url: str = DEFAULT_URL,
    output: Optional[str] = None,
    force: bool = False,
    zip_archive: bool = False,
    zip_output: Optional[str] = None,
) -> Dict[str, Any]:
    return create_agent_kit(
        store,
        daemon_url=daemon_url,
        output=output,
        force=force,
        zip_archive=zip_archive,
        zip_output=zip_output,
    )


def _print_agent_kit(kit: Dict[str, Any]) -> None:
    print("Agent Black Box agent kit")
    print(f"Directory: {Path(kit['files']['manifest']).parent}")
    print(f"Guide: {kit['files']['guide']}")
    print(f"OpenAPI: {kit['files']['openapi']}")
    print(f"Endpoints: {kit['files']['endpoints']}")
    print(f"Python client: {kit['files']['python_client']}")
    print(f"Node client: {kit['files']['node_client']}")
    if kit.get("archive"):
        print(f"Zip: {kit['archive']['path']}")
        print(f"SHA-256: {kit['archive']['sha256']}")
    print()
    print("Next steps:")
    print("- Run `sh smoke.sh` inside the kit directory.")
    print("- Start the daemon with `abb start`.")
    print("- Source `env.example`, then run the Python or Node client.")


def cmd_record(args: argparse.Namespace) -> int:
    command = normalize_command(args.command)
    if not command:
        print("Usage: abb record -- <command> [args...]", file=sys.stderr)
        return 2

    store = ABBStore(args.data_dir)
    run_name = args.name or " ".join(command)
    run = store.create_run(
        {
            "name": run_name,
            "source": "cli-record",
            "tags": args.tags,
            "environment": {
                "cwd": os.getcwd(),
                "platform": platform.platform(),
                "python": platform.python_version(),
            },
            "metadata": {"command": command},
        }
    )
    shell_span = store.start_span(
        {
            "run_id": run["run_id"],
            "type": "shell.command",
            "name": " ".join(command),
            "attributes": {"command": command, "cwd": os.getcwd()},
        }
    )

    env = os.environ.copy()
    env["ABB_ENABLED"] = env.get("ABB_ENABLED", "true")
    env["PYTHONDONTWRITEBYTECODE"] = env.get("PYTHONDONTWRITEBYTECODE", "1")
    add_src_to_pythonpath(env)

    server = None
    thread = None
    try:
        server, thread = serve_in_thread(store, host="127.0.0.1", port=0, auth_token=os.environ.get("ABB_AUTH_TOKEN"))
        daemon_url = f"http://127.0.0.1:{server.server_port}"
        env["ABB_DAEMON_URL"] = daemon_url
        env["ABB_ACTIVE_RUN_ID"] = run["run_id"]
    except OSError as exc:
        store.add_event(
            {
                "run_id": run["run_id"],
                "span_id": shell_span["span_id"],
                "type": "warning.detected",
                "message": "Temporary SDK collector could not start; recording shell command only.",
                "attributes": {"error": str(exc)},
            }
        )

    status = "ok"
    exit_code = 0
    try:
        completed = subprocess.run(command, capture_output=True, text=True, env=env)
        exit_code = completed.returncode
        if completed.stdout:
            sys.stdout.write(completed.stdout)
        if completed.stderr:
            sys.stderr.write(completed.stderr)
        if exit_code != 0:
            status = "error"

        artifact = store.add_artifact(
            run["run_id"],
            shell_span["span_id"],
            "terminal.transcript",
            json.dumps(
                {
                    "command": command,
                    "exit_code": exit_code,
                    "stdout": completed.stdout,
                    "stderr": completed.stderr,
                },
                indent=2,
            ),
            media_type="application/json",
        )
        store.add_event(
            {
                "run_id": run["run_id"],
                "span_id": shell_span["span_id"],
                "type": "shell.completed",
                "message": f"Command exited with {exit_code}",
                "attributes": {"exit_code": exit_code, "transcript_ref": artifact["artifact_id"]},
            }
        )
        store.end_span(
            shell_span["span_id"],
            status=status,
            output_ref=artifact["artifact_id"],
            attributes={"exit_code": exit_code},
        )
        store.end_run(run["run_id"], status=status)
    except FileNotFoundError as exc:
        status = "error"
        exit_code = 127
        store.add_event(
            {
                "run_id": run["run_id"],
                "span_id": shell_span["span_id"],
                "type": "error",
                "message": str(exc),
            }
        )
        store.end_span(shell_span["span_id"], status=status, attributes={"exit_code": exit_code})
        store.end_run(run["run_id"], status=status)
        print(str(exc), file=sys.stderr)
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=2)
        store.close()

    print(f"\nRecorded run: {run['run_id']}", file=sys.stderr)
    return exit_code


def cmd_runs(args: argparse.Namespace) -> int:
    store = ABBStore(args.data_dir)
    runs = store.list_runs(limit=args.limit)
    store.close()
    if args.json:
        print(json.dumps(runs, indent=2, sort_keys=True))
        return 0
    if not runs:
        print("No runs recorded yet")
        return 0
    for run in runs:
        ended = run.get("ended_at") or "running"
        provenance = _run_provenance_label(run)
        suffix = f"  [{provenance}]" if provenance else ""
        print(f"{run['run_id']}  {run['status']:8}  {run['created_at']}  {ended}  {run['name']}{suffix}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    store = ABBStore(args.data_dir)
    try:
        timeline = store.get_timeline(args.run_id)
        links = store.get_run_links(args.run_id)
    except KeyError:
        print(f"Run not found: {args.run_id}", file=sys.stderr)
        store.close()
        return 1
    store.close()
    if args.json:
        print(json.dumps(timeline, indent=2, sort_keys=True))
        return 0
    run = timeline["run"]
    print(f"{run['name']} ({run['run_id']})")
    print(f"Status: {run['status']}  Source: {run['source']}")
    for line in _run_provenance_lines(run):
        print(line)
    for line in _run_link_lines(links):
        print(line)
    for line in _compare_investigation_lines(timeline):
        print(line)
    for line in _run_summary_lines(timeline.get("summary") or {}):
        print(line)
    for line in _debug_path_lines(timeline.get("debug_path") or []):
        print(line)
    print()
    for item in timeline["items"]:
        print(_timeline_item_line(item))
    if timeline["annotations"]:
        print()
        print("Annotations:")
        for annotation in timeline["annotations"]:
            target = f" span={annotation['span_id']}" if annotation.get("span_id") else ""
            print(f"- {annotation['created_at']}{target} {annotation['message']}")
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    if not args.yes:
        print(
            "Refusing to delete without confirmation. Re-run with `--yes` after exporting anything you need.",
            file=sys.stderr,
        )
        return 2
    store = ABBStore(args.data_dir)
    try:
        result = store.delete_run(args.run_id, include_exports=not args.keep_exports)
    except KeyError:
        print(f"Run not found: {args.run_id}", file=sys.stderr)
        return 1
    finally:
        store.close()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    counts = result.get("counts") or {}
    print(f"Deleted run: {result['run_id']}")
    print(
        "Removed: "
        f"{counts.get('spans', 0)} spans, "
        f"{counts.get('events', 0)} events, "
        f"{counts.get('artifacts', 0)} artifacts, "
        f"{counts.get('annotations', 0)} annotations, "
        f"{counts.get('fixtures', 0)} fixtures"
    )
    print(
        "Local files removed: "
        f"{counts.get('artifact_objects', 0)} object files "
        f"({counts.get('artifact_bytes', 0)} bytes), "
        f"{counts.get('export_files', 0)} export files "
        f"({counts.get('export_bytes', 0)} bytes)"
    )
    if result.get("linked_investigations"):
        print("Linked investigation runs were kept:")
        for linked_run_id in result["linked_investigations"]:
            print(f"- {linked_run_id}")
    return 0


def _run_link_lines(links: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    source = links.get("source")
    if source:
        lines.append(f"Source trace: {source['run_id']} ({source['name']})")
    investigations = links.get("investigations") or []
    if investigations:
        lines.append(
            "Investigations: "
            + ", ".join(f"{run['run_id']} ({run['name']})" for run in investigations)
        )
    return lines


def _compare_investigation_lines(timeline: Dict[str, Any]) -> List[str]:
    run = timeline.get("run") or {}
    metadata = run.get("metadata") or {}
    source_run_id = metadata.get("source_compare_run_id") or ""
    if run.get("source") != "compare-ingest" and not source_run_id:
        return []

    source_span_id = metadata.get("source_compare_span_id") or ""
    source_span_name = metadata.get("source_compare_span_name") or ""
    pair_type = metadata.get("source_compare_pair_type") or "compare"
    pair_label = metadata.get("source_compare_pair_label") or pair_type
    artifact_by_kind: Dict[str, Dict[str, Any]] = {}
    for artifact in timeline.get("artifacts") or []:
        kind = artifact.get("kind")
        if kind and kind not in artifact_by_kind:
            artifact_by_kind[kind] = artifact

    lines = [
        "Compare Investigation:",
        f"Source run: {source_run_id or 'unknown'}",
    ]
    if source_span_name and source_span_id and source_span_name != source_span_id:
        lines.append(f"Source span: {source_span_name} ({source_span_id})")
    else:
        lines.append(f"Source span: {source_span_id or source_span_name or 'unknown'}")
    lines.append(f"Pair: {pair_type} / {pair_label}")
    lines.append("Evidence:")
    for label, kind in [
        ("packet", "compare.packet"),
        ("briefing", "compare.briefing"),
        ("left body", "compare.left"),
        ("right body", "compare.right"),
    ]:
        artifact = artifact_by_kind.get(kind)
        artifact_id = artifact.get("artifact_id") if artifact else "missing"
        lines.append(f"- {label}: {artifact_id} ({kind})")
    return lines


def _timeline_item_line(item: Dict[str, Any]) -> str:
    title = item.get("name") or item.get("message") or item.get("type")
    usage = usage_from_attributes(item.get("attributes") or {})
    usage_text = format_usage(usage)
    suffix = f"  {usage_text}" if usage_text else ""
    return f"- {item.get('ts')} [{item.get('type')}] {title}{suffix}"


def _run_summary_lines(summary: Dict[str, Any]) -> List[str]:
    if not summary:
        return []
    usage = summary.get("usage") or {}
    usage_text = format_usage(usage)
    lines = [
        "Summary: "
        f"{summary.get('model_calls', 0)} model calls, "
        f"{summary.get('tool_calls', 0)} tool calls, "
        f"{summary.get('graph_nodes', 0)} graph nodes, "
        f"{summary.get('warnings', 0)} warnings, "
        f"{summary.get('errors', 0)} errors, "
        f"{summary.get('artifacts', 0)} artifacts"
    ]
    if usage_text:
        lines.append(f"Usage: {usage_text}")
    first_failure = summary.get("first_failure")
    if first_failure:
        lines.append(
            "First failure: "
            f"{first_failure.get('ts') or 'unknown time'} "
            f"[{first_failure.get('type') or first_failure.get('kind')}] "
            f"{first_failure.get('title') or first_failure.get('id')}"
        )
    return lines


def _debug_path_lines(debug_path: List[Dict[str, Any]]) -> List[str]:
    if not debug_path:
        return []
    lines = ["Debug Path:"]
    for item in debug_path[:5]:
        refs = _format_refs(item.get("refs") or {})
        refs_text = f" refs: {refs}" if refs else ""
        lines.append(
            f"{item.get('step', '?')}. "
            f"[{item.get('priority', 'note')}] "
            f"{item.get('label') or item.get('kind')}: "
            f"{item.get('title') or item.get('id')} "
            f"@ {item.get('ts') or 'unknown time'}{refs_text}"
        )
        if item.get("reason"):
            lines.append(f"   Why: {item['reason']}")
        if item.get("suggested_action"):
            lines.append(f"   Next: {item['suggested_action']}")
    return lines


def _format_refs(refs: Dict[str, Any]) -> str:
    return ", ".join(f"{key}={refs[key]}" for key in sorted(refs))


def _run_provenance_label(run: Dict[str, Any]) -> str:
    metadata = run.get("metadata") or {}
    if metadata.get("remapped_from_run_id"):
        return "remapped import"
    if metadata.get("imported_from_bundle"):
        return "imported bundle"
    return ""


def _run_provenance_lines(run: Dict[str, Any]) -> List[str]:
    metadata = run.get("metadata") or {}
    lines: List[str] = []
    if metadata.get("remapped_from_run_id"):
        lines.append(f"Remapped from: {metadata['remapped_from_run_id']}")
    if metadata.get("imported_from_bundle"):
        lines.append(f"Imported bundle: {metadata['imported_from_bundle']}")
    return lines


def cmd_search(args: argparse.Namespace) -> int:
    store = ABBStore(args.data_dir)
    runs = store.search(args.query)
    store.close()
    if args.json:
        print(json.dumps(runs, indent=2, sort_keys=True))
        return 0
    for run in runs:
        print(f"{run['run_id']}  {run['status']:8}  {run['created_at']}  {run['name']}")
    return 0


def cmd_annotate(args: argparse.Namespace) -> int:
    store = ABBStore(args.data_dir)
    if not store.get_run(args.run_id):
        print(f"Run not found: {args.run_id}", file=sys.stderr)
        store.close()
        return 1
    annotation = store.add_annotation(args.run_id, args.message, span_id=args.span_id)
    store.close()
    print(f"{annotation['annotation_id']}  {annotation['created_at']}  {annotation['message']}")
    return 0


def cmd_annotations(args: argparse.Namespace) -> int:
    store = ABBStore(args.data_dir)
    if not store.get_run(args.run_id):
        print(f"Run not found: {args.run_id}", file=sys.stderr)
        store.close()
        return 1
    annotations = store.list_annotations(args.run_id)
    store.close()
    if args.json:
        print(json.dumps(annotations, indent=2, sort_keys=True))
        return 0
    if not annotations:
        print("No annotations")
        return 0
    for annotation in annotations:
        target = f" span={annotation['span_id']}" if annotation.get("span_id") else ""
        print(f"{annotation['annotation_id']}  {annotation['created_at']}{target}  {annotation['message']}")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    store = ABBStore(args.data_dir)
    try:
        diff = compare_runs(store, args.run_a, args.run_b)
    except KeyError as exc:
        print(f"Run not found: {exc}", file=sys.stderr)
        store.close()
        return 1
    store.close()
    if args.json:
        print(json.dumps(diff, indent=2, sort_keys=True))
    else:
        print(format_diff(diff))
    return 0


def cmd_artifacts(args: argparse.Namespace) -> int:
    store = ABBStore(args.data_dir)
    artifacts = store.list_artifacts(args.run_id)
    store.close()
    if args.json:
        print(json.dumps(artifacts, indent=2, sort_keys=True))
        return 0
    if not artifacts:
        print("No artifacts found")
        return 0
    for artifact in artifacts:
        print(
            f"{artifact['artifact_id']}  {artifact['kind']:20}  "
            f"{artifact['media_type']:24}  {artifact['size']:6} bytes  {artifact['created_at']}"
        )
    return 0


def cmd_artifact(args: argparse.Namespace) -> int:
    store = ABBStore(args.data_dir)
    artifact = store.get_artifact(args.artifact_id)
    content = store.read_artifact(args.artifact_id)
    store.close()
    if not artifact or content is None:
        print(f"Artifact not found: {args.artifact_id}", file=sys.stderr)
        return 1
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        print(path)
        return 0
    print(f"{artifact['artifact_id']}  {artifact['kind']}  {artifact['media_type']}  {artifact['size']} bytes")
    if artifact["media_type"].startswith("text/") or "json" in artifact["media_type"]:
        print()
        print(content.decode("utf-8", errors="replace"))
    return 0


def cmd_fixture_create(args: argparse.Namespace) -> int:
    store = ABBStore(args.data_dir)
    try:
        fixture = store.create_fixture(args.run_id, name=args.name)
    except KeyError:
        print(f"Run not found: {args.run_id}", file=sys.stderr)
        store.close()
        return 1
    store.close()
    print(fixture["fixture_id"])
    return 0


def cmd_fixture_list(args: argparse.Namespace) -> int:
    store = ABBStore(args.data_dir)
    fixtures = store.list_fixtures(limit=args.limit)
    store.close()
    if args.json:
        print(json.dumps(fixtures, indent=2, sort_keys=True))
        return 0
    if not fixtures:
        print("No replay fixtures yet")
        return 0
    for fixture in fixtures:
        print(f"{fixture['fixture_id']}  {fixture['created_at']}  {fixture['run_id']}  {fixture['name']}")
    return 0


def cmd_fixture_show(args: argparse.Namespace) -> int:
    store = ABBStore(args.data_dir)
    fixture = store.get_fixture(args.fixture_id)
    store.close()
    if not fixture:
        print(f"Fixture not found: {args.fixture_id}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(fixture, indent=2, sort_keys=True))
        return 0
    body = fixture["fixture"]
    expected = body.get("expected") or {}
    print(f"{fixture['name']} ({fixture['fixture_id']})")
    print(f"Source run: {fixture['run_id']}")
    print(
        f"Expected: {expected.get('status')}  "
        f"{expected.get('span_count')} spans  "
        f"{expected.get('event_count')} events  "
        f"{expected.get('artifact_count')} artifacts"
    )
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    store = ABBStore(args.data_dir)
    fixture = store.get_fixture(args.fixture_id)
    store.close()
    if not fixture:
        print(f"Fixture not found: {args.fixture_id}", file=sys.stderr)
        return 1
    print("\n".join(visual_replay_lines(fixture)))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    store = ABBStore(args.data_dir)
    try:
        output = store.export_run(args.run_id, fmt=args.format, output=args.output)
    except KeyError:
        print(f"Run not found: {args.run_id}", file=sys.stderr)
        store.close()
        return 1
    finally:
        store.close()
    print(output)
    return 0


def cmd_compare_export(args: argparse.Namespace) -> int:
    store = ABBStore(args.data_dir)
    try:
        if args.output == "-":
            payload = store.build_compare_export(args.run_id, span_id=args.span_id, pair=args.pair)
            print(format_compare_export(payload, args.format), end="")
        else:
            output = store.export_compare_pair(
                args.run_id,
                span_id=args.span_id,
                pair=args.pair,
                fmt=args.format,
                output=args.output,
            )
            print(output)
    except KeyError:
        print(f"Run not found: {args.run_id}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Compare export failed: {exc}", file=sys.stderr)
        return 1
    finally:
        store.close()
    return 0


def cmd_compare_ingest(args: argparse.Namespace) -> int:
    try:
        packet = _read_compare_packet(args.path)
        briefing = format_compare_briefing(packet)
        store = ABBStore(args.data_dir)
        try:
            result = store.ingest_compare_packet(packet, name=args.name, briefing=briefing)
        finally:
            store.close()
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        print(f"Compare ingest failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            f"Created compare investigation run {result['run']['run_id']} "
            f"from {result['source_run_id']} span {result['source_span_id']}"
        )
        print(f"Packet artifact: {result['packet_artifact']['artifact_id']}")
        print(f"Briefing artifact: {result['briefing_artifact']['artifact_id']}")
        print(f"Left artifact: {result['left_artifact']['artifact_id']}")
        print(f"Right artifact: {result['right_artifact']['artifact_id']}")
    return 0


def cmd_compare_evidence(args: argparse.Namespace) -> int:
    store = ABBStore(args.data_dir)
    try:
        timeline = store.get_timeline(args.run_id)
    except KeyError:
        print(f"Run not found: {args.run_id}", file=sys.stderr)
        store.close()
        return 1

    part = args.part
    if not part:
        try:
            summary = store.compare_evidence_summary(args.run_id)
        except ValueError as exc:
            store.close()
            print(str(exc), file=sys.stderr)
            return 1
        store.close()
        if args.output:
            print("--output requires --packet, --briefing, --left, or --right", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(summary, indent=2, sort_keys=True))
        else:
            for line in _compare_investigation_lines(timeline):
                print(line)
            print("Use --packet, --briefing, --left, or --right to print one evidence body.")
        return 0

    try:
        result = store.get_compare_evidence(args.run_id, part, raw=args.raw)
    except ValueError as exc:
        store.close()
        print(str(exc), file=sys.stderr)
        return 1
    store.close()

    artifact = result["artifact"]
    text = result["content"]
    if args.output and args.output != "-":
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(path)
        return 0
    if args.json:
        print(
            json.dumps(
                {
                    **result,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.output == "-":
        print(text, end="" if text.endswith("\n") else "\n")
        return 0
    print(f"{artifact['artifact_id']}  {artifact['kind']}  {artifact['media_type']}  {artifact['size']} bytes")
    print()
    print(text, end="" if text.endswith("\n") else "\n")
    return 0


def cmd_handoff(args: argparse.Namespace) -> int:
    modes = [bool(args.run_id), bool(args.file), bool(args.ingest_file)]
    if sum(1 for enabled in modes if enabled) != 1:
        print("Provide exactly one of RUN_ID, --file PATH, or --ingest PATH", file=sys.stderr)
        return 2
    try:
        if args.ingest_file:
            packet = _read_handoff_packet(args.ingest_file)
            briefing = format_handoff_briefing(packet, timeline_limit=args.timeline_limit)
            store = ABBStore(args.data_dir)
            try:
                result = store.ingest_handoff_packet(packet, briefing, name=args.name)
            finally:
                store.close()
            if args.json:
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                print(
                    f"Created investigation run {result['run']['run_id']} "
                    f"from handoff {result['source_run_id']}"
                )
                print(f"Packet artifact: {result['packet_artifact']['artifact_id']}")
                print(f"Briefing artifact: {result['briefing_artifact']['artifact_id']}")
            return 0
        if args.file:
            packet = _read_handoff_packet(args.file)
        else:
            store = ABBStore(args.data_dir)
            try:
                packet = store.build_handoff_packet(args.run_id)
            finally:
                store.close()
    except KeyError:
        print(f"Run not found: {args.run_id}", file=sys.stderr)
        return 1
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        print(f"Handoff read failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(packet, indent=2, sort_keys=True))
    else:
        print(format_handoff_briefing(packet, timeline_limit=args.timeline_limit))
    return 0


def cmd_support(args: argparse.Namespace) -> int:
    store = ABBStore(args.data_dir)
    try:
        result = _create_support_packet(
            store,
            args.run_id,
            output=args.output,
            include_bundle=args.include_bundle,
            daemon_url=args.url,
        )
    except KeyError:
        print(f"Run not found: {args.run_id}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"Support packet failed: {exc}", file=sys.stderr)
        return 1
    finally:
        store.close()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    print(f"Support packet: {result['directory']}")
    print(f"Briefing: {result['paths']['briefing']}")
    print(f"Handoff: {result['paths']['handoff']}")
    print(f"Doctor: {result['paths']['doctor']}")
    if result["paths"].get("bundle"):
        print(f"Bundle: {result['paths']['bundle']}")
    else:
        print("Bundle: not included (use --include-bundle for full artifact payloads)")
    return 0


def _create_support_packet(
    store: ABBStore,
    run_id: str,
    output: Optional[str] = None,
    include_bundle: bool = False,
    daemon_url: Optional[str] = None,
) -> Dict[str, Any]:
    timeline = store.get_timeline(run_id)
    handoff = store.build_handoff_packet(run_id)
    briefing = format_handoff_briefing(handoff)
    support_dir = (
        Path(output)
        if output
        else store.root / "support" / f"{run_id}-{new_id('support')}"
    )
    support_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "manifest": support_dir / "manifest.json",
        "readme": support_dir / "README.txt",
        "doctor": support_dir / "doctor.json",
        "handoff": support_dir / f"{run_id}.handoff.json",
        "briefing": support_dir / "briefing.txt",
        "timeline": support_dir / "timeline.json",
        "troubleshooting": support_dir / "TROUBLESHOOTING.txt",
        "known_limitations": support_dir / "KNOWN_LIMITATIONS.txt",
        "bundle": None,
    }
    _write_json(paths["handoff"], handoff)
    paths["briefing"].write_text(briefing + "\n", encoding="utf-8")
    _write_json(paths["timeline"], timeline)
    _write_json(paths["doctor"], _support_doctor_report(store, daemon_url))
    _write_support_doc(paths["troubleshooting"], "TROUBLESHOOTING.md", "Troubleshooting")
    _write_support_doc(paths["known_limitations"], "KNOWN_LIMITATIONS.md", "Known Limitations")
    if include_bundle:
        bundle_path = support_dir / f"{run_id}.abb"
        store.export_bundle(run_id, output=bundle_path)
        paths["bundle"] = bundle_path

    manifest = {
        "support_version": "0.1",
        "created_at": utc_now(),
        "run_id": run_id,
        "run_name": timeline["run"]["name"],
        "contains_full_bundle": include_bundle,
        "privacy": {
            "handoff_embeds_artifact_payloads": False,
            "timeline_embeds_artifact_payloads": False,
            "bundle_embeds_artifact_payloads": include_bundle,
        },
        "paths": {
            key: str(value) if value else None
            for key, value in paths.items()
        },
    }
    _write_json(paths["manifest"], manifest)
    paths["readme"].write_text(_support_readme(manifest), encoding="utf-8")
    return {
        "directory": str(support_dir),
        "run_id": run_id,
        "contains_full_bundle": include_bundle,
        "paths": manifest["paths"],
    }


def _support_doctor_report(store: ABBStore, daemon_url: Optional[str]) -> Dict[str, Any]:
    return _build_doctor_report(store.root, daemon_url, store=store)


def _write_support_doc(destination: Path, source_name: str, title: str) -> None:
    source = REPO_ROOT / "docs" / source_name
    if source.exists():
        text = source.read_text(encoding="utf-8")
    else:
        text = "\n".join(
            [
                f"# Agent Black Box {title}",
                "",
                f"The source install did not include docs/{source_name}.",
                "Start with README.txt, briefing.txt, timeline.json, and doctor.json in this packet.",
                "",
                "Useful local commands:",
                "- abb doctor",
                "- abb endpoints --json",
                "- abb support RUN_ID --include-bundle",
                "",
            ]
        )
    destination.write_text(text.rstrip() + "\n", encoding="utf-8")


def _build_doctor_report(
    data_dir: Path,
    daemon_url: Optional[str],
    store: Optional[ABBStore] = None,
) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    next_steps: List[str] = []
    active_store = store
    owns_store = False

    checks.append(
        _doctor_check(
            "python",
            "ok" if sys.version_info >= (3, 9) else "error",
            f"Python {platform.python_version()}",
            {
                "executable": sys.executable,
                "required": ">=3.9",
                "version": platform.python_version(),
            },
        )
    )
    if sys.version_info < (3, 9):
        next_steps.append("Use Python 3.9 or newer.")

    try:
        if active_store is None:
            active_store = ABBStore(data_dir)
            owns_store = True
        probe_path = active_store.root / ".doctor-write-test"
        probe_path.write_text("ok\n", encoding="utf-8")
        probe_path.unlink(missing_ok=True)
        run_count = len(active_store.list_runs(limit=1000))
        checks.append(
            _doctor_check(
                "storage",
                "ok",
                "Local store is writable",
                {
                    "data_dir": str(active_store.root.resolve()),
                    "database": str(active_store.db_path.resolve()),
                    "objects_dir": str(active_store.objects_dir.resolve()),
                    "exports_dir": str(active_store.exports_dir.resolve()),
                    "run_count_sample": run_count,
                },
            )
        )
        if run_count == 0:
            next_steps.append("Record a first trace with `abb record -- python3 examples/basic_agent.py`.")
    except Exception as exc:
        checks.append(
            _doctor_check(
                "storage",
                "error",
                f"Local store failed: {exc}",
                {"data_dir": str(data_dir), "error": str(exc)},
            )
        )
        next_steps.append("Check `ABB_HOME` or pass `--data-dir` to a writable local directory.")
    finally:
        if owns_store and active_store is not None:
            active_store.close()

    abb_executable = shutil.which("abb")
    checks.append(
        _doctor_check(
            "cli",
            "ok",
            "CLI entrypoint is available",
            {
                "argv0": sys.argv[0],
                "abb_on_path": abb_executable,
                "running_from_source": str(Path(__file__).resolve()),
            },
        )
    )

    daemon_health = http_get(daemon_url + "/health") if daemon_url else None
    if daemon_url and daemon_health:
        checks.append(
            _doctor_check(
                "daemon",
                "ok",
                f"Daemon is reachable at {daemon_url}",
                {"url": daemon_url, "health": daemon_health},
            )
        )
    elif daemon_url:
        checks.append(
            _doctor_check(
                "daemon",
                "warning",
                f"Daemon is not running at {daemon_url}",
                {"url": daemon_url},
            )
        )
        next_steps.append("Start the local dashboard with `abb start` when you want the browser UI or proxy.")

    openai_key_present = bool(os.environ.get("OPENAI_API_KEY"))
    checks.append(
        _doctor_check(
            "openai_proxy",
            "ok",
            "OpenAI-compatible proxy can record when traffic is routed through the daemon",
            {
                "base_url": os.environ.get("ABB_OPENAI_BASE_URL", "https://api.openai.com"),
                "openai_api_key_present": openai_key_present,
                "accepts_request_authorization_header": True,
            },
        )
    )
    if not openai_key_present:
        next_steps.append("For proxy tests, set `OPENAI_API_KEY` or send an Authorization header from the client.")

    next_steps.append("Discover local HTTP routes with `abb endpoints --json` or `abb endpoints --openapi`.")
    next_steps.append("For non-Python agents, start `abb start` and run `python3 examples/http_agent_client.py`.")
    next_steps.append("If you hit a local alpha issue, check `docs/TROUBLESHOOTING.md` or run `abb support RUN_ID`.")

    summary = {
        "errors": sum(1 for check in checks if check["status"] == "error"),
        "warnings": sum(1 for check in checks if check["status"] == "warning"),
        "ok": sum(1 for check in checks if check["status"] == "ok"),
    }
    status = "error" if summary["errors"] else "warning" if summary["warnings"] else "ok"
    return {
        "doctor_version": "0.1",
        "created_at": utc_now(),
        "status": status,
        "summary": summary,
        "abb_version": __version__,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "paths": {
            "data_dir": str(data_dir),
            "cwd": os.getcwd(),
        },
        "api": api_manifest(daemon_url or DEFAULT_URL),
        "environment": {
            "ABB_HOME": os.environ.get("ABB_HOME"),
            "ABB_DAEMON_URL": os.environ.get("ABB_DAEMON_URL"),
            "ABB_OPENAI_BASE_URL": os.environ.get("ABB_OPENAI_BASE_URL"),
            "ABB_AUTH_TOKEN_present": bool(os.environ.get("ABB_AUTH_TOKEN")),
            "OPENAI_API_KEY_present": openai_key_present,
        },
        "checks": checks,
        "next_steps": _dedupe_preserve_order(next_steps),
    }


def _doctor_check(
    name: str,
    status: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "message": message,
        "details": details or {},
    }


def _print_doctor_report(report: Dict[str, Any]) -> None:
    summary = report["summary"]
    print("Agent Black Box doctor")
    print(f"Status: {report['status']} ({summary['errors']} errors, {summary['warnings']} warnings)")
    print(f"Version: {report['abb_version']}")
    print(f"Python: {report['python']}")
    print(f"Platform: {report['platform']}")
    print(f"Data dir: {report['paths']['data_dir']}")
    print()
    print("Checks:")
    for check in report["checks"]:
        print(f"- [{check['status']}] {check['name']}: {check['message']}")
    if report["next_steps"]:
        print()
        print("Next steps:")
        for step in report["next_steps"]:
            print(f"- {step}")


def _dedupe_preserve_order(values: List[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _support_readme(manifest: Dict[str, Any]) -> str:
    bundle_note = (
        "This packet includes a full .abb bundle with artifact payloads."
        if manifest["contains_full_bundle"]
        else "This packet does not include a full .abb bundle or artifact payloads."
    )
    return "\n".join(
        [
            "Agent Black Box Support Packet",
            "",
            f"Run: {manifest['run_id']} ({manifest['run_name']})",
            f"Created: {manifest['created_at']}",
            "",
            "Start with briefing.txt for the compact agent-readable summary.",
            "Use the .handoff.json packet when another agent needs structured context.",
            "Use timeline.json for local trace metadata without artifact payloads.",
            "Use doctor.json for local environment and daemon status.",
            "Use TROUBLESHOOTING.txt and KNOWN_LIMITATIONS.txt for offline support context.",
            bundle_note,
            "",
            "When reporting a bug, include:",
            "- The command you ran and the exact error text.",
            "- The run_id from this packet.",
            "- Whether the problem happened in CLI, browser, SDK, HTTP API, proxy, or import/export.",
            "- The output of abb doctor or the included doctor.json.",
            "- Whether ABB_HOME, ABB_DAEMON_URL, or ABB_AUTH_TOKEN was set.",
            "",
            "Useful next commands:",
            f"- abb show {manifest['run_id']}",
            f"- abb handoff {manifest['run_id']}",
            f"- abb support {manifest['run_id']} --include-bundle",
            "",
            "Troubleshooting: TROUBLESHOOTING.txt (source: docs/TROUBLESHOOTING.md)",
            "Known limitations: KNOWN_LIMITATIONS.txt (source: docs/KNOWN_LIMITATIONS.md)",
            "",
        ]
    )


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_handoff_packet(path: str) -> Dict[str, Any]:
    packet = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(packet, dict):
        raise ValueError("handoff packet must be a JSON object")
    return packet


def _read_compare_packet(path: str) -> Dict[str, Any]:
    packet = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(packet, dict):
        raise ValueError("compare packet must be a JSON object")
    return packet


def cmd_bundle_export(args: argparse.Namespace) -> int:
    store = ABBStore(args.data_dir)
    try:
        output = store.export_bundle(args.run_id, output=args.output)
    except KeyError:
        print(f"Run not found: {args.run_id}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        store.close()
    print(output)
    return 0


def cmd_bundle_import(args: argparse.Namespace) -> int:
    store = ABBStore(args.data_dir)
    try:
        result = store.import_bundle(args.path, on_conflict=args.on_conflict)
    except (ValueError, KeyError, json.JSONDecodeError, OSError, zipfile.BadZipFile) as exc:
        print(f"Bundle import failed: {exc}", file=sys.stderr)
        return 1
    finally:
        store.close()
    counts = result.get("counts") or {}
    if result.get("skipped"):
        print(f"Skipped existing run {result['run_id']} from {result['bundle']}")
        return 0
    remap_note = ""
    if result.get("remapped"):
        remap_note = f" (remapped from {result['original_run_id']})"
    print(
        f"Imported {result['run_id']}{remap_note} from {result['bundle']} "
        f"({counts.get('spans', 0)} spans, {counts.get('events', 0)} events, "
        f"{counts.get('artifacts', 0)} artifacts)"
    )
    return 0


def cmd_open(args: argparse.Namespace) -> int:
    webbrowser.open(args.url)
    print(args.url)
    return 0


def normalize_command(command: List[str]) -> List[str]:
    if command and command[0] == "--":
        return command[1:]
    return command


def add_src_to_pythonpath(env: Dict[str, str]) -> None:
    src = Path(__file__).resolve().parents[1]
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(src) if not existing else str(src) + os.pathsep + existing


def http_get(url: str) -> Optional[Any]:
    try:
        req = request.Request(url, method="GET")
        token = os.environ.get("ABB_AUTH_TOKEN")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with request.urlopen(req, timeout=1.5) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
