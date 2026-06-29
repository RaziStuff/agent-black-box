#!/usr/bin/env python3
"""Build local alpha release artifacts without third-party build tools."""

from __future__ import annotations

import argparse
import ast
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from typing import Any, Dict, Iterable, List, Optional, Tuple
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
PACKAGE_ROOT = SRC_ROOT / "agent_black_box"
DIST_DIR = ROOT / "dist"
PACKAGE_NAME = "agent-black-box"
WHEEL_NAME = "agent_black_box"
SUMMARY = "Local-first flight recorder and replay debugger for AI agents."
REQUIRES_PYTHON = ">=3.9"
CONSOLE_SCRIPT = "abb = agent_black_box.cli:main"
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build Agent Black Box local alpha release artifacts.")
    parser.add_argument("--dist-dir", default=str(DIST_DIR), help="Directory for release artifacts.")
    parser.add_argument("--no-verify", action="store_true", help="Skip isolated wheel install verification.")
    parser.add_argument("--json", action="store_true", help="Print the machine-readable release manifest.")
    args = parser.parse_args(argv)

    try:
        manifest = build_release(Path(args.dist_dir), verify=not args.no_verify)
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"Release build failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0

    print("Agent Black Box release artifacts")
    print(f"Version: {manifest['version']}")
    for artifact in manifest["artifacts"]:
        print(f"- {artifact['kind']}: {artifact['path']}")
        print(f"  sha256: {artifact['sha256']}")
    print(f"Manifest: {manifest['manifest_path']}")
    print(f"Verification: {manifest['verification']['status']}")
    return 0


