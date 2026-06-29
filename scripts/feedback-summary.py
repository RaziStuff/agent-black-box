#!/usr/bin/env python3
"""Summarize design-partner Markdown feedback forms."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import statistics
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
FEEDBACK_VERSION = "0.1"
SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
FIELD_RE = re.compile(r"^-\s+([^:\n]+):\s*(.*)$")
CHECKBOX_RE = re.compile(r"^-\s+\[([ xX])\]\s+(.+?)\s*$")


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    paths = discover_feedback_paths(args.paths)
    if not paths:
        print("No feedback forms found.", file=sys.stderr)
        return 1

    report = summarize_feedback(paths)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report["output"] = str(output)
    if args.markdown:
        markdown = Path(args.markdown)
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(format_markdown_report(report), encoding="utf-8")
        report["markdown"] = str(markdown)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_markdown_report(report))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize returned Agent Black Box design-partner feedback forms.")
    parser.add_argument("paths", nargs="*", help="Feedback form files or directories to scan.")
    parser.add_argument("--output", help="Write JSON summary to this path.")
    parser.add_argument("--markdown", help="Write Markdown triage report to this path.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    return parser


def discover_feedback_paths(raw_paths: List[str]) -> List[Path]:
    if not raw_paths:
        raw_paths = ["docs/DESIGN_PARTNER_FEEDBACK_FORM.md"]
    paths: List[Path] = []
    for raw_path in raw_paths:
        path = Path(raw_path)
        if path.is_dir():
            paths.extend(sorted(candidate for candidate in path.rglob("*.md") if is_feedback_form(candidate)))
        elif path.is_file() and is_feedback_form(path):
            paths.append(path)
    return dedupe_paths(paths)


def is_feedback_form(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return "# Design Partner Feedback Form" in text and "## Workflow Completion" in text


def summarize_feedback(paths: Iterable[Path]) -> Dict[str, Any]:
    forms = [parse_feedback_form(path) for path in paths]
    return {
        "feedback_version": FEEDBACK_VERSION,
        "created_at": utc_now(),
        "form_count": len(forms),
        "forms": forms,
        "aggregate": aggregate_forms(forms),
        "triage": triage_forms(forms),
    }


def parse_feedback_form(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    sections = split_sections(text)
    reviewer = parse_fields(sections.get("Reviewer", ""))
    setup = parse_fields(sections.get("Setup", ""))
    scores = parse_scores(sections.get("Scores", ""))
    workflow_items = parse_checkboxes(sections.get("Workflow Completion", ""))
    debugging_value = parse_bullets(sections.get("Debugging Value", ""))
    privacy = parse_bullets(sections.get("Privacy And Sharing", ""))
    support = parse_support_artifacts(sections.get("Support Artifacts", ""))
    notes = {
        "most_useful_moment": first_code_block(sections.get("Most Useful Moment", "")),
        "first_confusing_moment": first_code_block(sections.get("First Confusing Moment", "")),
        "open_notes": first_code_block(sections.get("Open Notes", "")),
        "setup_error": first_code_block(sections.get("Setup", "")),
    }
    completed = sum(1 for item in workflow_items if item["checked"])
    completion_rate = round(completed / len(workflow_items), 3) if workflow_items else 0.0
    return {
        "path": str(path),
        "reviewer": reviewer,
        "setup": setup,
        "workflow": {
            "completed": completed,
            "total": len(workflow_items),
            "completion_rate": completion_rate,
            "items": workflow_items,
        },
        "scores": scores,
        "debugging_value": debugging_value,
        "privacy": privacy,
        "support": support,
        "notes": notes,
        "flags": form_flags(setup, scores, workflow_items, notes, privacy),
    }


def split_sections(text: str) -> Dict[str, str]:
    matches = list(SECTION_RE.finditer(text))
    sections: Dict[str, str] = {}
    for index, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[title] = text[start:end].strip()
    return sections


def parse_fields(section: str) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    for line in section.splitlines():
        match = FIELD_RE.match(line.strip())
        if match:
            fields[normalize_key(match.group(1))] = match.group(2).strip()
    return fields


def parse_scores(section: str) -> Dict[str, Optional[int]]:
    scores: Dict[str, Optional[int]] = {}
    for key, value in parse_fields(section).items():
        scores[key] = int(value) if value.isdigit() else None
    return scores


def parse_checkboxes(section: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for line in section.splitlines():
        match = CHECKBOX_RE.match(line.strip())
        if match:
            items.append({"label": match.group(2).strip(), "checked": match.group(1).lower() == "x"})
    return items


def parse_bullets(section: str) -> List[Dict[str, str]]:
    bullets = []
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and ":" not in stripped:
            bullets.append({"question": stripped[2:].strip(), "answer": ""})
        else:
            match = FIELD_RE.match(stripped)
            if match:
                bullets.append({"question": match.group(1).strip(), "answer": match.group(2).strip()})
    return bullets


def parse_support_artifacts(section: str) -> Dict[str, str]:
    return {"support_packet_path": first_code_block(section)}


def first_code_block(section: str) -> str:
    match = re.search(r"```(?:text)?\s*\n(.*?)\n```", section, flags=re.DOTALL)
    return match.group(1).strip() if match else ""


def form_flags(
    setup: Dict[str, str],
    scores: Dict[str, Optional[int]],
    workflow_items: List[Dict[str, Any]],
    notes: Dict[str, str],
    privacy: List[Dict[str, str]],
) -> List[str]:
    flags: List[str] = []
    for key, value in setup.items():
        normalized = value.lower()
        if normalized in {"no", "error"} or "error" in normalized:
            flags.append(f"setup:{key}={value}")
    for key, value in scores.items():
        if value is not None and value <= 2:
            flags.append(f"low_score:{key}={value}")
    incomplete = [item["label"] for item in workflow_items if not item["checked"]]
    if incomplete:
        flags.append(f"incomplete_workflow={len(incomplete)}")
    if notes.get("first_confusing_moment"):
        flags.append("has_confusion_note")
    for item in privacy:
        if "secret" in item["question"].lower() and "yes" in item["answer"].lower():
            flags.append("possible_redaction_issue")
    return flags


def aggregate_forms(forms: List[Dict[str, Any]]) -> Dict[str, Any]:
    score_values: Dict[str, List[int]] = {}
    completed_rates = []
    for form in forms:
        completed_rates.append(form["workflow"]["completion_rate"])
        for key, value in form["scores"].items():
            if isinstance(value, int):
                score_values.setdefault(key, []).append(value)
    score_averages = {
        key: round(statistics.mean(values), 2)
        for key, values in score_values.items()
        if values
    }
    return {
        "average_workflow_completion": round(statistics.mean(completed_rates), 3) if completed_rates else 0.0,
        "score_averages": score_averages,
        "total_flags": sum(len(form["flags"]) for form in forms),
    }


def triage_forms(forms: List[Dict[str, Any]]) -> Dict[str, Any]:
    flags: Dict[str, int] = {}
    confusion_notes = []
    useful_notes = []
    for form in forms:
        for flag in form["flags"]:
            flags[flag] = flags.get(flag, 0) + 1
        if form["notes"]["first_confusing_moment"]:
            confusion_notes.append({"path": form["path"], "text": form["notes"]["first_confusing_moment"]})
        if form["notes"]["most_useful_moment"]:
            useful_notes.append({"path": form["path"], "text": form["notes"]["most_useful_moment"]})
    return {
        "flags": dict(sorted(flags.items(), key=lambda item: (-item[1], item[0]))),
        "confusion_notes": confusion_notes,
        "useful_notes": useful_notes,
        "suggested_actions": suggested_actions(flags),
    }


def suggested_actions(flags: Dict[str, int]) -> List[str]:
    actions = []
    if any(flag.startswith("setup:") for flag in flags):
        actions.append("Review install and doctor setup instructions before adding features.")
    if any(flag.startswith("low_score:install_clarity") for flag in flags):
        actions.append("Tighten the install quickstart and first command sequence.")
    if any(flag.startswith("low_score:debug_path_usefulness") for flag in flags):
        actions.append("Improve Debug Path ranking, labels, or next-action text.")
    if any(flag.startswith("low_score:privacy_local_first_clarity") for flag in flags):
        actions.append("Clarify local storage, handoff, support, and bundle privacy boundaries.")
    if any(flag == "possible_redaction_issue" for flag in flags):
        actions.append("Pause sharing and inspect redaction before the next partner send.")
    if any(flag.startswith("incomplete_workflow=") for flag in flags):
        actions.append("Find the first incomplete workflow step and reduce friction there.")
    if not actions:
        actions.append("No blocking pattern found; read free-text notes for product opportunities.")
    return actions


def format_markdown_report(report: Dict[str, Any]) -> str:
    lines = [
        "# Design Partner Feedback Summary",
        "",
        f"Created: {report['created_at']}",
        f"Forms: {report['form_count']}",
        f"Average workflow completion: {report['aggregate']['average_workflow_completion']}",
        f"Total flags: {report['aggregate']['total_flags']}",
        "",
        "## Score Averages",
        "",
    ]
    if report["aggregate"]["score_averages"]:
        for key, value in report["aggregate"]["score_averages"].items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- No scored responses yet.")
    lines.extend(["", "## Flags", ""])
    if report["triage"]["flags"]:
        for key, count in report["triage"]["flags"].items():
            lines.append(f"- {key}: {count}")
    else:
        lines.append("- No flags.")
    lines.extend(["", "## Suggested Actions", ""])
    for action in report["triage"]["suggested_actions"]:
        lines.append(f"- {action}")
    lines.extend(["", "## Confusion Notes", ""])
    if report["triage"]["confusion_notes"]:
        for note in report["triage"]["confusion_notes"]:
            lines.append(f"- {note['path']}: {note['text']}")
    else:
        lines.append("- None.")
    lines.extend(["", "## Useful Moments", ""])
    if report["triage"]["useful_notes"]:
        for note in report["triage"]["useful_notes"]:
            lines.append(f"- {note['path']}: {note['text']}")
    else:
        lines.append("- None.")
    lines.append("")
    return "\n".join(lines)


def normalize_key(value: str) -> str:
    normalized = value.strip().lower()
    normalized = normalized.replace("`", "")
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    return normalized.strip("_")


def dedupe_paths(paths: Iterable[Path]) -> List[Path]:
    seen = set()
    result = []
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            result.append(path)
    return result


def utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


if __name__ == "__main__":
    raise SystemExit(main())
