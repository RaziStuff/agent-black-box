#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any, Dict, Iterable, List, Optional


ROOT = Path(__file__).resolve().parents[1]
READINESS_VERSION = "0.1"
SHIP = "SHIP"
SHIP_WITH_KNOWN_SKIPS = "SHIP WITH KNOWN SKIPS"
DO_NOT_SHIP = "DO NOT SHIP"


@dataclass
class StepResult:
    name: str
    status: str
    command: List[str]
    returncode: Optional[int]
    started_at: str
    ended_at: str
    duration_seconds: float
    stdout: str
    stderr: str


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_readiness_report(args)
    if not args.no_report:
        write_reports(report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_human_summary(report)

    if report["final_status"] == DO_NOT_SHIP:
        return 1
    if args.strict and report["final_status"] != SHIP:
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Agent Black Box alpha release readiness checks and write a ship/no-ship report."
    )
    parser.add_argument("--python", default=sys.executable, help="Python executable to use for checks.")
    parser.add_argument("--report-dir", default=".abb-release", help="Directory for readiness reports.")
    parser.add_argument("--skip-smoke", action="store_true", help="Skip the full smoke suite.")
    parser.add_argument("--browser-required", action="store_true", help="Require rendered browser smoke to pass.")
    parser.add_argument("--node-required", action="store_true", help="Require the Node HTTP client smoke to pass.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero for known skips or warnings.")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report.")
    parser.add_argument("--no-report", action="store_true", help="Do not write report files.")
    return parser


def build_readiness_report(args: argparse.Namespace) -> Dict[str, Any]:
    now = datetime.utcnow()
    stamp = format_utc(now)
    path_stamp = format_file_stamp(now)
    report_dir = resolve_report_dir(args.report_dir)
    report_paths = {
        "json": str(report_dir / f"readiness-{path_stamp}.json"),
        "text": str(report_dir / f"readiness-{path_stamp}.txt"),
        "smoke_home": str(report_dir / f"smoke-{path_stamp}"),
    }
    env = os.environ.copy()
    env["PYTHONPYCACHEPREFIX"] = str(ROOT / ".pycache")

    static_checks = collect_static_checks(ROOT)
    steps: List[StepResult] = []
    steps.append(
        run_step(
            "compile",
            [
                args.python,
                "-m",
                "compileall",
                "src",
                "examples",
                "tests",
                "scripts/browser-smoke.py",
                "scripts/http-client-smoke.py",
                "scripts/build-release.py",
                "scripts/feedback-summary.py",
                "scripts/prepare-design-partner-send.py",
                "scripts/rank-design-partners.py",
                "scripts/release-readiness.py",
            ],
            env,
        )
    )
    steps.append(run_step("unit tests", [args.python, "-m", "unittest", "discover", "-s", "tests"], env))
    steps.append(run_step("release artifacts", [args.python, "scripts/build-release.py", "--no-verify", "--json"], env))
    steps.append(run_step("smoke script syntax", ["sh", "-n", "scripts/smoke.sh"], env))
    steps.append(run_step("alpha demo syntax", ["sh", "-n", "scripts/alpha-demo.sh"], env))

    if args.skip_smoke:
        steps.append(skipped_step("full smoke", "Skipped by --skip-smoke."))
    else:
        smoke_env = env.copy()
        smoke_env["PYTHON"] = args.python
        smoke_env["ABB_SMOKE_HOME"] = report_paths["smoke_home"]
        if args.browser_required:
            smoke_env["ABB_BROWSER_SMOKE_REQUIRED"] = "1"
        steps.append(run_step("full smoke", ["sh", "scripts/smoke.sh"], smoke_env))

    if args.node_required:
        steps.append(
            run_step(
                "required Node HTTP smoke",
                [args.python, "scripts/http-client-smoke.py", "--required", "--node-required"],
                env,
            )
        )

    known_skips = collect_known_skips(steps)
    warnings = collect_warnings(steps)
    final_status = derive_final_status(steps, static_checks, known_skips, warnings)
    return {
        "readiness_version": READINESS_VERSION,
        "created_at": stamp,
        "root": str(ROOT),
        "python": args.python,
        "strict": args.strict,
        "final_status": final_status,
        "summary": {
            "steps_ok": sum(1 for step in steps if step.status == "ok"),
            "steps_skipped": sum(1 for step in steps if step.status == "skipped"),
            "steps_error": sum(1 for step in steps if step.status == "error"),
            "static_ok": sum(1 for check in static_checks if check["status"] == "ok"),
            "static_error": sum(1 for check in static_checks if check["status"] == "error"),
            "known_skips": len(known_skips),
            "warnings": len(warnings),
        },
        "known_skips": known_skips,
        "warnings": warnings,
        "static_checks": static_checks,
        "steps": [asdict(step) for step in steps],
        "report_paths": report_paths,
    }


