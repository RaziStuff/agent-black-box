#!/usr/bin/env python3
"""Rank Agent Black Box design-partner candidates from a CSV score sheet."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple


SCORE_FIELDS = [
    "active_agent_workflow",
    "debugging_pain",
    "terminal_comfort",
    "local_first_need",
    "feedback_availability",
    "wedge_fit",
    "privacy_fit",
    "relationship_strength",
]
CORE_SEGMENTS = ["agent founder", "agent infra engineer", "local automation builder"]
REQUIRED_FIELDS = ["candidate_id", "contact", "segment", "source", *SCORE_FIELDS, "notes"]
LOW_SIGNAL_THRESHOLD = 12


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        candidates = read_candidates(Path(args.csv_path))
        report = build_report(candidates, top_n=args.top)
    except (OSError, ValueError) as exc:
        print(f"Could not rank design-partner candidates: {exc}", file=sys.stderr)
        return 1

    if args.json_output:
        json_output = Path(args.json_output)
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.markdown:
        markdown = Path(args.markdown)
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(format_markdown(report), encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_markdown(report))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rank Agent Black Box design-partner candidates.")
    parser.add_argument("csv_path", help="Path to DESIGN_PARTNER_INTAKE.csv or a compatible candidate CSV.")
    parser.add_argument("--top", type=int, default=3, help="Number of selected candidates to recommend.")
    parser.add_argument("--markdown", help="Write Markdown ranking report to this path.")
    parser.add_argument("--json-output", help="Write JSON ranking report to this path.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    return parser


def read_candidates(path: Path) -> List[Dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("candidate CSV has no header")
        missing = [field for field in REQUIRED_FIELDS if field not in reader.fieldnames]
        if missing:
            raise ValueError(f"candidate CSV is missing required columns: {', '.join(missing)}")
        rows = [normalize_candidate(row, row_number=index + 2) for index, row in enumerate(reader)]
    if not rows:
        raise ValueError("candidate CSV has no candidates")
    return rows


def normalize_candidate(row: Dict[str, Optional[str]], row_number: int) -> Dict[str, Any]:
    candidate: Dict[str, Any] = {
        "candidate_id": clean(row.get("candidate_id")),
        "contact": clean(row.get("contact")),
        "segment": clean(row.get("segment")).lower(),
        "source": clean(row.get("source")),
        "notes": clean(row.get("notes")),
        "row_number": row_number,
    }
    if not candidate["candidate_id"]:
        raise ValueError(f"row {row_number} is missing candidate_id")
    if not candidate["contact"]:
        raise ValueError(f"row {row_number} is missing contact")
    if not candidate["segment"]:
        raise ValueError(f"row {row_number} is missing segment")

    scores: Dict[str, int] = {}
    for field in SCORE_FIELDS:
        scores[field] = parse_score(row.get(field), field, row_number)
    candidate["scores"] = scores
    candidate["total_score"] = sum(scores.values())
    candidate["status"] = candidate_status(candidate)
    candidate["flags"] = candidate_flags(candidate)
    return candidate


def clean(value: Optional[str]) -> str:
    return (value or "").strip()


def parse_score(raw: Optional[str], field: str, row_number: int) -> int:
    try:
        score = int(clean(raw))
    except ValueError as exc:
        raise ValueError(f"row {row_number} has invalid {field}: {raw!r}") from exc
    if score < 0 or score > 3:
        raise ValueError(f"row {row_number} {field} must be between 0 and 3")
    return score


def candidate_status(candidate: Dict[str, Any]) -> str:
    scores = candidate["scores"]
    if scores["active_agent_workflow"] == 0 or scores["terminal_comfort"] == 0 or scores["privacy_fit"] == 0:
        return "disqualified"
    if candidate["total_score"] < LOW_SIGNAL_THRESHOLD:
        return "low_signal"
    return "qualified"


def candidate_flags(candidate: Dict[str, Any]) -> List[str]:
    scores = candidate["scores"]
    flags: List[str] = []
    if scores["active_agent_workflow"] == 0:
        flags.append("no_active_agent_workflow")
    if scores["terminal_comfort"] == 0:
        flags.append("terminal_dealbreaker")
    if scores["privacy_fit"] == 0:
        flags.append("privacy_dealbreaker")
    if candidate["total_score"] < LOW_SIGNAL_THRESHOLD:
        flags.append("low_total_score")
    if candidate["segment"] not in CORE_SEGMENTS:
        flags.append("non_core_segment")
    if scores["debugging_pain"] >= 3:
        flags.append("acute_debugging_pain")
    if scores["wedge_fit"] >= 3:
        flags.append("strong_wedge_fit")
    return flags


def build_report(candidates: List[Dict[str, Any]], top_n: int = 3) -> Dict[str, Any]:
    ranked = sorted(candidates, key=ranking_key)
    selected = select_candidates(ranked, top_n=top_n)
    return {
        "version": "0.1",
        "created_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "top_n": top_n,
        "candidate_count": len(candidates),
        "qualified_count": sum(1 for candidate in candidates if candidate["status"] == "qualified"),
        "selected": [public_candidate(candidate) for candidate in selected],
        "ranked": [public_candidate(candidate) for candidate in ranked],
        "segment_summary": segment_summary(candidates),
        "suggested_actions": suggested_actions(candidates, selected),
    }


def ranking_key(candidate: Dict[str, Any]) -> Tuple[int, int, int, int, int, str]:
    status_penalty = {"qualified": 0, "low_signal": 1, "disqualified": 2}[candidate["status"]]
    scores = candidate["scores"]
    return (
        status_penalty,
        -candidate["total_score"],
        -scores["debugging_pain"],
        -scores["wedge_fit"],
        -scores["relationship_strength"],
        candidate["candidate_id"],
    )


def select_candidates(ranked: List[Dict[str, Any]], top_n: int = 3) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    qualified = [candidate for candidate in ranked if candidate["status"] == "qualified"]

    for segment in CORE_SEGMENTS:
        match = next((candidate for candidate in qualified if candidate["segment"] == segment), None)
        if match and match not in selected:
            selected.append(match)
        if len(selected) >= top_n:
            return selected

    for candidate in qualified:
        if candidate not in selected:
            selected.append(candidate)
        if len(selected) >= top_n:
            break
    return selected


def public_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "candidate_id": candidate["candidate_id"],
        "contact": candidate["contact"],
        "segment": candidate["segment"],
        "source": candidate["source"],
        "total_score": candidate["total_score"],
        "status": candidate["status"],
        "flags": candidate["flags"],
        "scores": candidate["scores"],
        "notes": candidate["notes"],
    }


def segment_summary(candidates: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    summary: Dict[str, Dict[str, int]] = {}
    for candidate in candidates:
        segment = candidate["segment"]
        if segment not in summary:
            summary[segment] = {"total": 0, "qualified": 0, "selected_ready": 0}
        summary[segment]["total"] += 1
        if candidate["status"] == "qualified":
            summary[segment]["qualified"] += 1
        if candidate["status"] == "qualified" and candidate["total_score"] >= 16:
            summary[segment]["selected_ready"] += 1
    return summary


def suggested_actions(candidates: List[Dict[str, Any]], selected: List[Dict[str, Any]]) -> List[str]:
    actions: List[str] = []
    selected_segments = {candidate["segment"] for candidate in selected}
    missing_segments = [segment for segment in CORE_SEGMENTS if segment not in selected_segments]
    if missing_segments:
        actions.append("Find stronger candidates for missing segments: " + ", ".join(missing_segments) + ".")
    if len(selected) < 3:
        actions.append("Do not send yet; fewer than three qualified candidates are ready.")
    if any(candidate["status"] == "disqualified" for candidate in candidates):
        actions.append("Keep disqualified candidates out of the first send even if they are easy to contact.")
    if selected:
        actions.append("Copy selected contacts into docs/DESIGN_PARTNER_TRACKER.csv before generating send drafts.")
    return actions


def format_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Design Partner Candidate Ranking",
        "",
        f"- Candidates: {report['candidate_count']}",
        f"- Qualified: {report['qualified_count']}",
        f"- Selected: {len(report['selected'])}",
        "",
        "## Selected",
        "",
    ]
    if report["selected"]:
        lines.extend(format_table(report["selected"]))
    else:
        lines.append("No qualified candidates selected.")
    lines.extend(["", "## Ranked Candidates", ""])
    lines.extend(format_table(report["ranked"]))
    lines.extend(["", "## Suggested Actions", ""])
    for action in report["suggested_actions"]:
        lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)


def format_table(candidates: List[Dict[str, Any]]) -> List[str]:
    lines = [
        "| rank | candidate_id | contact | segment | total | status | flags |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for index, candidate in enumerate(candidates, start=1):
        flags = ", ".join(candidate["flags"]) if candidate["flags"] else ""
        lines.append(
            "| {rank} | {candidate_id} | {contact} | {segment} | {total} | {status} | {flags} |".format(
                rank=index,
                candidate_id=escape_cell(candidate["candidate_id"]),
                contact=escape_cell(candidate["contact"]),
                segment=escape_cell(candidate["segment"]),
                total=candidate["total_score"],
                status=candidate["status"],
                flags=escape_cell(flags),
            )
        )
    return lines


def escape_cell(value: Any) -> str:
    return str(value).replace("|", "\\|")


if __name__ == "__main__":
    raise SystemExit(main())
