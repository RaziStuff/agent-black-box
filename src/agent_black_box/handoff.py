from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List

from .usage import format_usage


def format_handoff_briefing(
    packet: Dict[str, Any],
    timeline_limit: int = 12,
    attention_limit: int = 10,
    artifact_limit: int = 8,
    fixture_limit: int = 5,
) -> str:
    run = packet.get("run") or {}
    counts = packet.get("counts") or {}
    lines = [
        f"Agent Handoff: {run.get('name') or 'unnamed run'}",
        f"Run: {run.get('run_id') or 'unknown'}  Status: {run.get('status') or 'unknown'}  Source: {run.get('source') or 'unknown'}",
        f"Created: {run.get('created_at') or 'unknown'}  Ended: {run.get('ended_at') or 'not ended'}",
        "Counts: "
        + ", ".join(
            [
                _count(counts, "spans"),
                _count(counts, "events"),
                _count(counts, "artifacts"),
                _count(counts, "annotations"),
                _count(counts, "fixtures"),
            ]
        ),
    ]

    provenance = _provenance_lines(packet.get("provenance") or {})
    if provenance:
        lines.extend(["", "Provenance:", *provenance])

    summary = _summary_lines(packet.get("summary") or {})
    if summary:
        lines.extend(["", "Run Summary:", *summary])

    lines.extend(
        _section(
            "Debug Path",
            (_format_debug_path_item(item) for item in packet.get("debug_path") or []),
            limit=8,
            empty="No debug path items.",
        )
    )
    lines.extend(
        _section(
            "Attention",
            (_format_attention(item) for item in packet.get("attention") or []),
            limit=attention_limit,
            empty="No attention items.",
        )
    )
    lines.extend(
        _section(
            "Artifact Groups",
            (_format_artifact_group(group) for group in packet.get("artifact_groups") or []),
            limit=artifact_limit,
            empty="No artifact groups.",
        )
    )
    lines.extend(
        _section(
            "Timeline",
            (_format_timeline_item(item) for item in packet.get("timeline") or []),
            limit=timeline_limit,
            empty="No timeline entries.",
        )
    )
    lines.extend(
        _section(
            "Artifacts",
            (_format_artifact(artifact) for artifact in packet.get("artifacts") or []),
            limit=artifact_limit,
            empty="No artifacts.",
        )
    )
    lines.extend(
        _section(
            "Fixtures",
            (_format_fixture(fixture) for fixture in packet.get("fixtures") or []),
            limit=fixture_limit,
            empty="No fixtures.",
        )
    )
    lines.extend(
        _section(
            "Suggested Next Steps",
            (f"- {step}" for step in packet.get("suggested_next_steps") or []),
            limit=20,
            empty="No suggested next steps.",
        )
    )
    return "\n".join(lines)


def _count(counts: Dict[str, Any], key: str) -> str:
    value = counts.get(key, 0)
    return f"{value} {key}"


