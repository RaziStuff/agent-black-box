#!/usr/bin/env python3
"""Prepare checksum-filled design-partner send drafts from a release manifest."""

from __future__ import annotations

import argparse
import csv
from datetime import date, timedelta
import io
import json
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, List, Optional


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ".abb-send/design-partner-send-queue.md"
DEFAULT_TRACKER_OUTPUT = ".abb-send/design-partner-tracker-rows.csv"

TRACKER_FIELDS = [
    "partner_id",
    "contact",
    "segment",
    "artifact_sent",
    "artifact_sha256",
    "sent_at",
    "status",
    "current_step",
    "installed_at",
    "workflow_completed_at",
    "feedback_path",
    "support_packet_path",
    "handoff_path",
    "bundle_path",
    "blocker",
    "next_follow_up_at",
    "owner",
    "decision",
    "notes",
]

PARTNERS = [
    {
        "partner_id": "dp-001",
        "contact": "AGENT_FOUNDER_NAME",
        "segment": "agent founder",
        "current_step": "send founder email",
        "notes": "replace contact then send founder draft",
    },
    {
        "partner_id": "dp-002",
        "contact": "AGENT_INFRA_NAME",
        "segment": "agent infra engineer",
        "current_step": "send infra email",
        "notes": "replace contact then send infra draft",
    },
    {
        "partner_id": "dp-003",
        "contact": "LOCAL_AUTOMATION_NAME",
        "segment": "local automation builder",
        "current_step": "send automation dm",
        "notes": "replace contact then send automation draft",
    },
]


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        send_date = parse_date(args.date)
        artifact = load_design_partner_artifact(Path(args.manifest))
        tracker_csv = format_tracker_csv(artifact, send_date, args.owner, mark_sent=args.mark_sent)
        markdown = format_send_queue(artifact, send_date, args.owner, tracker_csv, mark_sent=args.mark_sent)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Could not prepare design-partner send queue: {exc}", file=sys.stderr)
        return 1

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")

    tracker_output = Path(args.tracker_output)
    tracker_output.parent.mkdir(parents=True, exist_ok=True)
    tracker_output.write_text(tracker_csv, encoding="utf-8")

    summary = {
        "artifact": artifact["filename"],
        "sha256": artifact["sha256"],
        "send_date": send_date.isoformat(),
        "next_follow_up_at": next_business_day(send_date).isoformat(),
        "output": str(output),
        "tracker_output": str(tracker_output),
        "mark_sent": args.mark_sent,
    }
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(f"Wrote {output}")
        print(f"Wrote {tracker_output}")
        print(f"Artifact SHA-256: {artifact['sha256']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate checksum-filled first-send drafts and tracker rows for Agent Black Box design partners."
    )
    parser.add_argument("--manifest", default="dist/release-manifest.json", help="Path to release-manifest.json.")
    parser.add_argument("--date", help="Send date in YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--owner", default="YOUR_NAME", help="Owner name to put in tracker rows and message signoffs.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Markdown send queue output path.")
    parser.add_argument("--tracker-output", default=DEFAULT_TRACKER_OUTPUT, help="CSV tracker rows output path.")
    parser.add_argument("--mark-sent", action="store_true", help="Generate rows with status=sent and sent_at populated.")
    parser.add_argument("--json", action="store_true", help="Print a JSON summary.")
    return parser


def parse_date(raw: Optional[str]) -> date:
    if raw:
        return date.fromisoformat(raw)
    return date.today()


def load_design_partner_artifact(manifest_path: Path) -> Dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts", [])
    for artifact in artifacts:
        if artifact.get("kind") == "design_partner_kit":
            filename = artifact["filename"]
            sha256 = artifact["sha256"]
            if not filename.endswith("-design-partner.zip"):
                raise ValueError(f"design_partner_kit filename is unexpected: {filename}")
            if len(sha256) != 64:
                raise ValueError("design_partner_kit sha256 must be a 64-character hex digest")
            return artifact
    raise ValueError("release manifest does not contain a design_partner_kit artifact")


def next_business_day(start: date) -> date:
    candidate = start + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def tracker_rows(artifact: Dict[str, Any], send_date: date, owner: str, mark_sent: bool = False) -> List[Dict[str, str]]:
    next_follow_up = next_business_day(send_date).isoformat()
    rows: List[Dict[str, str]] = []
    for partner in PARTNERS:
        rows.append(
            {
                "partner_id": partner["partner_id"],
                "contact": partner["contact"],
                "segment": partner["segment"],
                "artifact_sent": artifact["filename"],
                "artifact_sha256": artifact["sha256"],
                "sent_at": send_date.isoformat() if mark_sent else "",
                "status": "sent" if mark_sent else "candidate",
                "current_step": partner["current_step"],
                "installed_at": "",
                "workflow_completed_at": "",
                "feedback_path": "",
                "support_packet_path": "",
                "handoff_path": "",
                "bundle_path": "",
                "blocker": "",
                "next_follow_up_at": next_follow_up if mark_sent else "",
                "owner": owner,
                "decision": "",
                "notes": partner["notes"],
            }
        )
    return rows


def format_tracker_csv(artifact: Dict[str, Any], send_date: date, owner: str, mark_sent: bool = False) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=TRACKER_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(tracker_rows(artifact, send_date, owner, mark_sent=mark_sent))
    return output.getvalue()