def run_step(name: str, command: List[str], env: Dict[str, str]) -> StepResult:
    started = utc_stamp()
    start = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=str(ROOT),
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        status = "ok" if completed.returncode == 0 else "error"
        return StepResult(
            name=name,
            status=status,
            command=command,
            returncode=completed.returncode,
            started_at=started,
            ended_at=utc_stamp(),
            duration_seconds=round(time.monotonic() - start, 3),
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    except Exception as exc:
        return StepResult(
            name=name,
            status="error",
            command=command,
            returncode=None,
            started_at=started,
            ended_at=utc_stamp(),
            duration_seconds=round(time.monotonic() - start, 3),
            stdout="",
            stderr=str(exc),
        )


def skipped_step(name: str, reason: str) -> StepResult:
    now = utc_stamp()
    return StepResult(
        name=name,
        status="skipped",
        command=[],
        returncode=None,
        started_at=now,
        ended_at=now,
        duration_seconds=0.0,
        stdout=reason,
        stderr="",
    )


def collect_static_checks(root: Path) -> List[Dict[str, str]]:
    checks: List[Dict[str, str]] = []
    required_files = [
        "README.md",
        "docs/RELEASE_CHECKLIST.md",
        "docs/LOCAL_ALPHA_CHECKLIST.md",
        "docs/API_REFERENCE.md",
        "docs/DESIGN_PARTNER_INTAKE.md",
        "docs/DESIGN_PARTNER_INTAKE.csv",
        "docs/DESIGN_PARTNER_FIRST_SEND_PACKET.md",
        "docs/DESIGN_PARTNER_HANDOFF.md",
        "docs/DESIGN_PARTNER_OUTREACH.md",
        "docs/DESIGN_PARTNER_FEEDBACK_FORM.md",
        "docs/DESIGN_PARTNER_TRACKER.md",
        "docs/DESIGN_PARTNER_TRACKER.csv",
        "docs/TROUBLESHOOTING.md",
        "docs/KNOWN_LIMITATIONS.md",
        "docs/AGENT_INTEGRATION_PROMPT.md",
        "examples/http_agent_client.py",
        "examples/js-agent-client.mjs",
        "scripts/smoke.sh",
        "scripts/http-client-smoke.py",
        "scripts/browser-smoke.py",
        "scripts/build-release.py",
        "scripts/feedback-summary.py",
        "scripts/prepare-design-partner-send.py",
        "scripts/rank-design-partners.py",
    ]
    for rel_path in required_files:
        path = root / rel_path
        checks.append(
            {
                "name": f"file:{rel_path}",
                "status": "ok" if path.exists() else "error",
                "message": "present" if path.exists() else "missing",
            }
        )

    content_checks = {
        "README.md": ["scripts/release-readiness.py", "scripts/smoke.sh", "scripts/build-release.py", "scripts/rank-design-partners.py", "scripts/prepare-design-partner-send.py", "scripts/feedback-summary.py", "design-partner.zip", "DESIGN_PARTNER_INTAKE.md", "DESIGN_PARTNER_FIRST_SEND_PACKET.md", "DESIGN_PARTNER_OUTREACH.md", "DESIGN_PARTNER_FEEDBACK_FORM.md", "DESIGN_PARTNER_TRACKER.md", "abb doctor", "abb agent-kit", "abb delete RUN_ID --yes", "DELETE /v1/runs/RUN_ID", "--zip", "/v1/agent-kit"],
        "docs/API_REFERENCE.md": ["/v1/agent-kit", "agent-kit.json", "AGENT_BLACK_BOX.md", "zip_path", "sha256", "DELETE", "/v1/runs/{run_id}", "keep_exports"],
        "docs/RELEASE_CHECKLIST.md": [SHIP, SHIP_WITH_KNOWN_SKIPS, DO_NOT_SHIP, "scripts/build-release.py", "scripts/rank-design-partners.py", "scripts/prepare-design-partner-send.py", "scripts/feedback-summary.py", "DESIGN_PARTNER_INTAKE.md", "DESIGN_PARTNER_FIRST_SEND_PACKET.md", "DESIGN_PARTNER_OUTREACH.md", "DESIGN_PARTNER_FEEDBACK_FORM.md", "DESIGN_PARTNER_TRACKER.md", "design-partner.zip", "release-manifest.json", "abb delete RUN_ID --yes", "DELETE /v1/runs/RUN_ID", "abb agent-kit --json", "abb agent-kit --zip", "/v1/agent-kit"],
        "docs/LOCAL_ALPHA_CHECKLIST.md": ["scripts/release-readiness.py", "scripts/build-release.py", "scripts/rank-design-partners.py", "scripts/prepare-design-partner-send.py", "scripts/feedback-summary.py", "DESIGN_PARTNER_INTAKE.csv", "DESIGN_PARTNER_FIRST_SEND_PACKET.md", "DESIGN_PARTNER_OUTREACH.md", "DESIGN_PARTNER_FEEDBACK_FORM.md", "DESIGN_PARTNER_TRACKER.csv", "design-partner.zip", "release-manifest.json", "abb support RUN_ID", "abb agent-kit --json", "abb agent-kit --zip", "/v1/agent-kit"],
        "docs/DESIGN_PARTNER_INTAKE.md": ["Score Fields", "Dealbreakers", "Selection Rule", "active_agent_workflow", "scripts/rank-design-partners.py", ".abb-send/design-partner-ranking.md"],
        "docs/DESIGN_PARTNER_INTAKE.csv": ["candidate_id,contact,segment", "active_agent_workflow", "debugging_pain", "privacy_fit", "AGENT_FOUNDER_NAME"],
        "docs/DESIGN_PARTNER_FIRST_SEND_PACKET.md": ["Partner Selection", "DESIGN_PARTNER_INTAKE.csv", "scripts/rank-design-partners.py", "Follow-Up Schedule", "Partner-Level Rubric", "Cohort Decision Rubric", "Support Artifact Order", "scripts/prepare-design-partner-send.py", ".abb-send/", "dp-001", "ready_next_partner", "ship_next_alpha"],
        "docs/DESIGN_PARTNER_HANDOFF.md": ["design-partner.zip", "DESIGN_PARTNER_INTAKE.md", "DESIGN_PARTNER_FIRST_SEND_PACKET.md", "DESIGN_PARTNER_OUTREACH.md", "DESIGN_PARTNER_FEEDBACK_FORM.md", "DESIGN_PARTNER_TRACKER.md", "sh install.sh", "FIRST_USER_WORKFLOW.md", "Privacy Reminder", "Stop Conditions"],
        "docs/DESIGN_PARTNER_OUTREACH.md": ["Subject:", "agent-black-box-0.1.0-design-partner.zip", "SHA-256", "scripts/rank-design-partners.py", "scripts/prepare-design-partner-send.py", "DESIGN_PARTNER_INTAKE.md", "DESIGN_PARTNER_FIRST_SEND_PACKET.md", "DESIGN_PARTNER_FEEDBACK_FORM.md", "DESIGN_PARTNER_TRACKER.csv", "Internal Send Checklist"],
        "docs/DESIGN_PARTNER_FEEDBACK_FORM.md": ["Workflow Completion", "Scores", "Privacy And Sharing", "Support Artifacts", "abb support RUN_ID"],
        "docs/DESIGN_PARTNER_TRACKER.md": ["Status Values", "DESIGN_PARTNER_INTAKE.md", "DESIGN_PARTNER_FIRST_SEND_PACKET.md", "artifact_sha256", "support_packet_path", "next_follow_up_at", "decision"],
        "docs/DESIGN_PARTNER_TRACKER.csv": ["partner_id,contact,segment", "AGENT_FOUNDER_NAME", "AGENT_INFRA_NAME", "LOCAL_AUTOMATION_NAME", "artifact_sha256", "SHA256_FROM_RELEASE_MANIFEST", "next_follow_up_at", "decision"],
        "docs/FIRST_USER_WORKFLOW.md": ["design-partner.zip", "sh install.sh", "abb agent-kit --zip", "release-manifest.json", "DESIGN_PARTNER_FEEDBACK_FORM.md"],
        "src/agent_black_box/cli.py": ["agent-kit", "delete", "keep-exports", "TROUBLESHOOTING.txt", "KNOWN_LIMITATIONS.txt"],
        "src/agent_black_box/daemon.py": ["Agent Kit", "/v1/agent-kit", "agent-kit-button", "agent-kit-zip", "delete-run-button", "DELETE"],
        "scripts/build-release.py": ["py3-none-any.whl", "tar.gz", "design-partner.zip", "QUICKSTART.md", "release-manifest.json", "sha256", "pip install --no-index"],
        "scripts/feedback-summary.py": ["Workflow Completion", "possible_redaction_issue", "Design Partner Feedback Summary", "suggested_actions"],
        "scripts/prepare-design-partner-send.py": ["design_partner_kit", "DESIGN_PARTNER_TRACKER", "AGENT_FOUNDER_NAME", "next_business_day", ".abb-send/design-partner-send-queue.md"],
        "scripts/rank-design-partners.py": ["SCORE_FIELDS", "CORE_SEGMENTS", "disqualified", "low_signal", "Design Partner Candidate Ranking"],
        "scripts/smoke.sh": ["agent-kit", "--zip", "/v1/agent-kit", "DELETE", "abb delete", "sha256", "TROUBLESHOOTING.txt", "KNOWN_LIMITATIONS.txt", "scripts/http-client-smoke.py"],
        "examples/http_agent_client.py": ["/v1/openapi.json", "/v1/runs"],
        "examples/js-agent-client.mjs": ["/v1/openapi.json", "/v1/runs"],
    }
    for rel_path, needles in content_checks.items():
        checks.append(check_contains(root / rel_path, rel_path, needles))
    return checks


def check_contains(path: Path, rel_path: str, needles: Iterable[str]) -> Dict[str, str]:
    if not path.exists():
        return {"name": f"content:{rel_path}", "status": "error", "message": "file missing"}
    text = path.read_text(encoding="utf-8")
    missing = [needle for needle in needles if needle not in text]
    if missing:
        return {
            "name": f"content:{rel_path}",
            "status": "error",
            "message": "missing: " + ", ".join(missing),
        }
    return {"name": f"content:{rel_path}", "status": "ok", "message": "required content present"}


def collect_known_skips(steps: List[StepResult]) -> List[str]:
    skips: List[str] = []
    for step in steps:
        if step.status == "skipped":
            skips.append(f"{step.name}: {step.stdout.strip()}")
        for line in (step.stdout + "\n" + step.stderr).splitlines():
            stripped = line.strip()
            if stripped.startswith("SKIP "):
                skips.append(f"{step.name}: {stripped}")
    return dedupe(skips)


def collect_warnings(steps: List[StepResult]) -> List[str]:
    warnings: List[str] = []
    for step in steps:
        combined = step.stdout + "\n" + step.stderr
        if "Status: warning" in combined:
            warnings.append(f"{step.name}: doctor reported warning status")
    return dedupe(warnings)


def derive_final_status(
    steps: List[StepResult],
    static_checks: List[Dict[str, str]],
    known_skips: List[str],
    warnings: List[str],
) -> str:
    if any(step.status == "error" for step in steps):
        return DO_NOT_SHIP
    if any(check["status"] == "error" for check in static_checks):
        return DO_NOT_SHIP
    if known_skips or warnings:
        return SHIP_WITH_KNOWN_SKIPS
    return SHIP


def write_reports(report: Dict[str, Any]) -> None:
    paths = report["report_paths"]
    json_path = Path(paths["json"])
    text_path = Path(paths["text"])
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    text_path.write_text(render_text_report(report), encoding="utf-8")


def print_human_summary(report: Dict[str, Any]) -> None:
    print(render_text_report(report).rstrip())


def render_text_report(report: Dict[str, Any]) -> str:
    lines = [
        "Agent Black Box Release Readiness",
        "",
        f"Status: {report['final_status']}",
        f"Created: {report['created_at']}",
        f"Root: {report['root']}",
        "",
        "Steps:",
    ]
    for step in report["steps"]:
        duration = f"{step['duration_seconds']:.3f}s"
        command = " ".join(shlex.quote(part) for part in step["command"]) if step["command"] else "(none)"
        lines.append(f"- [{step['status']}] {step['name']} ({duration})")
        lines.append(f"  command: {command}")
        if step["status"] == "error":
            lines.extend(indent_tail("  stderr: ", step["stderr"]))
            lines.extend(indent_tail("  stdout: ", step["stdout"]))

    lines.extend(["", "Static Checks:"])
    for check in report["static_checks"]:
        lines.append(f"- [{check['status']}] {check['name']}: {check['message']}")

    if report["known_skips"]:
        lines.extend(["", "Known Skips:"])
        for skip in report["known_skips"]:
            lines.append(f"- {skip}")

    if report["warnings"]:
        lines.extend(["", "Warnings:"])
        for warning in report["warnings"]:
            lines.append(f"- {warning}")

    lines.extend(
        [
            "",
            "Reports:",
            f"- JSON: {report['report_paths']['json']}",
            f"- Text: {report['report_paths']['text']}",
            f"- Smoke store: {report['report_paths']['smoke_home']}",
            "",
        ]
    )
    return "\n".join(lines)


def indent_tail(prefix: str, text: str, limit: int = 12) -> List[str]:
    if not text.strip():
        return [prefix + "(empty)"]
    lines = text.rstrip().splitlines()[-limit:]
    return [prefix + lines[0]] + [" " * len(prefix) + line for line in lines[1:]]


def resolve_report_dir(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path


def utc_stamp() -> str:
    return format_utc(datetime.utcnow())


def format_utc(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def format_file_stamp(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%SZ")


def dedupe(values: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