def build_release(dist_dir: Path = DIST_DIR, verify: bool = True) -> Dict[str, Any]:
    version = read_version()
    dist_dir.mkdir(parents=True, exist_ok=True)

    wheel_path = build_wheel(version, dist_dir)
    sdist_path = build_sdist(version, dist_dir)
    verification = verify_wheel(wheel_path) if verify else {"status": "skipped", "reason": "--no-verify"}
    wheel_record = artifact_record("wheel", wheel_path)
    sdist_record = artifact_record("sdist", sdist_path)
    partner_kit_path = build_design_partner_kit(version, dist_dir, wheel_path, sdist_path, [wheel_record, sdist_record])

    manifest_path = dist_dir / "release-manifest.json"
    manifest = {
        "package": PACKAGE_NAME,
        "version": version,
        "artifacts": [
            wheel_record,
            sdist_record,
            artifact_record("design_partner_kit", partner_kit_path),
        ],
        "manifest_path": str(manifest_path),
        "verification": verification,
        "commands": {
            "build": "python3 scripts/build-release.py",
            "install_wheel": f"python3 -m pip install --no-index --no-deps {wheel_path.name}",
            "smoke": "abb doctor && abb --help",
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def read_version() -> str:
    tree = ast.parse((PACKAGE_ROOT / "__init__.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__version__":
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        return node.value.value
    raise RuntimeError("Could not find agent_black_box.__version__")


def build_wheel(version: str, dist_dir: Path) -> Path:
    wheel_path = dist_dir / f"{WHEEL_NAME}-{version}-py3-none-any.whl"
    dist_info = f"{WHEEL_NAME}-{version}.dist-info"
    entries: List[Tuple[str, bytes]] = []

    for path in package_files():
        archive_name = path.relative_to(SRC_ROOT).as_posix()
        entries.append((archive_name, path.read_bytes()))

    entries.extend(
        [
            (f"{dist_info}/METADATA", metadata_text(version).encode("utf-8")),
            (f"{dist_info}/WHEEL", wheel_text().encode("utf-8")),
            (f"{dist_info}/entry_points.txt", entry_points_text().encode("utf-8")),
        ]
    )

    record_rows = [[name, f"sha256={hash_b64(data)}", str(len(data))] for name, data in entries]
    record_name = f"{dist_info}/RECORD"
    record_rows.append([record_name, "", ""])
    record_data = csv_record(record_rows)

    with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            write_zip_bytes(archive, name, data)
        write_zip_bytes(archive, record_name, record_data)
    return wheel_path


def build_sdist(version: str, dist_dir: Path) -> Path:
    sdist_path = dist_dir / f"{PACKAGE_NAME}-{version}.tar.gz"
    root_name = f"{PACKAGE_NAME}-{version}"
    with tarfile.open(sdist_path, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        for path in sdist_files():
            archive.add(path, arcname=f"{root_name}/{path.relative_to(ROOT).as_posix()}", recursive=False)
    return sdist_path


def build_design_partner_kit(
    version: str,
    dist_dir: Path,
    wheel_path: Path,
    sdist_path: Path,
    release_artifacts: List[Dict[str, Any]],
) -> Path:
    kit_path = dist_dir / f"{PACKAGE_NAME}-{version}-design-partner.zip"
    root_name = f"{PACKAGE_NAME}-{version}-design-partner"
    kit_manifest = {
        "package": PACKAGE_NAME,
        "version": version,
        "purpose": "local alpha design-partner handoff",
        "artifacts": release_artifacts,
        "commands": {
            "install": "sh install.sh",
            "activate": ". .venv/bin/activate",
            "doctor": "abb doctor",
            "workflow": "Follow docs/FIRST_USER_WORKFLOW.md",
        },
    }
    with zipfile.ZipFile(kit_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        write_zip_bytes(archive, f"{root_name}/QUICKSTART.md", design_partner_quickstart(version).encode("utf-8"))
        write_zip_bytes(archive, f"{root_name}/install.sh", design_partner_install_script().encode("utf-8"), mode=0o755)
        write_zip_bytes(
            archive,
            f"{root_name}/release-manifest.json",
            (json.dumps(kit_manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
        write_zip_bytes(archive, f"{root_name}/artifacts/{wheel_path.name}", wheel_path.read_bytes())
        write_zip_bytes(archive, f"{root_name}/artifacts/{sdist_path.name}", sdist_path.read_bytes())
        for path in partner_kit_files():
            archive_name = f"{root_name}/{path.relative_to(ROOT).as_posix()}"
            mode = 0o755 if os.access(path, os.X_OK) else 0o644
            write_zip_bytes(archive, archive_name, path.read_bytes(), mode=mode)
    return kit_path


def package_files() -> Iterable[Path]:
    return sorted(path for path in PACKAGE_ROOT.rglob("*.py") if path.is_file())


def partner_kit_files() -> Iterable[Path]:
    roots = [
        ROOT / "docs",
        ROOT / "examples",
        ROOT / "README.md",
        ROOT / "scripts" / "feedback-summary.py",
    ]
    for root in roots:
        if root.is_file():
            yield root
        elif root.is_dir():
            for path in sorted(root.rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    yield path


def sdist_files() -> Iterable[Path]:
    roots = [
        ROOT / "AGENT_BLACK_BOX_BUILD_PLAN.md",
        ROOT / "README.md",
        ROOT / "abb.py",
        ROOT / "pyproject.toml",
        ROOT / "docs",
        ROOT / "examples",
        ROOT / "scripts",
        ROOT / "src",
        ROOT / "tests",
    ]
    for root in roots:
        if root.is_file():
            yield root
        elif root.is_dir():
            for path in sorted(root.rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    yield path


def metadata_text(version: str) -> str:
    classifiers = [
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Topic :: Software Development :: Debuggers",
        "Topic :: Software Development :: Testing",
    ]
    lines = [
        "Metadata-Version: 2.1",
        f"Name: {PACKAGE_NAME}",
        f"Version: {version}",
        f"Summary: {SUMMARY}",
        f"Requires-Python: {REQUIRES_PYTHON}",
    ]
    lines.extend(f"Classifier: {classifier}" for classifier in classifiers)
    lines.append("Description-Content-Type: text/markdown")
    lines.append("")
    lines.append((ROOT / "README.md").read_text(encoding="utf-8"))
    return "\n".join(lines) + "\n"


def wheel_text() -> str:
    return "\n".join(
        [
            "Wheel-Version: 1.0",
            "Generator: agent-black-box build-release",
            "Root-Is-Purelib: true",
            "Tag: py3-none-any",
            "",
        ]
    )


def entry_points_text() -> str:
    return f"[console_scripts]\n{CONSOLE_SCRIPT}\n"


def design_partner_quickstart(version: str) -> str:
    return f"""# Agent Black Box {version} Design Partner Kit

This folder is a local alpha handoff. It includes:

- `artifacts/agent_black_box-{version}-py3-none-any.whl`
- `artifacts/agent-black-box-{version}.tar.gz`
- `release-manifest.json` with SHA-256 checksums
- first-user docs under `docs/`
- no-network demo examples under `examples/`

## Install

```bash
sh install.sh
. .venv/bin/activate
abb doctor
```

## Try The First Workflow

```bash
python3 examples/openai_wrapper_agent.py
python3 examples/langchain_callback_agent.py
python3 examples/langgraph_node_agent.py
python3 examples/tool_call_agent.py
abb record --name first-debug-run -- python3 examples/basic_agent.py
abb runs
```

Then follow `docs/FIRST_USER_WORKFLOW.md`.

After the workflow, fill out `docs/DESIGN_PARTNER_FEEDBACK_FORM.md`.

## Privacy

Data is written to `.abb/` inside this folder unless you set `ABB_HOME`.
Use `abb support RUN_ID` for compact support packets and inspect artifacts before
sharing `.abb` bundles.
"""


def design_partner_install_script() -> str:
    return """#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PYTHON_BIN="${PYTHON:-python3}"
VENV_DIR="${ABB_VENV:-"$ROOT_DIR/.venv"}"
WHEEL=""

for candidate in "$ROOT_DIR"/artifacts/agent_black_box-*-py3-none-any.whl; do
  WHEEL="$candidate"
  break
done

if [ ! -f "$WHEEL" ]; then
  printf 'No Agent Black Box wheel found under %s/artifacts\\n' "$ROOT_DIR" >&2
  exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

VENV_PYTHON="$VENV_DIR/bin/python"
VENV_ABB="$VENV_DIR/bin/abb"
ABB_HOME_DIR="${ABB_HOME:-$ROOT_DIR/.abb}"

export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_CACHE_DIR="$ROOT_DIR/.pip-cache"
"$VENV_PYTHON" -m pip install --no-index --no-deps "$WHEEL"

ABB_HOME="$ABB_HOME_DIR" "$VENV_ABB" doctor

cat <<EOF

Installed Agent Black Box from:
  $WHEEL

Next:
  . "$VENV_DIR/bin/activate"
  export ABB_HOME="$ABB_HOME_DIR"
  abb doctor
  python3 examples/openai_wrapper_agent.py
  abb runs

Then follow:
  docs/FIRST_USER_WORKFLOW.md
EOF
"""


def csv_record(rows: List[List[str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def write_zip_bytes(archive: zipfile.ZipFile, name: str, data: bytes, mode: int = 0o644) -> None:
    info = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = mode << 16
    archive.writestr(info, data)


def hash_b64(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def artifact_record(kind: str, path: Path) -> Dict[str, Any]:
    data = path.read_bytes()
    return {
        "kind": kind,
        "path": str(path),
        "filename": path.name,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    }


def verify_wheel(wheel_path: Path) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="abb-release-verify-") as tmp:
        tmp_path = Path(tmp)
        venv_dir = tmp_path / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        python = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        abb = venv_dir / ("Scripts/abb.exe" if os.name == "nt" else "bin/abb")
        env = os.environ.copy()
        env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        env["PIP_NO_INDEX"] = "1"
        env["PIP_CACHE_DIR"] = str(tmp_path / "pip-cache")
        subprocess.run(
            [str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel_path)],
            check=True,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        subprocess.run([str(abb), "--help"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        result = subprocess.run(
            [str(python), "-c", "import agent_black_box; print(agent_black_box.__version__)"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    return {"status": "passed", "version": result.stdout.strip()}


if __name__ == "__main__":
    raise SystemExit(main())
