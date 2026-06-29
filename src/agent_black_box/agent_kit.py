from __future__ import annotations

import json
import hashlib
from pathlib import Path
import shlex
from typing import Any, Dict, Optional
import zipfile

from .api_manifest import api_manifest, openapi_spec
from .ids import new_id, utc_now
from .storage import ABBStore


DEFAULT_DAEMON_URL = "http://127.0.0.1:43188"
REPO_ROOT = Path(__file__).resolve().parents[2]


def create_agent_kit(
    store: ABBStore,
    daemon_url: str = DEFAULT_DAEMON_URL,
    output: Optional[str] = None,
    force: bool = False,
    zip_archive: bool = False,
    zip_output: Optional[str] = None,
) -> Dict[str, Any]:
    kit_id = new_id("agentkit")
    output_dir = Path(output) if output else store.root / "agent-kit"
    zip_path = Path(zip_output) if zip_output else output_dir / "agent-kit.zip"
    paths = {
        "manifest": output_dir / "agent-kit.json",
        "readme": output_dir / "README.txt",
        "guide": output_dir / "AGENT_BLACK_BOX.md",
        "endpoints": output_dir / "endpoints.json",
        "openapi": output_dir / "openapi.json",
        "python_client": output_dir / "python_client.py",
        "node_client": output_dir / "node_client.mjs",
        "env": output_dir / "env.example",
        "smoke": output_dir / "smoke.sh",
    }
    existing = [path for path in paths.values() if path.exists()]
    if zip_archive and zip_path.exists():
        existing.append(zip_path)
    if existing and not force:
        raise ValueError(
            "agent-kit output already exists; pass --force or choose a new --output: "
            + ", ".join(str(path) for path in existing)
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    endpoint_manifest = api_manifest(daemon_url)
    openapi = openapi_spec(daemon_url)
    manifest = {
        "agent_kit_version": "0.1",
        "kit_id": kit_id,
        "created_at": utc_now(),
        "daemon_url": daemon_url.rstrip("/"),
        "data_dir": str(store.root.resolve()),
        "files": {key: str(path) for key, path in paths.items()},
        "zip_path": None,
        "sha256": None,
        "archive": None,
        "commands": {
            "start_daemon": "abb start",
            "doctor": "abb doctor",
            "discover": "abb endpoints --json",
            "openapi": "abb endpoints --openapi",
            "zip": "abb agent-kit --zip",
            "python_smoke": "python3 python_client.py",
            "node_smoke": "node node_client.mjs",
            "handoff": "abb handoff RUN_ID",
            "support": "abb support RUN_ID",
        },
        "api": {
            "service": endpoint_manifest["service"],
            "manifest_version": endpoint_manifest["manifest_version"],
            "openapi": openapi["openapi"],
            "endpoint_count": len(endpoint_manifest["endpoints"]),
        },
    }

    _write_json(paths["endpoints"], endpoint_manifest)
    _write_json(paths["openapi"], openapi)
    paths["python_client"].write_text(_repo_text("examples/http_agent_client.py", _fallback_python_client()), encoding="utf-8")
    paths["node_client"].write_text(_repo_text("examples/js-agent-client.mjs", _fallback_node_client()), encoding="utf-8")
    paths["env"].write_text(_agent_kit_env_text(store.root, daemon_url), encoding="utf-8")
    paths["guide"].write_text(_agent_kit_guide(manifest), encoding="utf-8")
    paths["readme"].write_text(_agent_kit_readme(manifest), encoding="utf-8")
    paths["smoke"].write_text(_agent_kit_smoke_text(), encoding="utf-8")
    paths["smoke"].chmod(0o755)
    _write_json(paths["manifest"], manifest)
    if zip_archive:
        archive = _write_agent_kit_zip(paths, zip_path)
        manifest["zip_path"] = archive["path"]
        manifest["sha256"] = archive["sha256"]
        manifest["archive"] = archive
        _write_json(paths["manifest"], manifest)
    return manifest


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_agent_kit_zip(paths: Dict[str, Path], zip_path: Path) -> Dict[str, Any]:
    ordered_keys = [
        "readme",
        "guide",
        "endpoints",
        "openapi",
        "python_client",
        "node_client",
        "env",
        "smoke",
        "manifest",
    ]
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    contents = []
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for key in ordered_keys:
            path = paths[key]
            archive.write(path, arcname=path.name)
            contents.append(path.name)
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    return {
        "path": str(zip_path),
        "sha256": digest,
        "size": zip_path.stat().st_size,
        "contents": contents,
    }


def _repo_text(relative_path: str, fallback: str) -> str:
    path = REPO_ROOT / relative_path
    if path.exists():
        return path.read_text(encoding="utf-8")
    return fallback


def _agent_kit_env_text(data_dir: Path, daemon_url: str) -> str:
    return "\n".join(
        [
            "# Agent Black Box agent-kit environment",
            "# Source with: . env.example",
            f"export ABB_DAEMON_URL={shlex.quote(daemon_url.rstrip('/'))}",
            f"export ABB_HOME={shlex.quote(str(data_dir.resolve()))}",
            "",
            "# Optional: require bearer auth when abb start is launched with --token.",
            "# export ABB_AUTH_TOKEN=replace-me",
            "",
        ]
    )


def _agent_kit_guide(manifest: Dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Agent Black Box Agent Kit",
            "",
            f"Generated: {manifest['created_at']}",
            f"Daemon URL: {manifest['daemon_url']}",
            "",
            "## Goal",
            "",
            "Use this folder to teach any local agent how to record traces into Agent Black Box without reading the whole repository.",
            "",
            "## Files",
            "",
            "- `endpoints.json`: machine-readable local API manifest.",
            "- `openapi.json`: OpenAPI 3.1 contract for HTTP clients and tool generation.",
            "- `python_client.py`: dependency-free Python HTTP example.",
            "- `node_client.mjs`: dependency-free Node 18+ HTTP example.",
            "- `env.example`: shell environment for daemon URL, local store, and optional auth token.",
            "- `smoke.sh`: offline kit validation that does not require the daemon.",
            "",
            "## First Run",
            "",
            "```bash",
            "abb start",
            ". env.example",
            "python3 python_client.py",
            "node node_client.mjs",
            "```",
            "",
            "If `ABB_AUTH_TOKEN` is set, clients send it as a bearer token.",
            "",
            "## Required HTTP Flow",
            "",
            "1. Read `/v1/openapi.json` or `openapi.json` before writing client calls.",
            "2. `POST /v1/runs` with name, source, tags, and metadata.",
            "3. `POST /v1/spans` around model calls, tool calls, graph nodes, or agent steps.",
            "4. `POST /v1/artifacts` for prompts, responses, tool inputs, tool outputs, schemas, and notes.",
            "5. `POST /v1/events` for important observations and state changes.",
            "6. `POST /v1/spans/{span_id}/end` and `POST /v1/runs/{run_id}/end` when work completes.",
            "7. `GET /v1/runs/{run_id}/timeline` to verify what was recorded.",
            "",
            "## After Recording",
            "",
            "```bash",
            "abb show RUN_ID",
            "abb compare-export RUN_ID --format json",
            "abb handoff RUN_ID",
            "abb support RUN_ID",
            "```",
            "",
            "`abb support RUN_ID` is the smallest useful folder to send back for debugging. Use `--include-bundle` only when artifact payloads can be shared.",
            "",
            "## Privacy",
            "",
            "Agent Black Box is local-first. It does not add hosted telemetry. Redaction catches obvious secrets, but inspect artifacts before sharing support packets or `.abb` bundles.",
            "",
        ]
    )