def _provenance_lines(provenance: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    if provenance.get("remapped_from_run_id"):
        lines.append(f"- Remapped from: {provenance['remapped_from_run_id']}")
    if provenance.get("imported_from_bundle"):
        lines.append(f"- Imported bundle: {provenance['imported_from_bundle']}")
    return lines


def _summary_lines(summary: Dict[str, Any]) -> List[str]:
    if not summary:
        return []
    lines = [
        "- "
        f"{summary.get('model_calls', 0)} model calls, "
        f"{summary.get('tool_calls', 0)} tool calls, "
        f"{summary.get('graph_nodes', 0)} graph nodes, "
        f"{summary.get('warnings', 0)} warnings, "
        f"{summary.get('errors', 0)} errors, "
        f"{summary.get('artifacts', 0)} artifacts"
    ]
    usage = format_usage(summary.get("usage") if isinstance(summary.get("usage"), dict) else None)
    if usage:
        lines.append(f"- Usage: {usage}")
    first_failure = summary.get("first_failure")
    if first_failure:
        lines.append(
            "- First failure: "
            f"{first_failure.get('ts') or 'unknown time'} "
            f"[{first_failure.get('type') or first_failure.get('kind')}] "
            f"{first_failure.get('title') or first_failure.get('id')}"
        )
    return lines


def _section(
    title: str,
    rows: Iterable[str],
    limit: int,
    empty: str,
) -> List[str]:
    materialized = list(rows)
    if not materialized:
        return ["", f"{title}:", f"- {empty}"]
    clipped = materialized[: max(limit, 0)]
    remaining = len(materialized) - len(clipped)
    lines = ["", f"{title}:", *clipped]
    if remaining:
        lines.append(f"- ... {remaining} more")
    return lines


def _format_debug_path_item(item: Dict[str, Any]) -> str:
    label = item.get("label") or item.get("kind") or "Inspect"
    title = item.get("title") or item.get("id") or ""
    priority = item.get("priority") or "note"
    step = item.get("step") or "?"
    ts = item.get("ts") or "unknown time"
    refs = _format_refs(item.get("refs") or {})
    refs_text = f" refs: {refs}" if refs else ""
    artifact_refs = _format_artifact_refs(item.get("artifact_refs") or [])
    artifact_text = f" artifacts: {artifact_refs}" if artifact_refs else ""
    reason = f" why: {item['reason']}" if item.get("reason") else ""
    action = f" next: {item['suggested_action']}" if item.get("suggested_action") else ""
    return f"- {step}. [{priority}] {label} @ {ts}: {title}{reason}{action}{artifact_text}{refs_text}"


def _format_attention(item: Dict[str, Any]) -> str:
    kind = item.get("kind") or "item"
    label = item.get("type") or item.get("id") or kind
    title = item.get("title") or ""
    span = f" span={item['span_id']}" if item.get("span_id") else ""
    ts = f" @ {item['ts']}" if item.get("ts") else ""
    return f"- {kind} {label}{span}{ts}: {title}"


def _format_artifact_group(group: Dict[str, Any]) -> str:
    title = group.get("name") or group.get("span_id") or "span"
    span_type = group.get("type") or "span"
    artifacts = []
    for artifact in group.get("artifacts") or []:
        role = artifact.get("role") or artifact.get("ref") or "artifact"
        artifact_id = artifact.get("artifact_id") or "unknown"
        kind = artifact.get("kind") or "artifact"
        artifacts.append(f"{role}={artifact_id} ({kind})")
    artifact_text = ", ".join(artifacts) if artifacts else "none"
    return f"- {title} [{span_type}] artifacts: {artifact_text}"


def _format_timeline_item(item: Dict[str, Any]) -> str:
    kind = item.get("kind") or "item"
    item_type = item.get("type") or kind
    title = item.get("title") or item.get("id") or "untitled"
    status = f" ({item['status']})" if item.get("status") else ""
    ts = item.get("ts") or "unknown time"
    refs = _format_refs(item.get("refs") or {})
    refs_text = f" refs: {refs}" if refs else ""
    usage = format_usage(item.get("usage") if isinstance(item.get("usage"), dict) else None)
    usage_text = f" {usage}" if usage else ""
    return f"- {ts} [{kind}/{item_type}] {title}{status}{usage_text}{refs_text}"


def _format_artifact(artifact: Dict[str, Any]) -> str:
    redacted = " redacted" if artifact.get("redacted") else ""
    return (
        f"- {artifact.get('artifact_id') or 'unknown'} "
        f"{artifact.get('kind') or 'artifact'} "
        f"{artifact.get('media_type') or 'application/octet-stream'} "
        f"{artifact.get('size', 0)} bytes{redacted}"
    )


def _format_fixture(fixture: Dict[str, Any]) -> str:
    expected = fixture.get("expected") or {}
    expected_text = ", ".join(
        value
        for value in [
            f"status={expected.get('status')}" if expected.get("status") else "",
            f"spans={expected.get('span_count')}" if expected.get("span_count") is not None else "",
            f"events={expected.get('event_count')}" if expected.get("event_count") is not None else "",
            f"artifacts={expected.get('artifact_count')}" if expected.get("artifact_count") is not None else "",
        ]
        if value
    )
    suffix = f" expected: {expected_text}" if expected_text else ""
    return f"- {fixture.get('fixture_id') or 'unknown'} {fixture.get('name') or 'unnamed fixture'}{suffix}"


def _format_refs(refs: Dict[str, Any]) -> str:
    parts = []
    for key in sorted(refs):
        value = refs[key]
        if isinstance(value, (dict, list)):
            rendered = json.dumps(value, sort_keys=True)
        else:
            rendered = str(value)
        parts.append(f"{key}={rendered}")
    return ", ".join(parts)


def _format_artifact_refs(refs: List[Dict[str, Any]]) -> str:
    parts = []
    for ref in refs:
        label = ref.get("ref") or "artifact"
        artifact_id = ref.get("artifact_id") or "unknown"
        kind = ref.get("kind") or "artifact"
        parts.append(f"{label}={artifact_id} ({kind})")
    return ", ".join(parts)
