from __future__ import annotations

from typing import Any, Dict, List


def visual_replay_lines(fixture: Dict[str, Any]) -> List[str]:
    body = fixture.get("fixture") or fixture
    source = body.get("source_run") or {}
    lines = [
        f"Replay fixture: {body.get('name') or fixture.get('name')}",
        f"Source run: {source.get('run_id')} [{source.get('status')}]",
        "",
    ]
    for index, item in enumerate(body.get("timeline", []), start=1):
        label = item.get("name") or item.get("message") or item.get("type") or "Untitled"
        type_name = item.get("type") or item.get("kind") or "event"
        status = item.get("status") or "recorded"
        lines.append(f"{index:03d}. [{type_name}] {label} ({status})")
    expected = body.get("expected") or {}
    if expected:
        lines.extend(
            [
                "",
                "Expected:",
                f"- status: {expected.get('status')}",
                f"- spans: {expected.get('span_count')}",
                f"- events: {expected.get('event_count')}",
                f"- artifacts: {expected.get('artifact_count')}",
            ]
        )
    return lines