def format_send_queue(
    artifact: Dict[str, Any],
    send_date: date,
    owner: str,
    tracker_csv: str,
    mark_sent: bool = False,
) -> str:
    artifact_name = artifact["filename"]
    sha256 = artifact["sha256"]
    next_follow_up = next_business_day(send_date).isoformat()
    row_status = "sent" if mark_sent else "candidate"
    sent_at_note = send_date.isoformat() if mark_sent else "leave blank until the message is actually sent"
    follow_up_note = next_follow_up if mark_sent else "set to the next business day after sending"

    return f"""# Design Partner Send Queue

Generated from `dist/release-manifest.json`.

## Artifact

- File: `dist/{artifact_name}`
- SHA-256: `{sha256}`
- Prepared date: `{send_date.isoformat()}`
- Default next follow-up after send: `{next_follow_up}`

## Operator Notes

- Replace the three contact placeholders before sending.
- Keep `status={row_status}` until the message state changes.
- `sent_at`: {sent_at_note}.
- `next_follow_up_at`: {follow_up_note}.
- Attach only `dist/{artifact_name}`.
- Ask for `docs/DESIGN_PARTNER_FEEDBACK_FORM.md`, `abb support RUN_ID`, or `abb handoff RUN_ID` before any full `.abb` bundle.

## Tracker Rows

Paste these rows into `docs/DESIGN_PARTNER_TRACKER.csv` or another local tracker:

```csv
{tracker_csv.rstrip()}
```

## dp-001 Agent Founder Email

Subject: Local alpha: debug one real agent run with Agent Black Box

Hi AGENT_FOUNDER_NAME,

I am testing a local-first tool called Agent Black Box with three design
partners. It records AI agent runs on your machine so you can inspect what
happened, find the first useful debug point, compare request/response or
input/output artifacts, and export a compact handoff packet for another agent or
human.

I am not looking for a polished product review yet. I am trying to learn whether
this makes debugging one real agent workflow faster than logs and screenshots.

I attached:

- `{artifact_name}`

Checksum:

```text
SHA-256: {sha256}
```

To try it:

```bash
unzip {artifact_name}
cd {artifact_name.removesuffix(".zip")}
sh install.sh
. .venv/bin/activate
abb doctor
```

Then follow `docs/FIRST_USER_WORKFLOW.md`. If you only have 20 minutes, run the
demo workflow and tell me the first command or page that either helped or
confused you.

The most useful return artifacts are:

- `docs/DESIGN_PARTNER_FEEDBACK_FORM.md`
- `abb support RUN_ID`
- `abb handoff RUN_ID`

Privacy notes:

- Agent Black Box stores data locally by default in `.abb/`.
- `.handoff.json` files are compact summaries and do not include full artifact payloads.
- `.abb` bundles include artifact payloads and should be inspected before sharing.

Thank you,
{owner}

## dp-002 Infra Or Platform Engineer Email

Subject: Can you sanity-check a local-first agent trace handoff?

Hi AGENT_INFRA_NAME,

I am running a tiny design-partner loop for Agent Black Box, a local-first flight
recorder for agent runs. The wedge I want to test with you is whether the trace,
compare, support, handoff, and local API surfaces are useful enough for agents
and platform engineers to debug without sending data to a hosted service.

I attached the local alpha kit:

- `{artifact_name}`

Checksum:

```text
SHA-256: {sha256}
```

Install path:

```bash
unzip {artifact_name}
cd {artifact_name.removesuffix(".zip")}
sh install.sh
. .venv/bin/activate
abb doctor
abb endpoints --json
abb endpoints --openapi
```

Then follow `docs/FIRST_USER_WORKFLOW.md`, especially compare export, handoff
export, handoff ingest, support packet creation, and `abb agent-kit --zip`.

I am looking for blunt feedback on:

- Whether the local API and agent kit are easy for another agent to consume.
- Whether `.handoff.json` contains enough context without becoming a full trace archive.
- Whether support packets are the right default artifact when something breaks.
- Whether the privacy boundary is clear.

Useful return artifacts:

- `docs/DESIGN_PARTNER_FEEDBACK_FORM.md`
- `abb support RUN_ID`
- `abb export RUN_ID --format handoff`

Thank you,
{owner}

## dp-003 Local Automation Builder DM

I have a local alpha ready for Agent Black Box, a local-first flight recorder for
AI agent runs. It records runs locally, shows what happened, points to the first
debug path, and exports a compact handoff or support packet.

Can I send you `{artifact_name}`?

Checksum:

```text
SHA-256: {sha256}
```

The useful path is 20 to 40 minutes:

```bash
unzip {artifact_name}
cd {artifact_name.removesuffix(".zip")}
sh install.sh
. .venv/bin/activate
abb doctor
```

Then follow `docs/FIRST_USER_WORKFLOW.md` and return
`docs/DESIGN_PARTNER_FEEDBACK_FORM.md` or `abb support RUN_ID` if you hit a
blocker. Data stays local unless you choose to export or share a packet.

## Ten Minute Follow-Up

If you only have 10 minutes, please do this:

```bash
sh install.sh
. .venv/bin/activate
abb doctor
python3 examples/openai_wrapper_agent.py
abb runs
abb show RUN_ID
```

Then tell me:

- Did install and `abb doctor` work without help?
- Did `abb show RUN_ID` make the run easier to understand?
- What was the first confusing command, page, or concept?

## Blocked Follow-Up

Please do not send a full `.abb` bundle yet. The smallest useful debug artifacts are:

```bash
abb doctor --json
abb support RUN_ID
abb handoff RUN_ID
```

If there is no run ID yet, send the exact command, exact error output, Python
version, and whether this happened during install, doctor, CLI, browser, SDK,
HTTP API, proxy, or import/export.
"""


if __name__ == "__main__":
    raise SystemExit(main())
