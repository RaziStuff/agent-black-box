#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, Optional
from urllib import request
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from agent_black_box.daemon import serve_in_thread
from agent_black_box.storage import ABBStore


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run live HTTP client smoke tests against an in-process daemon.")
    parser.add_argument("--data-dir", help="Data directory to use for the smoke store.")
    parser.add_argument("--keep-data", action="store_true", help="Keep the generated smoke store.")
    parser.add_argument("--token", default="http-client-smoke-token", help="Bearer token used to exercise authenticated clients.")
    parser.add_argument("--skip-node", action="store_true", help="Do not run the Node.js client even if node is available.")
    parser.add_argument(
        "--required",
        action="store_true",
        help="Fail instead of skipping when the local daemon or Python HTTP client cannot run.",
    )
    parser.add_argument(
        "--node-required",
        action="store_true",
        help="Fail instead of skipping when node is unavailable or too old.",
    )
    args = parser.parse_args(argv)

    store_dir = Path(args.data_dir) if args.data_dir else Path(tempfile.mkdtemp(prefix="abb-http-client-smoke-"))
    store_dir.mkdir(parents=True, exist_ok=True)
    store = ABBStore(store_dir)
    server = None
    thread = None
    try:
        server, thread = serve_in_thread(store, host="127.0.0.1", port=0, auth_token=args.token)
        url = f"http://127.0.0.1:{server.server_port}"
        python_result = _run_json_command(
            [
                sys.executable,
                str(ROOT / "examples" / "http_agent_client.py"),
                "--url",
                url,
                "--token",
                args.token,
            ]
        )
        _verify_recorded_run(store, python_result, source="http-python-example", language="python")
        print(f"Python HTTP client smoke passed: {python_result['run_id']}")

        kit_result = _create_agent_kit_over_http(url, args.token, store.root / "agent-kit-http")
        _verify_agent_kit(kit_result)
        print(f"Agent kit HTTP smoke passed: {kit_result['kit_id']}")

        node_status = "skipped"
        if not args.skip_node:
            node_status = _run_node_client(store, url, args.token, required=args.node_required)
        else:
            print("SKIP Node HTTP client smoke: --skip-node was provided")

        print(
            json.dumps(
                {
                    "status": "ok",
                    "url": url,
                    "python_run_id": python_result["run_id"],
                    "agent_kit_id": kit_result["kit_id"],
                    "node": node_status,
                    "data_dir": str(store.root),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        return _skip_or_fail(args.required, f"HTTP client smoke could not run: {exc}")
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=2)
        store.close()
        if not args.keep_data and not args.data_dir:
            shutil.rmtree(store_dir, ignore_errors=True)


def _run_node_client(store: ABBStore, url: str, token: str, required: bool) -> str:
    node = shutil.which("node")
    if not node:
        return _skip_or_fail_node(required, "node is not installed")
    version = _node_major_version(node)
    if version is None:
        return _skip_or_fail_node(required, "could not determine node version")
    if version < 18:
        return _skip_or_fail_node(required, f"node {version} is too old; Node.js 18 or newer is required")
    result = _run_json_command(
        [
            node,
            str(ROOT / "examples" / "js-agent-client.mjs"),
            "--url",
            url,
            "--token",
            token,
        ]
    )
    _verify_recorded_run(store, result, source="http-js-example", language="javascript")
    print(f"Node HTTP client smoke passed: {result['run_id']}")
    return f"ok:{result['run_id']}"


def _node_major_version(node: str) -> Optional[int]:
    completed = subprocess.run([node, "--version"], cwd=ROOT, text=True, capture_output=True, timeout=10)
    if completed.returncode != 0:
        return None
    match = re.search(r"v(\d+)", completed.stdout.strip())
    return int(match.group(1)) if match else None


def _run_json_command(command: list[str]) -> Dict[str, Any]:
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=30)
    if completed.returncode != 0:
        raise RuntimeError(
            f"{' '.join(command)} exited {completed.returncode}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{' '.join(command)} did not print JSON: {completed.stdout}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{' '.join(command)} printed non-object JSON")
    return payload


def _create_agent_kit_over_http(url: str, token: str, output: Path) -> Dict[str, Any]:
    payload = json.dumps({"output": str(output), "force": True, "zip": True}).encode("utf-8")
    http_request = request.Request(
        url + "/v1/agent-kit",
        data=payload,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    with request.urlopen(http_request, timeout=10) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not isinstance(result, dict):
        raise RuntimeError(f"agent kit endpoint returned non-object JSON: {result}")
    return result


def _verify_agent_kit(result: Dict[str, Any]) -> None:
    if result.get("agent_kit_version") != "0.1":
        raise RuntimeError(f"unexpected agent kit version: {result}")
    if result.get("api", {}).get("service") != "agent-black-box":
        raise RuntimeError(f"agent kit manifest did not include service metadata: {result}")
    files = result.get("files") or {}
    for key in ["manifest", "guide", "endpoints", "openapi", "python_client", "node_client", "env", "smoke"]:
        path = Path(files.get(key, ""))
        if not path.exists():
            raise RuntimeError(f"agent kit missing {key}: {path}")
    archive = result.get("archive") or {}
    zip_path = Path(archive.get("path", ""))
    if not zip_path.exists():
        raise RuntimeError(f"agent kit zip was not created: {archive}")
    if archive.get("sha256") != hashlib.sha256(zip_path.read_bytes()).hexdigest():
        raise RuntimeError(f"agent kit zip checksum mismatch: {archive}")
    with zipfile.ZipFile(zip_path) as zipped:
        names = set(zipped.namelist())
        smoke_mode = zipped.getinfo("smoke.sh").external_attr >> 16
    required = {
        "README.txt",
        "AGENT_BLACK_BOX.md",
        "endpoints.json",
        "openapi.json",
        "python_client.py",
        "node_client.mjs",
        "env.example",
        "smoke.sh",
        "agent-kit.json",
    }
    if names != required:
        raise RuntimeError(f"agent kit zip contents mismatch: {names}")
    if not smoke_mode & 0o111:
        raise RuntimeError("agent kit smoke.sh was not executable in the zip")


def _verify_recorded_run(store: ABBStore, result: Dict[str, Any], source: str, language: str) -> None:
    run_id = result.get("run_id")
    span_id = result.get("span_id")
    artifact_id = result.get("artifact_id")
    if not run_id or not span_id or not artifact_id:
        raise RuntimeError(f"client result did not include run/span/artifact IDs: {result}")
    timeline = store.get_timeline(run_id)
    run = timeline["run"]
    if run["source"] != source:
        raise RuntimeError(f"expected source {source}, got {run['source']}")
    if run["status"] != "ok":
        raise RuntimeError(f"expected run {run_id} to be ok, got {run['status']}")
    if not any(span["span_id"] == span_id and span["status"] == "ok" for span in timeline["spans"]):
        raise RuntimeError(f"span {span_id} was not recorded as ok")
    if not any(artifact["artifact_id"] == artifact_id and artifact["kind"] == "agent.note" for artifact in timeline["artifacts"]):
        raise RuntimeError(f"artifact {artifact_id} was not recorded as agent.note")
    if not any(event["type"] == "agent.observation" for event in timeline["events"]):
        raise RuntimeError(f"run {run_id} did not include an agent.observation event")
    counts = result.get("timeline_counts") or {}
    if counts.get("spans", 0) < 1 or counts.get("events", 0) < 1 or counts.get("artifacts", 0) < 1:
        raise RuntimeError(f"client result had bad timeline counts: {counts}")
    artifact_content = store.read_artifact(artifact_id) or b""
    artifact_text = artifact_content.decode("utf-8", errors="replace")
    if f'"client": "{language}"' not in artifact_text:
        raise RuntimeError(f"artifact {artifact_id} did not include client language {language}")


def _skip_or_fail(required: bool, message: str) -> int:
    prefix = "FAIL" if required else "SKIP"
    print(f"{prefix} HTTP client smoke: {message}")
    return 1 if required else 0


def _skip_or_fail_node(required: bool, message: str) -> str:
    if required:
        raise RuntimeError(f"Node HTTP client smoke required but skipped: {message}")
    print(f"SKIP Node HTTP client smoke: {message}")
    return f"skipped:{message}"


if __name__ == "__main__":
    raise SystemExit(main())