def _agent_kit_readme(manifest: Dict[str, Any]) -> str:
    return "\n".join(
        [
            "Agent Black Box Agent Kit",
            "",
            f"Kit: {manifest['kit_id']}",
            f"Created: {manifest['created_at']}",
            f"Daemon URL: {manifest['daemon_url']}",
            "",
            "Start here:",
            "1. Run `sh smoke.sh` to verify this kit is intact.",
            "2. Start Agent Black Box with `abb start`.",
            "3. Source env with `. env.example`.",
            "4. Run `python3 python_client.py` or `node node_client.mjs`.",
            "",
            "Send back on failure:",
            "- The command and exact error text.",
            "- `abb doctor --json` output.",
            "- The generated run_id, if one was created.",
            "- `abb support RUN_ID` when a run exists.",
            "",
            "Files:",
            "- AGENT_BLACK_BOX.md",
            "- endpoints.json",
            "- openapi.json",
            "- python_client.py",
            "- node_client.mjs",
            "- env.example",
            "- smoke.sh",
            "- agent-kit.json",
            "",
        ]
    )


def _agent_kit_smoke_text() -> str:
    return "\n".join(
        [
            "#!/usr/bin/env sh",
            "set -eu",
            "KIT_DIR=\"$(CDPATH= cd -- \"$(dirname -- \"$0\")\" && pwd)\"",
            "PYTHON_BIN=\"${PYTHON:-python3}\"",
            "",
            "\"$PYTHON_BIN\" -m json.tool \"$KIT_DIR/endpoints.json\" >/dev/null",
            "\"$PYTHON_BIN\" -m json.tool \"$KIT_DIR/openapi.json\" >/dev/null",
            "\"$PYTHON_BIN\" -m json.tool \"$KIT_DIR/agent-kit.json\" >/dev/null",
            "\"$PYTHON_BIN\" \"$KIT_DIR/python_client.py\" --help >/dev/null",
            "if command -v node >/dev/null 2>&1; then",
            "  node \"$KIT_DIR/node_client.mjs\" --help >/dev/null",
            "else",
            "  printf 'SKIP node client help: node is not installed\\n'",
            "fi",
            "printf 'Agent Black Box agent kit is readable. Start abb start before live client calls.\\n'",
            "",
        ]
    )


def _fallback_python_client() -> str:
    return "\n".join(
        [
            "from __future__ import annotations",
            "",
            "import sys",
            "",
            "if '--help' in sys.argv:",
            "    print('Start abb start, then use /v1/openapi.json and /v1/runs to record traces.')",
            "    raise SystemExit(0)",
            "raise SystemExit('examples/http_agent_client.py was not packaged with this install.')",
            "",
        ]
    )


def _fallback_node_client() -> str:
    return "\n".join(
        [
            "if (process.argv.includes('--help')) {",
            "  console.log('Start abb start, then use /v1/openapi.json and /v1/runs to record traces.');",
            "  process.exit(0);",
            "}",
            "throw new Error('examples/js-agent-client.mjs was not packaged with this install.');",
            "",
        ]
    )
