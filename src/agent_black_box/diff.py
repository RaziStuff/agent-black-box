from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .storage import ABBStore


def compare_runs(store: ABBStore, run_a: str, run_b: str) -> Dict[str, Any]:
    timeline_a = store.get_timeline(run_a)
    timeline_b = store.get_timeline(run_b)
    items_a = timeline_a["items"]
    items_b = timeline_b["items"]
    signatures_a = [_signature(item) for item in items_a]
    signatures_b = [_signature(item) for item in items_b]
    first_divergence = _first_divergence(signatures_a, signatures_b)

    return {
        "run_a": _run_summary(timeline_a),
        "run_b": _run_summary(timeline_b),
        "counts": {
            "spans": {"a": len(timeline_a["spans"]), "b": len(timeline_b["spans"])},
            "events": {"a": len(timeline_a["events"]), "b": len(timeline_b["events"])},
            "artifacts": {"a": len(timeline_a["artifacts"]), "b": len(timeline_b["artifacts"])},
        },
        "span_types": _type_delta(timeline_a["spans"], timeline_b["spans"]),
        "event_types": _type_delta(timeline_a["events"], timeline_b["events"]),
        "first_divergence": first_divergence,
    }


def format_diff(diff: Dict[str, Any]) -> str:
    lines = [
        f"Run A: {diff['run_a']['name']} ({diff['run_a']['run_id']}) [{diff['run_a']['status']}]",
        f"Run B: {diff['run_b']['name']} ({diff['run_b']['run_id']}) [{diff['run_b']['status']}]",
        "",
        "Counts:",
    ]
    for key, value in diff["counts"].items():
        lines.append(f"- {key}: {value['a']} -> {value['b']}")
    lines.append("")
    lines.append("Span types:")
    lines.extend(_format_type_delta(diff["span_types"]))
    lines.append("")
    lines.append("Event types:")
    lines.extend(_format_type_delta(diff["event_types"]))
    lines.append("")
    divergence = diff["first_divergence"]
    if divergence is None:
        lines.append("First divergence: none detected in normalized timeline signatures")
    else:
        lines.append(f"First divergence: timeline index {divergence['index']}")
        lines.append(f"- A: {divergence.get('a') or 'missing'}")
        lines.append(f"- B: {divergence.get('b') or 'missing'}")
    return "\n".join(lines)


def _run_summary(timeline: Dict[str, Any]) -> Dict[str, Any]:
    run = timeline["run"]
    return {
        "run_id": run["run_id"],
        "name": run["name"],
        "status": run["status"],
        "created_at": run["created_at"],
        "ended_at": run.get("ended_at"),
        "source": run["source"],
    }


def _type_delta(items_a: List[Dict[str, Any]], items_b: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    counts_a = _count_types(items_a)
    counts_b = _count_types(items_b)
    keys = sorted(set(counts_a) | set(counts_b))
    return {key: {"a": counts_a.get(key, 0), "b": counts_b.get(key, 0)} for key in keys}


def _count_types(items: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in items:
        key = item.get("type") or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return counts


def _signature(item: Dict[str, Any]) -> str:
    normalized = {
        "kind": item.get("kind"),
        "type": item.get("type"),
        "name": item.get("name"),
        "message": item.get("message"),
        "status": item.get("status"),
        "attributes": item.get("attributes") or {},
    }
    return json.dumps(normalized, sort_keys=True)


def _first_divergence(signatures_a: List[str], signatures_b: List[str]) -> Optional[Dict[str, Any]]:
    total = max(len(signatures_a), len(signatures_b))
    for index in range(total):
        a = signatures_a[index] if index < len(signatures_a) else None
        b = signatures_b[index] if index < len(signatures_b) else None
        if a != b:
            return {"index": index, "a": a, "b": b}
    return None


def _format_type_delta(delta: Dict[str, Dict[str, int]]) -> List[str]:
    if not delta:
        return ["- none"]
    return [f"- {key}: {value['a']} -> {value['b']}" for key, value in delta.items()]

