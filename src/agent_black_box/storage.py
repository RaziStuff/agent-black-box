from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any, Dict, List, Optional, Tuple, Union
import zipfile

from .ids import new_id, utc_now
from .redaction import redact_payload, redact_text
from .usage import usage_from_attributes


COMPARE_PAIR_TYPES = ("request-response", "input-output", "schema-input", "schema-output")
COMPARE_EVIDENCE_PARTS = {
    "packet": "compare.packet",
    "briefing": "compare.briefing",
    "left": "compare.left",
    "right": "compare.right",
}
_COMPARE_PAIR_DEFS = {
    "request-response": ("Request vs Response", "request", "response"),
    "input-output": ("Input vs Output", "input", "output"),
    "schema-input": ("Schema vs Input", "schema", "input"),
    "schema-output": ("Schema vs Output", "schema", "output"),
}


def default_data_dir() -> Path:
    value = os.environ.get("ABB_HOME")
    if value:
        return Path(value).expanduser()
    return Path.cwd() / ".abb"


def _to_json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True)


def _from_json(value: Optional[str], fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


class ABBStore:
    def __init__(self, root: Optional[Union[os.PathLike, str]] = None):
        self.root = Path(root) if root else default_data_dir()
        self.root.mkdir(parents=True, exist_ok=True)
        self.objects_dir = self.root / "objects"
        self.exports_dir = self.root / "exports"
        self.objects_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "abb.sqlite"
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    ended_at TEXT,
                    source TEXT NOT NULL,
                    agent_json TEXT NOT NULL,
                    environment_json TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS spans (
                    span_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    parent_span_id TEXT,
                    type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    status TEXT NOT NULL,
                    input_ref TEXT,
                    output_ref TEXT,
                    attributes_json TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    span_id TEXT,
                    type TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    message TEXT,
                    attributes_json TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    run_id TEXT,
                    span_id TEXT,
                    hash TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    path TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    redacted INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS annotations (
                    annotation_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    span_id TEXT,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS replay_fixtures (
                    fixture_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    fixture_json TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at);
                CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
                CREATE INDEX IF NOT EXISTS idx_spans_run_started ON spans(run_id, started_at);
                CREATE INDEX IF NOT EXISTS idx_events_run_ts ON events(run_id, ts);
                CREATE INDEX IF NOT EXISTS idx_artifacts_hash ON artifacts(hash);
                CREATE INDEX IF NOT EXISTS idx_fixtures_run_id ON replay_fixtures(run_id);
                """
            )
            self._conn.commit()

    def create_run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload, hits = redact_payload(payload)
        run_id = payload.get("run_id") or new_id("run")
        created_at = payload.get("created_at") or utc_now()
        row = {
            "run_id": run_id,
            "name": payload.get("name") or "Untitled run",
            "status": payload.get("status") or "running",
            "created_at": created_at,
            "ended_at": payload.get("ended_at"),
            "source": payload.get("source") or "unknown",
            "agent": payload.get("agent") or {},
            "environment": payload.get("environment") or {},
            "tags": payload.get("tags") or [],
            "metadata": payload.get("metadata") or {},
        }
        if hits:
            row["metadata"] = {**row["metadata"], "redaction_hits": hits}

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO runs (
                    run_id, name, status, created_at, ended_at, source,
                    agent_json, environment_json, tags_json, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["run_id"],
                    row["name"],
                    row["status"],
                    row["created_at"],
                    row["ended_at"],
                    row["source"],
                    _to_json(row["agent"]),
                    _to_json(row["environment"]),
                    _to_json(row["tags"]),
                    _to_json(row["metadata"]),
                ),
            )
            self._conn.commit()
        return row

    def end_run(self, run_id: str, status: str = "ok", ended_at: Optional[str] = None) -> Optional[Dict[str, Any]]:
        ended_at = ended_at or utc_now()
        with self._lock:
            self._conn.execute(
                "UPDATE runs SET status = ?, ended_at = ? WHERE run_id = ?",
                (status, ended_at, run_id),
            )
            self._conn.commit()
        return self.get_run(run_id)

    def start_span(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload, hits = redact_payload(payload)
        span_id = payload.get("span_id") or new_id("span")
        attributes = payload.get("attributes") or {}
        if hits:
            attributes = {**attributes, "redaction_hits": hits}
        row = {
            "span_id": span_id,
            "run_id": payload["run_id"],
            "parent_span_id": payload.get("parent_span_id"),
            "type": payload.get("type") or "agent.step",
            "name": payload.get("name") or "Untitled span",
            "started_at": payload.get("started_at") or utc_now(),
            "ended_at": payload.get("ended_at"),
            "status": payload.get("status") or "running",
            "input_ref": payload.get("input_ref"),
            "output_ref": payload.get("output_ref"),
            "attributes": attributes,
        }
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO spans (
                    span_id, run_id, parent_span_id, type, name, started_at,
                    ended_at, status, input_ref, output_ref, attributes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["span_id"],
                    row["run_id"],
                    row["parent_span_id"],
                    row["type"],
                    row["name"],
                    row["started_at"],
                    row["ended_at"],
                    row["status"],
                    row["input_ref"],
                    row["output_ref"],
                    _to_json(row["attributes"]),
                ),
            )
            self._conn.commit()
        return row

    def end_span(
        self,
        span_id: str,
        status: str = "ok",
        ended_at: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
        output_ref: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        ended_at = ended_at or utc_now()
        if attributes is not None:
            attributes, _ = redact_payload(attributes)
        with self._lock:
            current = self._conn.execute(
                "SELECT attributes_json FROM spans WHERE span_id = ?",
                (span_id,),
            ).fetchone()
            merged_attributes = _from_json(current["attributes_json"], {}) if current else {}
            if attributes:
                merged_attributes.update(attributes)
            self._conn.execute(
                """
                UPDATE spans
                SET status = ?, ended_at = ?, attributes_json = ?,
                    output_ref = COALESCE(?, output_ref)
                WHERE span_id = ?
                """,
                (status, ended_at, _to_json(merged_attributes), output_ref, span_id),
            )
            self._conn.commit()
        return self.get_span(span_id)

    def add_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload, hits = redact_payload(payload)
        attributes = payload.get("attributes") or {}
        if hits:
            attributes = {**attributes, "redaction_hits": hits}
        row = {
            "event_id": payload.get("event_id") or new_id("evt"),
            "run_id": payload["run_id"],
            "span_id": payload.get("span_id"),
            "type": payload.get("type") or "event",
            "ts": payload.get("ts") or utc_now(),
            "message": payload.get("message"),
            "attributes": attributes,
        }
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO events (
                    event_id, run_id, span_id, type, ts, message, attributes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["event_id"],
                    row["run_id"],
                    row["span_id"],
                    row["type"],
                    row["ts"],
                    row["message"],
                    _to_json(row["attributes"]),
                ),
            )
            self._conn.commit()
        return row

    def add_annotation(self, run_id: str, message: str, span_id: Optional[str] = None) -> Dict[str, Any]:
        message, hits = redact_text(message)
        row = {
            "annotation_id": new_id("ann"),
            "run_id": run_id,
            "span_id": span_id,
            "message": message,
            "created_at": utc_now(),
        }
        if hits:
            self.add_event(
                {
                    "run_id": run_id,
                    "span_id": span_id,
                    "type": "secret.redacted",
                    "message": "Annotation contained redacted content",
                    "attributes": {"redaction_hits": [hit.__dict__ for hit in hits]},
                }
            )
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO annotations (annotation_id, run_id, span_id, message, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (row["annotation_id"], row["run_id"], row["span_id"], row["message"], row["created_at"]),
            )
            self._conn.commit()
        self.add_event({"run_id": run_id, "span_id": span_id, "type": "run.annotated", "message": message})
        return row

    def list_annotations(self, run_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM annotations WHERE run_id = ? ORDER BY created_at ASC",
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_artifact(
        self,
        run_id: Optional[str],
        span_id: Optional[str],
        kind: str,
        content: Union[bytes, str],
        media_type: str = "text/plain",
    ) -> Dict[str, Any]:
        redacted = False
        if isinstance(content, str):
            content, hits = redact_text(content)
            redacted = bool(hits)
            data = content.encode("utf-8")
        else:
            data = content
        digest = hashlib.sha256(data).hexdigest()
        artifact_id = f"blob_{digest[:24]}"
        path = self.objects_dir / "sha256" / digest[:2] / digest[2:4] / digest
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
        row = {
            "artifact_id": artifact_id,
            "run_id": run_id,
            "span_id": span_id,
            "hash": digest,
            "kind": kind,
            "media_type": media_type,
            "path": str(path.relative_to(self.root)),
            "size": len(data),
            "created_at": utc_now(),
            "redacted": redacted,
        }
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO artifacts (
                    artifact_id, run_id, span_id, hash, kind, media_type,
                    path, size, created_at, redacted
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["artifact_id"],
                    row["run_id"],
                    row["span_id"],
                    row["hash"],
                    row["kind"],
                    row["media_type"],
                    row["path"],
                    row["size"],
                    row["created_at"],
                    int(row["redacted"]),
                ),
            )
            self._conn.commit()
        return row

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return self._run_row(row) if row else None

    def get_span(self, span_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM spans WHERE span_id = ?", (span_id,)).fetchone()
        return self._span_row(row) if row else None

    def list_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._run_row(row) for row in rows]

    def get_run_links(self, run_id: str) -> Dict[str, Any]:
        run = self.get_run(run_id)
        if not run:
            raise KeyError(run_id)
        metadata = run.get("metadata") or {}
        source_run_id = metadata.get("source_handoff_run_id") or metadata.get("source_compare_run_id")
        source = self.get_run(source_run_id) if source_run_id else None
        investigations: List[Dict[str, Any]] = []
        for investigation in self.list_runs(limit=1000):
            investigation_metadata = investigation.get("metadata") or {}
            linked_source_id = (
                investigation_metadata.get("source_handoff_run_id")
                or investigation_metadata.get("source_compare_run_id")
            )
            if linked_source_id != run_id:
                continue
            investigations.append(
                {
                    "run_id": investigation["run_id"],
                    "name": investigation["name"],
                    "status": investigation["status"],
                    "created_at": investigation["created_at"],
                    "source": investigation["source"],
                }
            )
        return {
            "run_id": run_id,
            "source": _compact_linked_run(source) if source else None,
            "investigations": investigations,
        }

    def get_timeline(self, run_id: str) -> Dict[str, Any]:
        run = self.get_run(run_id)
        if not run:
            raise KeyError(run_id)
        with self._lock:
            spans = [
                self._span_row(row)
                for row in self._conn.execute(
                    "SELECT * FROM spans WHERE run_id = ? ORDER BY started_at ASC",
                    (run_id,),
                ).fetchall()
            ]
            events = [
                self._event_row(row)
                for row in self._conn.execute(
                    "SELECT * FROM events WHERE run_id = ? ORDER BY ts ASC",
                    (run_id,),
                ).fetchall()
            ]
            artifacts = [
                self._artifact_row(row)
                for row in self._conn.execute(
                    "SELECT * FROM artifacts WHERE run_id = ? ORDER BY created_at ASC",
                    (run_id,),
                ).fetchall()
            ]
            annotations = [
                dict(row)
                for row in self._conn.execute(
                    "SELECT * FROM annotations WHERE run_id = ? ORDER BY created_at ASC",
                    (run_id,),
                ).fetchall()
            ]
        items: List[Dict[str, Any]] = []
        for span in spans:
            items.append({"kind": "span", "ts": span["started_at"], **span})
        for event in events:
            items.append({"kind": "event", "ts": event["ts"], **event})
        items.sort(key=lambda item: item.get("ts") or "")
        timeline = {
            "run": run,
            "items": items,
            "spans": spans,
            "events": events,
            "artifacts": artifacts,
            "annotations": annotations,
        }
        timeline["summary"] = _timeline_summary(timeline)
        timeline["debug_path"] = _debug_path(timeline)
        timeline["artifact_groups"] = _artifact_groups(timeline)
        return timeline

    def search(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        pattern = f"%{query}%"
        with self._lock:
            run_rows = self._conn.execute(
                """
                SELECT DISTINCT runs.*
                FROM runs
                LEFT JOIN spans ON spans.run_id = runs.run_id
                LEFT JOIN events ON events.run_id = runs.run_id
                LEFT JOIN annotations ON annotations.run_id = runs.run_id
                WHERE runs.name LIKE ?
                   OR runs.status LIKE ?
                   OR runs.source LIKE ?
                   OR runs.tags_json LIKE ?
                   OR runs.metadata_json LIKE ?
                   OR spans.name LIKE ?
                   OR events.message LIKE ?
                   OR annotations.message LIKE ?
                ORDER BY runs.created_at DESC
                LIMIT ?
                """,
                (pattern, pattern, pattern, pattern, pattern, pattern, pattern, pattern, limit),
            ).fetchall()
        return [self._run_row(row) for row in run_rows]

    def read_artifact(self, artifact_id: str) -> Optional[bytes]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM artifacts WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
        if not row:
            return None
        path = self.root / row["path"]
        return path.read_bytes()

    def get_artifact(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM artifacts WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
        return self._artifact_row(row) if row else None

    def list_artifacts(self, run_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM artifacts WHERE run_id = ? ORDER BY created_at ASC",
                (run_id,),
            ).fetchall()
        return [self._artifact_row(row) for row in rows]

    def create_fixture(self, run_id: str, name: Optional[str] = None) -> Dict[str, Any]:
        timeline = self.get_timeline(run_id)
        run = timeline["run"]
        fixture_id = new_id("fix")
        created_at = utc_now()
        fixture = {
            "fixture_id": fixture_id,
            "trace_version": "0.1",
            "run_id": run_id,
            "name": name or f"{run['name']} fixture",
            "created_at": created_at,
            "source_run": run,
            "timeline": [
                {
                    "kind": item.get("kind"),
                    "type": item.get("type"),
                    "name": item.get("name"),
                    "message": item.get("message"),
                    "status": item.get("status"),
                    "ts": item.get("ts"),
                    "span_id": item.get("span_id"),
                    "event_id": item.get("event_id"),
                    "parent_span_id": item.get("parent_span_id"),
                    "attributes": item.get("attributes") or {},
                }
                for item in timeline["items"]
            ],
            "artifacts": timeline["artifacts"],
            "annotations": timeline["annotations"],
            "expected": {
                "status": run["status"],
                "span_count": len(timeline["spans"]),
                "event_count": len(timeline["events"]),
                "artifact_count": len(timeline["artifacts"]),
            },
        }
        row = {
            "fixture_id": fixture_id,
            "run_id": run_id,
            "name": fixture["name"],
            "created_at": created_at,
            "fixture": fixture,
        }
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO replay_fixtures (fixture_id, run_id, name, created_at, fixture_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (fixture_id, run_id, row["name"], created_at, _to_json(fixture)),
            )
            self._conn.commit()
        return row

    def list_fixtures(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM replay_fixtures ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._fixture_row(row) for row in rows]

    def get_fixture(self, fixture_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM replay_fixtures WHERE fixture_id = ?",
                (fixture_id,),
            ).fetchone()
        return self._fixture_row(row) if row else None

    def list_fixtures_for_run(self, run_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM replay_fixtures WHERE run_id = ? ORDER BY created_at ASC",
                (run_id,),
            ).fetchall()
        return [self._fixture_row(row) for row in rows]

    def build_handoff_packet(self, run_id: str) -> Dict[str, Any]:
        timeline = self.get_timeline(run_id)
        return _handoff_packet(timeline, self.list_fixtures_for_run(run_id))

    def ingest_handoff_packet(
        self,
        packet: Dict[str, Any],
        briefing: str,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        source_run = _validate_handoff_packet(packet)
        source_run_id = source_run["run_id"]
        source_name = source_run.get("name") or source_run_id
        run = self.create_run(
            {
                "name": name or f"Investigate {source_name}",
                "source": "handoff-ingest",
                "tags": ["handoff", "investigation"],
                "metadata": {
                    "source_handoff_run_id": source_run_id,
                    "source_handoff_name": source_name,
                    "source_handoff_status": source_run.get("status"),
                    "handoff_version": packet.get("handoff_version"),
                },
            }
        )
        span = self.start_span(
            {
                "run_id": run["run_id"],
                "type": "handoff.ingest",
                "name": f"Ingest handoff from {source_run_id}",
                "attributes": {
                    "source_run_id": source_run_id,
                    "source_status": source_run.get("status"),
                    "source_counts": packet.get("counts") or {},
                },
            }
        )
        packet_artifact = self.add_artifact(
            run["run_id"],
            span["span_id"],
            "handoff.packet",
            json.dumps(packet, indent=2, sort_keys=True),
            media_type="application/json",
        )
        briefing_artifact = self.add_artifact(
            run["run_id"],
            span["span_id"],
            "handoff.briefing",
            briefing,
            media_type="text/plain",
        )
        self.add_event(
            {
                "run_id": run["run_id"],
                "span_id": span["span_id"],
                "type": "handoff.ingested",
                "message": f"Ingested handoff from {source_run_id}",
                "attributes": {
                    "source_run_id": source_run_id,
                    "packet_ref": packet_artifact["artifact_id"],
                    "briefing_ref": briefing_artifact["artifact_id"],
                },
            }
        )
        self.add_annotation(
            run["run_id"],
            f"Investigation created from handoff packet for {source_run_id}",
            span_id=span["span_id"],
        )
        self.end_span(
            span["span_id"],
            status="ok",
            output_ref=briefing_artifact["artifact_id"],
            attributes={
                "packet_ref": packet_artifact["artifact_id"],
                "briefing_ref": briefing_artifact["artifact_id"],
            },
        )
        return {
            "run": self.get_run(run["run_id"]),
            "span": self.get_span(span["span_id"]),
            "packet_artifact": packet_artifact,
            "briefing_artifact": briefing_artifact,
            "source_run_id": source_run_id,
        }

    def ingest_compare_packet(
        self,
        packet: Dict[str, Any],
        name: Optional[str] = None,
        briefing: Optional[str] = None,
    ) -> Dict[str, Any]:
        packet = _validate_compare_packet(packet)
        source_run_id = packet["run_id"]
        source_span = packet.get("span") or {}
        pair = packet.get("pair") or {}
        artifacts = packet.get("artifacts") or {}
        left = artifacts["left"]
        right = artifacts["right"]
        source_span_id = source_span.get("span_id") or ""
        source_span_name = source_span.get("name") or source_span_id or "span"
        pair_type = pair.get("type") or "compare"
        pair_label = pair.get("label") or pair_type
        briefing_text = briefing if briefing is not None else format_compare_briefing(packet)

        run = self.create_run(
            {
                "name": name or f"Investigate {pair_label}",
                "source": "compare-ingest",
                "tags": ["compare", "investigation"],
                "metadata": {
                    "source_compare_run_id": source_run_id,
                    "source_compare_span_id": source_span_id,
                    "source_compare_span_name": source_span_name,
                    "source_compare_pair_type": pair_type,
                    "source_compare_pair_label": pair_label,
                    "compare_schema_version": packet.get("schema_version"),
                },
            }
        )
        span = self.start_span(
            {
                "run_id": run["run_id"],
                "type": "compare.ingest",
                "name": f"Ingest compare pair from {source_run_id}",
                "attributes": {
                    "source_run_id": source_run_id,
                    "source_span_id": source_span_id,
                    "source_span_name": source_span_name,
                    "pair_type": pair_type,
                    "pair_label": pair_label,
                    "left_artifact_id": left.get("artifact_id"),
                    "right_artifact_id": right.get("artifact_id"),
                },
            }
        )
        packet_artifact = self.add_artifact(
            run["run_id"],
            span["span_id"],
            "compare.packet",
            json.dumps(packet, indent=2, sort_keys=True),
            media_type="application/json",
        )
        briefing_artifact = self.add_artifact(
            run["run_id"],
            span["span_id"],
            "compare.briefing",
            briefing_text,
            media_type="text/plain",
        )
        left_artifact = self.add_artifact(
            run["run_id"],
            span["span_id"],
            "compare.left",
            json.dumps(_compare_ingest_body("left", left), indent=2, sort_keys=True),
            media_type="application/json",
        )
        right_artifact = self.add_artifact(
            run["run_id"],
            span["span_id"],
            "compare.right",
            json.dumps(_compare_ingest_body("right", right), indent=2, sort_keys=True),
            media_type="application/json",
        )
        self.add_event(
            {
                "run_id": run["run_id"],
                "span_id": span["span_id"],
                "type": "compare.ingested",
                "message": f"Ingested compare pair from {source_run_id}",
                "attributes": {
                    "source_run_id": source_run_id,
                    "source_span_id": source_span_id,
                    "pair_type": pair_type,
                    "packet_ref": packet_artifact["artifact_id"],
                    "briefing_ref": briefing_artifact["artifact_id"],
                    "left_ref": left_artifact["artifact_id"],
                    "right_ref": right_artifact["artifact_id"],
                },
            }
        )
        self.add_annotation(
            run["run_id"],
            f"Investigation created from compare pair {pair_label} for {source_run_id}",
            span_id=span["span_id"],
        )
        self.end_span(
            span["span_id"],
            status="ok",
            output_ref=briefing_artifact["artifact_id"],
            attributes={
                "packet_ref": packet_artifact["artifact_id"],
                "briefing_ref": briefing_artifact["artifact_id"],
                "left_ref": left_artifact["artifact_id"],
                "right_ref": right_artifact["artifact_id"],
            },
        )
        return {
            "run": self.get_run(run["run_id"]),
            "span": self.get_span(span["span_id"]),
            "packet_artifact": packet_artifact,
            "briefing_artifact": briefing_artifact,
            "left_artifact": left_artifact,
            "right_artifact": right_artifact,
            "source_run_id": source_run_id,
            "source_span_id": source_span_id,
        }

    def export_run(self, run_id: str, fmt: str = "jsonl", output: Optional[Union[os.PathLike, str]] = None) -> Path:
        timeline = self.get_timeline(run_id)
        suffix = "handoff.json" if fmt == "handoff" else fmt
        output_path = Path(output) if output else self.exports_dir / f"{run_id}.{suffix}"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "jsonl":
            with output_path.open("w", encoding="utf-8") as handle:
                handle.write(json.dumps({"type": "run", "data": timeline["run"]}, sort_keys=True) + "\n")
                for span in timeline["spans"]:
                    handle.write(json.dumps({"type": "span", "data": span}, sort_keys=True) + "\n")
                for event in timeline["events"]:
                    handle.write(json.dumps({"type": "event", "data": event}, sort_keys=True) + "\n")
                for artifact in timeline["artifacts"]:
                    handle.write(json.dumps({"type": "artifact", "data": artifact}, sort_keys=True) + "\n")
            return output_path
        if fmt in {"md", "markdown"}:
            with output_path.open("w", encoding="utf-8") as handle:
                run = timeline["run"]
                handle.write(f"# Agent Black Box Run: {run['name']}\n\n")
                handle.write(f"- Run ID: `{run['run_id']}`\n")
                handle.write(f"- Status: `{run['status']}`\n")
                handle.write(f"- Source: `{run['source']}`\n")
                handle.write(f"- Created: `{run['created_at']}`\n")
                handle.write(f"- Ended: `{run.get('ended_at') or 'not ended'}`\n\n")
                handle.write("## Timeline\n\n")
                for item in timeline["items"]:
                    title = item.get("name") or item.get("message") or item.get("type")
                    handle.write(f"- `{item.get('ts')}` **{item.get('type')}** {title}\n")
            return output_path
        if fmt == "handoff":
            packet = _handoff_packet(timeline, self.list_fixtures_for_run(run_id))
            with output_path.open("w", encoding="utf-8") as handle:
                json.dump(packet, handle, indent=2, sort_keys=True)
                handle.write("\n")
            return output_path
        raise ValueError(f"Unsupported export format: {fmt}")

    def build_compare_export(
        self,
        run_id: str,
        span_id: Optional[str] = None,
        pair: str = "auto",
    ) -> Dict[str, Any]:
        timeline = self.get_timeline(run_id)
        selected_group, selected_pair = _select_compare_pair(
            timeline.get("artifact_groups") or [],
            span_id=span_id,
            pair=pair,
        )
        left = selected_pair["left"]
        right = selected_pair["right"]
        left_text = self._read_artifact_text(left["artifact_id"])
        right_text = self._read_artifact_text(right["artifact_id"])
        return _compare_export_payload(
            run_id=run_id,
            group=selected_group,
            pair=selected_pair,
            left_text=left_text,
            right_text=right_text,
        )

    def export_compare_pair(
        self,
        run_id: str,
        span_id: Optional[str] = None,
        pair: str = "auto",
        fmt: str = "markdown",
        output: Optional[Union[os.PathLike, str]] = None,
    ) -> Path:
        payload = self.build_compare_export(run_id, span_id=span_id, pair=pair)
        normalized = _normalize_compare_format(fmt)
        extension = "json" if normalized == "json" else "md"
        output_path = Path(output) if output else self.exports_dir / (
            f"{_safe_export_token(run_id)}."
            f"{_safe_export_token(payload['span'].get('span_id') or 'span')}."
            f"{_safe_export_token(payload['pair'].get('type') or pair or 'auto')}."
            f"compare.{extension}"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(format_compare_export(payload, normalized), encoding="utf-8")
        return output_path

    def compare_evidence_summary(self, run_id: str) -> Dict[str, Any]:
        timeline = self.get_timeline(run_id)
        _validate_compare_investigation_timeline(timeline)
        return _compare_evidence_summary(timeline)

    def get_compare_evidence(
        self,
        run_id: str,
        part: str,
        raw: bool = False,
    ) -> Dict[str, Any]:
        if part not in COMPARE_EVIDENCE_PARTS:
            raise ValueError("compare evidence part must be one of: " + ", ".join(COMPARE_EVIDENCE_PARTS))
        timeline = self.get_timeline(run_id)
        _validate_compare_investigation_timeline(timeline)
        evidence = compare_evidence_artifacts(timeline)
        artifact = evidence.get(part)
        if not artifact:
            raise ValueError(f"Compare evidence not found: {part}")
        content = self.read_artifact(artifact["artifact_id"])
        if content is None:
            raise ValueError(f"Artifact content missing: {artifact['artifact_id']}")
        return {
            "run_id": run_id,
            "part": part,
            "raw": bool(raw),
            "artifact": artifact,
            "content": decode_compare_evidence_content(part, content, raw=raw),
        }

    def _read_artifact_text(self, artifact_id: str) -> str:
        content = self.read_artifact(artifact_id)
        if content is None:
            raise ValueError(f"Artifact content missing: {artifact_id}")
        return content.decode("utf-8", errors="replace")

    def export_bundle(self, run_id: str, output: Optional[Union[os.PathLike, str]] = None) -> Path:
        timeline = self.get_timeline(run_id)
        fixtures = self.list_fixtures_for_run(run_id)
        output_path = Path(output) if output else self.exports_dir / f"{run_id}.abb"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        manifest = {
            "bundle_version": "0.1",
            "trace_version": "0.1",
            "exported_at": utc_now(),
            "run_id": run_id,
            "counts": {
                "spans": len(timeline["spans"]),
                "events": len(timeline["events"]),
                "artifacts": len(timeline["artifacts"]),
                "annotations": len(timeline["annotations"]),
                "fixtures": len(fixtures),
            },
        }
        trace = {
            "run": timeline["run"],
            "spans": timeline["spans"],
            "events": timeline["events"],
            "artifacts": timeline["artifacts"],
            "annotations": timeline["annotations"],
            "fixtures": fixtures,
        }
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
            bundle.writestr("trace.json", json.dumps(trace, indent=2, sort_keys=True))
            for artifact in timeline["artifacts"]:
                artifact_id = artifact["artifact_id"]
                if not _safe_bundle_id(artifact_id):
                    raise ValueError(f"Unsafe artifact id: {artifact_id}")
                content = self.read_artifact(artifact_id)
                if content is None:
                    raise ValueError(f"Artifact content missing: {artifact_id}")
                bundle.writestr(f"artifacts/{artifact_id}", content)
        return output_path

    def import_bundle(
        self,
        bundle_path: Union[os.PathLike, str],
        on_conflict: str = "fail",
    ) -> Dict[str, Any]:
        if on_conflict not in {"fail", "skip", "remap"}:
            raise ValueError("on_conflict must be one of: fail, skip, remap")
        path = Path(bundle_path)
        with zipfile.ZipFile(path, "r") as bundle:
            names = set(bundle.namelist())
            if "manifest.json" not in names or "trace.json" not in names:
                raise ValueError("Invalid ABB bundle: manifest.json and trace.json are required")
            manifest = json.loads(bundle.read("manifest.json").decode("utf-8"))
            original_trace = json.loads(bundle.read("trace.json").decode("utf-8"))
            original_run = original_trace["run"]
            original_run_id = original_run["run_id"]
            existing_run = self.get_run(original_run_id)
            if existing_run and on_conflict == "fail":
                raise ValueError(f"Run already exists: {original_run_id}")
            if existing_run and on_conflict == "skip":
                return {
                    "run_id": original_run_id,
                    "bundle": str(path),
                    "manifest": manifest,
                    "counts": manifest.get("counts") or {},
                    "skipped": True,
                    "conflict": True,
                    "remapped": False,
                    "original_run_id": original_run_id,
                    "id_map": {},
                }
            original_artifacts = original_trace.get("artifacts", [])
            artifact_payloads: Dict[str, bytes] = {}
            for artifact in original_artifacts:
                artifact_id = artifact["artifact_id"]
                if not _safe_bundle_id(artifact_id):
                    raise ValueError(f"Unsafe artifact id: {artifact_id}")
                member = f"artifacts/{artifact_id}"
                if member not in names:
                    raise ValueError(f"Missing artifact payload: {artifact_id}")
                payload = bundle.read(member)
                digest = hashlib.sha256(payload).hexdigest()
                if digest != artifact["hash"]:
                    raise ValueError(f"Artifact hash mismatch: {artifact_id}")
                artifact_payloads[artifact_id] = payload
            remapped = bool(existing_run and on_conflict == "remap")
            if remapped:
                trace, id_map = _remap_bundle_trace(original_trace)
                artifact_payloads = {
                    id_map["artifacts"].get(artifact_id, artifact_id): payload
                    for artifact_id, payload in artifact_payloads.items()
                }
            else:
                trace = original_trace
                id_map = _empty_bundle_id_map()
            run = trace["run"]
            run_id = run["run_id"]
            artifacts = trace.get("artifacts", [])

        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT INTO runs (
                        run_id, name, status, created_at, ended_at, source,
                        agent_json, environment_json, tags_json, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run["run_id"],
                        run["name"],
                        run["status"],
                        run["created_at"],
                        run.get("ended_at"),
                        run["source"],
                        _to_json(run.get("agent") or {}),
                        _to_json(run.get("environment") or {}),
                        _to_json(run.get("tags") or []),
                        _to_json({**(run.get("metadata") or {}), "imported_from_bundle": str(path)}),
                    ),
                )
                for span in trace.get("spans", []):
                    self._conn.execute(
                        """
                        INSERT INTO spans (
                            span_id, run_id, parent_span_id, type, name, started_at,
                            ended_at, status, input_ref, output_ref, attributes_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            span["span_id"],
                            run_id,
                            span.get("parent_span_id"),
                            span["type"],
                            span["name"],
                            span["started_at"],
                            span.get("ended_at"),
                            span["status"],
                            span.get("input_ref"),
                            span.get("output_ref"),
                            _to_json(span.get("attributes") or {}),
                        ),
                    )
                for event in trace.get("events", []):
                    self._conn.execute(
                        """
                        INSERT INTO events (
                            event_id, run_id, span_id, type, ts, message, attributes_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event["event_id"],
                            run_id,
                            event.get("span_id"),
                            event["type"],
                            event["ts"],
                            event.get("message"),
                            _to_json(event.get("attributes") or {}),
                        ),
                    )
                for artifact in artifacts:
                    artifact_id = artifact["artifact_id"]
                    payload = artifact_payloads[artifact_id]
                    digest = artifact["hash"]
                    artifact_path = self.objects_dir / "sha256" / digest[:2] / digest[2:4] / digest
                    artifact_path.parent.mkdir(parents=True, exist_ok=True)
                    if not artifact_path.exists():
                        artifact_path.write_bytes(payload)
                    self._conn.execute(
                        """
                        INSERT INTO artifacts (
                            artifact_id, run_id, span_id, hash, kind, media_type,
                            path, size, created_at, redacted
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            artifact_id,
                            run_id,
                            artifact.get("span_id"),
                            digest,
                            artifact["kind"],
                            artifact["media_type"],
                            str(artifact_path.relative_to(self.root)),
                            len(payload),
                            artifact["created_at"],
                            int(bool(artifact.get("redacted"))),
                        ),
                    )
                for annotation in trace.get("annotations", []):
                    self._conn.execute(
                        """
                        INSERT INTO annotations (annotation_id, run_id, span_id, message, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            annotation["annotation_id"],
                            run_id,
                            annotation.get("span_id"),
                            annotation["message"],
                            annotation["created_at"],
                        ),
                    )
                for fixture in trace.get("fixtures", []):
                    self._conn.execute(
                        """
                        INSERT INTO replay_fixtures (fixture_id, run_id, name, created_at, fixture_json)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            fixture["fixture_id"],
                            run_id,
                            fixture["name"],
                            fixture["created_at"],
                            _to_json(fixture.get("fixture") or {}),
                        ),
                    )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        return {
            "run_id": run_id,
            "bundle": str(path),
            "manifest": manifest,
            "counts": manifest.get("counts") or {},
            "skipped": False,
            "conflict": bool(existing_run),
            "remapped": remapped,
            "original_run_id": original_run_id,
            "id_map": id_map,
        }

    def _run_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "run_id": row["run_id"],
            "name": row["name"],
            "status": row["status"],
            "created_at": row["created_at"],
            "ended_at": row["ended_at"],
            "source": row["source"],
            "agent": _from_json(row["agent_json"], {}),
            "environment": _from_json(row["environment_json"], {}),
            "tags": _from_json(row["tags_json"], []),
            "metadata": _from_json(row["metadata_json"], {}),
        }

    def _span_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "span_id": row["span_id"],
            "run_id": row["run_id"],
            "parent_span_id": row["parent_span_id"],
            "type": row["type"],
            "name": row["name"],
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "status": row["status"],
            "input_ref": row["input_ref"],
            "output_ref": row["output_ref"],
            "attributes": _from_json(row["attributes_json"], {}),
        }

    def _event_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "event_id": row["event_id"],
            "run_id": row["run_id"],
            "span_id": row["span_id"],
            "type": row["type"],
            "ts": row["ts"],
            "message": row["message"],
            "attributes": _from_json(row["attributes_json"], {}),
        }

    def _artifact_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "artifact_id": row["artifact_id"],
            "run_id": row["run_id"],
            "span_id": row["span_id"],
            "hash": row["hash"],
            "kind": row["kind"],
            "media_type": row["media_type"],
            "path": row["path"],
            "size": row["size"],
            "created_at": row["created_at"],
            "redacted": bool(row["redacted"]),
        }

    def _fixture_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "fixture_id": row["fixture_id"],
            "run_id": row["run_id"],
            "name": row["name"],
            "created_at": row["created_at"],
            "fixture": _from_json(row["fixture_json"], {}),
        }


def _safe_bundle_id(value: str) -> bool:
    if not value or "/" in value or "\\" in value or ".." in value:
        return False
    return all(character.isalnum() or character in {"_", "-"} for character in value)


def _safe_export_token(value: str) -> str:
    token = "".join(character if character.isalnum() or character in {"_", "-", "."} else "-" for character in str(value))
    token = token.strip("-")[:120]
    return token or "compare"


def _normalize_compare_format(fmt: str) -> str:
    if fmt == "md":
        return "markdown"
    if fmt in {"markdown", "json"}:
        return fmt
    raise ValueError("compare export format must be one of: markdown, md, json")


def format_compare_export(payload: Dict[str, Any], fmt: str = "markdown") -> str:
    normalized = _normalize_compare_format(fmt)
    if normalized == "json":
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"
    return _format_compare_markdown(payload)


def format_compare_briefing(packet: Dict[str, Any], text_limit: int = 2000) -> str:
    packet = _validate_compare_packet(packet)
    span = packet.get("span") or {}
    pair = packet.get("pair") or {}
    artifacts = packet.get("artifacts") or {}
    pair_type = pair.get("type") or "compare"
    pair_label = pair.get("label") or pair_type
    span_name = span.get("name") or span.get("span_id") or "span"
    lines = [
        f"Agent Compare Investigation: {pair_label}",
        "",
        f"Source Run: {packet.get('run_id') or ''}",
        f"Source Span: {span_name}",
        f"Source Span ID: {span.get('span_id') or ''}",
        f"Pair Type: {pair_type}",
        f"Exported: {packet.get('exported_at') or ''}",
        "",
        "Left Artifact:",
        *_compare_briefing_artifact_lines(artifacts["left"], text_limit),
        "",
        "Right Artifact:",
        *_compare_briefing_artifact_lines(artifacts["right"], text_limit),
        "",
        "Suggested Next Steps:",
        "- Inspect the left body against the right body for mismatch, loss, or unexpected transformation.",
        "- Open the source trace and inspect nearby events around the source span.",
        "- Add annotations or fixtures once the suspected cause is reproduced.",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _format_compare_markdown(payload: Dict[str, Any]) -> str:
    span = payload.get("span") or {}
    pair = payload.get("pair") or {}
    artifacts = payload.get("artifacts") or {}
    span_name = span.get("name") or span.get("span_id") or "Span"
    return "\n".join(
        [
            "# Agent Black Box Compare Export",
            "",
            f"- Run: {payload.get('run_id') or ''}",
            f"- Span: {span_name}",
            f"- Span ID: {span.get('span_id') or ''}",
            f"- Pair: {pair.get('label') or ''}",
            f"- Exported: {payload.get('exported_at') or ''}",
            "",
            "## Left Artifact",
            _format_compare_markdown_artifact(artifacts.get("left") or {}),
            "",
            "## Right Artifact",
            _format_compare_markdown_artifact(artifacts.get("right") or {}),
            "",
        ]
    )


def _format_compare_markdown_artifact(artifact: Dict[str, Any]) -> str:
    redacted = " (redacted)" if artifact.get("redacted") else ""
    return "\n".join(
        [
            f"- Role: {artifact.get('role') or ''}",
            f"- Artifact ID: {artifact.get('artifact_id') or ''}",
            f"- Kind: {artifact.get('kind') or ''}",
            f"- Media Type: {artifact.get('media_type') or ''}",
            f"- Size: {artifact.get('size') or 0} bytes{redacted}",
            "",
            _markdown_fence(str(artifact.get("text") or "")),
        ]
    )


def _compare_briefing_artifact_lines(artifact: Dict[str, Any], text_limit: int) -> List[str]:
    redacted = " yes" if artifact.get("redacted") else " no"
    return [
        f"- Role: {artifact.get('role') or ''}",
        f"- Artifact ID: {artifact.get('artifact_id') or ''}",
        f"- Kind: {artifact.get('kind') or ''}",
        f"- Media Type: {artifact.get('media_type') or ''}",
        f"- Size: {artifact.get('size') or 0} bytes",
        f"- Redacted:{redacted}",
        "",
        "Body:",
        _markdown_fence(_truncate_compare_text(str(artifact.get("text") or ""), text_limit)),
    ]


def _truncate_compare_text(text: str, limit: int) -> str:
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return text[:limit].rstrip() + f"\n... truncated {omitted} characters"


def _markdown_fence(text: str) -> str:
    longest = 2
    current = 0
    for character in text:
        if character == "`":
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    fence = "`" * (longest + 1)
    return f"{fence}\n{text}\n{fence}"


def _select_compare_pair(
    groups: List[Dict[str, Any]],
    span_id: Optional[str],
    pair: str,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    requested_pair = pair or "auto"
    if requested_pair != "auto" and requested_pair not in _COMPARE_PAIR_DEFS:
        raise ValueError("compare pair must be one of: auto, " + ", ".join(COMPARE_PAIR_TYPES))

    candidate_groups = groups
    if span_id:
        candidate_groups = [group for group in groups if group.get("span_id") == span_id]
        if not candidate_groups:
            raise ValueError(f"Span has no comparable artifact group: {span_id}")

    for group in candidate_groups:
        pairs = _compare_pairs_for_group(group)
        if requested_pair == "auto" and pairs:
            return group, pairs[0]
        for candidate in pairs:
            if candidate["type"] == requested_pair:
                return group, candidate

    if span_id:
        available = [pair["type"] for pair in _compare_pairs_for_group(candidate_groups[0])]
        suffix = f" Available pairs: {', '.join(available)}." if available else ""
        raise ValueError(f"Span does not have compare pair: {requested_pair}.{suffix}")
    raise ValueError(f"Run has no comparable artifact pair for: {requested_pair}")


def _compare_pairs_for_group(group: Dict[str, Any]) -> List[Dict[str, Any]]:
    by_role: Dict[str, Dict[str, Any]] = {}
    for artifact in group.get("artifacts") or []:
        role = artifact.get("role") or artifact.get("ref") or ""
        if role and role not in by_role:
            by_role[role] = artifact

    pairs: List[Dict[str, Any]] = []
    seen = set()
    for pair_type in COMPARE_PAIR_TYPES:
        label, left_role, right_role = _COMPARE_PAIR_DEFS[pair_type]
        left = by_role.get(left_role)
        right = by_role.get(right_role)
        if not left or not right or left.get("artifact_id") == right.get("artifact_id"):
            continue
        key = f"{left.get('artifact_id')}::{right.get('artifact_id')}"
        if key in seen:
            continue
        seen.add(key)
        pairs.append({"type": pair_type, "label": label, "left": left, "right": right, "key": key})
    return pairs


def _compare_export_payload(
    run_id: str,
    group: Dict[str, Any],
    pair: Dict[str, Any],
    left_text: str,
    right_text: str,
) -> Dict[str, Any]:
    return {
        "kind": "agent_black_box.compare_pair",
        "schema_version": 1,
        "exported_at": utc_now(),
        "run_id": run_id,
        "span": {
            "span_id": group.get("span_id") or "",
            "name": group.get("name") or "",
            "type": group.get("type") or "",
            "status": group.get("status") or "",
            "ts": group.get("ts") or "",
        },
        "pair": {
            "key": pair.get("key") or "",
            "type": pair.get("type") or "",
            "label": pair.get("label") or "",
        },
        "artifacts": {
            "left": _compare_export_artifact(pair["left"], left_text),
            "right": _compare_export_artifact(pair["right"], right_text),
        },
    }


def _compare_export_artifact(artifact: Dict[str, Any], text: str) -> Dict[str, Any]:
    return {
        "artifact_id": artifact.get("artifact_id"),
        "role": artifact.get("role") or artifact.get("ref") or "artifact",
        "kind": artifact.get("kind") or "",
        "media_type": artifact.get("media_type") or "application/octet-stream",
        "size": artifact.get("size") if artifact.get("size") is not None else len(text),
        "source": artifact.get("source") or "",
        "redacted": bool(artifact.get("redacted")),
        "text": text,
    }


def compare_evidence_artifacts(timeline: Dict[str, Any]) -> Dict[str, Optional[Dict[str, Any]]]:
    artifact_by_kind: Dict[str, Dict[str, Any]] = {}
    for artifact in timeline.get("artifacts") or []:
        kind = artifact.get("kind")
        if kind and kind not in artifact_by_kind:
            artifact_by_kind[kind] = artifact
    return {part: artifact_by_kind.get(kind) for part, kind in COMPARE_EVIDENCE_PARTS.items()}


def decode_compare_evidence_content(part: str, content: bytes, raw: bool = False) -> str:
    text = content.decode("utf-8", errors="replace")
    if raw or part not in {"left", "right"}:
        return text
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text
    if isinstance(payload, dict) and "text" in payload:
        return str(payload.get("text") or "")
    return text


def _compare_evidence_summary(timeline: Dict[str, Any]) -> Dict[str, Any]:
    run = timeline.get("run") or {}
    metadata = run.get("metadata") or {}
    return {
        "run_id": run.get("run_id"),
        "source_run_id": metadata.get("source_compare_run_id"),
        "source_span_id": metadata.get("source_compare_span_id"),
        "source_span_name": metadata.get("source_compare_span_name"),
        "pair_type": metadata.get("source_compare_pair_type"),
        "pair_label": metadata.get("source_compare_pair_label"),
        "evidence": compare_evidence_artifacts(timeline),
    }


def _validate_compare_investigation_timeline(timeline: Dict[str, Any]) -> None:
    run = timeline.get("run") or {}
    metadata = run.get("metadata") or {}
    if run.get("source") != "compare-ingest" and not metadata.get("source_compare_run_id"):
        raise ValueError(f"Run is not a compare investigation: {run.get('run_id') or ''}")


def _compare_ingest_body(side: str, artifact: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "side": side,
        "source_artifact": {
            "artifact_id": artifact.get("artifact_id"),
            "role": artifact.get("role") or "",
            "kind": artifact.get("kind") or "",
            "media_type": artifact.get("media_type") or "",
            "size": artifact.get("size") or 0,
            "source": artifact.get("source") or "",
            "redacted": bool(artifact.get("redacted")),
        },
        "text": str(artifact.get("text") or ""),
    }


def _compact_linked_run(run: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not run:
        return None
    return {
        "run_id": run["run_id"],
        "name": run["name"],
        "status": run["status"],
        "created_at": run["created_at"],
        "source": run["source"],
    }


def _handoff_packet(
    timeline: Dict[str, Any],
    fixtures: List[Dict[str, Any]],
) -> Dict[str, Any]:
    run = timeline["run"]
    return {
        "handoff_version": "0.1",
        "generated_at": utc_now(),
        "run": {
            "run_id": run["run_id"],
            "name": run["name"],
            "status": run["status"],
            "source": run["source"],
            "created_at": run["created_at"],
            "ended_at": run.get("ended_at"),
            "tags": run.get("tags") or [],
        },
        "provenance": _handoff_provenance(run),
        "counts": {
            "spans": len(timeline["spans"]),
            "events": len(timeline["events"]),
            "artifacts": len(timeline["artifacts"]),
            "annotations": len(timeline["annotations"]),
            "fixtures": len(fixtures),
        },
        "summary": timeline.get("summary") or _timeline_summary(timeline),
        "debug_path": timeline.get("debug_path") or _debug_path(timeline),
        "artifact_groups": timeline.get("artifact_groups") or _artifact_groups(timeline),
        "attention": _handoff_attention(timeline),
        "timeline": [_compact_timeline_item(item) for item in timeline["items"]],
        "artifacts": [_compact_artifact(artifact) for artifact in timeline["artifacts"]],
        "annotations": timeline["annotations"],
        "fixtures": [_compact_fixture(fixture) for fixture in fixtures],
        "suggested_next_steps": _handoff_next_steps(timeline, fixtures),
    }


def _timeline_summary(timeline: Dict[str, Any]) -> Dict[str, Any]:
    spans = timeline.get("spans") or []
    events = timeline.get("events") or []
    artifacts = timeline.get("artifacts") or []
    annotations = timeline.get("annotations") or []
    model_spans = [span for span in spans if span.get("type") == "model.call"]
    warning_events = [
        event for event in events
        if "warn" in f"{event.get('type') or ''} {event.get('message') or ''}".lower()
    ]
    error_events = [
        event for event in events
        if any(marker in f"{event.get('type') or ''} {event.get('message') or ''}".lower() for marker in ("error", "fail", "exception"))
    ]
    failed_spans = [span for span in spans if span.get("status") not in {None, "", "ok", "running"}]
    first_failure = _first_failure(failed_spans, error_events)
    usage = _summary_usage(model_spans, events)
    return {
        "model_calls": len(model_spans),
        "tool_calls": sum(1 for span in spans if span.get("type") == "tool.call"),
        "graph_nodes": sum(1 for span in spans if span.get("type") in {"graph.node", "langgraph.node"}),
        "warnings": len(warning_events),
        "errors": len(error_events) + len(failed_spans),
        "artifacts": len(artifacts),
        "annotations": len(annotations),
        "usage": usage,
        "first_failure": first_failure,
    }


def _summary_usage(spans: List[Dict[str, Any]], events: List[Dict[str, Any]]) -> Dict[str, int]:
    totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    seen = False
    for item in spans:
        usage = usage_from_attributes(item.get("attributes") or {})
        if not usage:
            continue
        seen = True
        for key in totals:
            if isinstance(usage.get(key), int):
                totals[key] += usage[key]
    if not seen:
        for item in events:
            usage = usage_from_attributes(item.get("attributes") or {})
            if not usage:
                continue
            seen = True
            for key in totals:
                if isinstance(usage.get(key), int):
                    totals[key] += usage[key]
    return totals if seen else {}


def _first_failure(
    failed_spans: List[Dict[str, Any]],
    error_events: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for span in failed_spans:
        candidates.append(
            {
                "kind": "span",
                "id": span.get("span_id"),
                "type": span.get("type"),
                "title": span.get("name"),
                "status": span.get("status"),
                "ts": span.get("started_at"),
            }
        )
    for event in error_events:
        candidates.append(
            {
                "kind": "event",
                "id": event.get("event_id"),
                "type": event.get("type"),
                "title": event.get("message") or event.get("type"),
                "span_id": event.get("span_id"),
                "ts": event.get("ts"),
            }
        )
    candidates.sort(key=lambda item: item.get("ts") or "")
    return candidates[0] if candidates else None


def _debug_path(timeline: Dict[str, Any]) -> List[Dict[str, Any]]:
    spans = timeline.get("spans") or []
    events = timeline.get("events") or []
    annotations = timeline.get("annotations") or []
    artifacts = {
        artifact.get("artifact_id"): artifact
        for artifact in timeline.get("artifacts") or []
        if artifact.get("artifact_id")
    }
    path: List[Dict[str, Any]] = []

    for span in spans:
        if span.get("status") not in {None, "", "ok", "running"}:
            label = "Failed tool" if span.get("type") == "tool.call" else "Failed span"
            path.append(
                _debug_item(
                    priority=10,
                    severity="critical",
                    kind="span",
                    item=span,
                    label=label,
                    reason=f"Span ended with status {span.get('status') or 'unknown'}.",
                    suggested_action=_span_action(span),
                    artifacts=artifacts,
                )
            )

    for event in events:
        event_type = event.get("type") or ""
        message = event.get("message") or ""
        haystack = f"{event_type} {message}".lower()
        if any(marker in haystack for marker in ("error", "fail", "exception")):
            label = "Failed tool" if event_type == "tool.failed" else "Failure event"
            path.append(
                _debug_item(
                    priority=12,
                    severity="critical",
                    kind="event",
                    item=event,
                    label=label,
                    reason="The event reports a failure or exception.",
                    suggested_action=_event_action(event),
                    artifacts=artifacts,
                )
            )
        elif "warn" in haystack:
            path.append(
                _debug_item(
                    priority=20,
                    severity="warning",
                    kind="event",
                    item=event,
                    label="Warning",
                    reason="The run emitted a warning before or during execution.",
                    suggested_action=_event_action(event),
                    artifacts=artifacts,
                )
            )

    for annotation in annotations:
        message = annotation.get("message") or ""
        concern = any(marker in message.lower() for marker in ("bad", "wrong", "fail", "error", "warning", "regression"))
        path.append(
            {
                "priority": "warning" if concern else "note",
                "rank": 30 if concern else 40,
                "kind": "annotation",
                "id": annotation.get("annotation_id"),
                "span_id": annotation.get("span_id"),
                "type": "annotation",
                "label": "Annotated concern" if concern else "Annotation",
                "title": message,
                "ts": annotation.get("created_at"),
                "reason": "A human note flags this as worth inspecting." if concern else "A human note adds debugging context.",
                "suggested_action": "Read the linked span and nearby timeline events.",
                "refs": _refs_from_item(annotation),
                "artifact_refs": _artifact_refs(_refs_from_item(annotation), artifacts),
            }
        )

    if not path:
        first_decision = next(
            (
                span for span in spans
                if span.get("type") in {"model.call", "tool.call", "langgraph.node", "graph.node"}
            ),
            None,
        )
        if first_decision:
            path.append(
                _debug_item(
                    priority=50,
                    severity="context",
                    kind="span",
                    item=first_decision,
                    label="First decision point",
                    reason="No failures or warnings were detected, so start with the first model, tool, or graph node.",
                    suggested_action=_span_action(first_decision),
                    artifacts=artifacts,
                )
            )

    path.sort(key=lambda item: (item.get("rank", 99), item.get("ts") or ""))
    for index, item in enumerate(path[:8], start=1):
        item["step"] = index
        item.pop("rank", None)
    return path[:8]


def _debug_item(
    priority: int,
    severity: str,
    kind: str,
    item: Dict[str, Any],
    label: str,
    reason: str,
    suggested_action: str,
    artifacts: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    refs = _refs_from_item(item)
    return {
        "priority": severity,
        "rank": priority,
        "kind": kind,
        "id": item.get("span_id") or item.get("event_id"),
        "span_id": item.get("span_id"),
        "type": item.get("type"),
        "label": label,
        "title": item.get("name") or item.get("message") or item.get("type"),
        "status": item.get("status"),
        "ts": item.get("started_at") or item.get("ts"),
        "reason": reason,
        "suggested_action": suggested_action,
        "refs": refs,
        "artifact_refs": _artifact_refs(refs, artifacts),
    }


def _span_action(span: Dict[str, Any]) -> str:
    span_type = span.get("type")
    if span_type == "tool.call":
        return "Open the tool input/output artifacts and compare the arguments with the result."
    if span_type == "model.call":
        return "Open the model request/response artifacts and check the prompt, output, and usage."
    if span_type in {"langgraph.node", "graph.node"}:
        return "Open the node input/output artifacts and compare the state transition."
    return "Open referenced artifacts and inspect nearby events."


def _event_action(event: Dict[str, Any]) -> str:
    attributes = event.get("attributes") or {}
    if any(key.endswith("_ref") for key in attributes):
        return "Open referenced artifacts from the event attributes."
    if event.get("span_id"):
        return "Inspect the linked span and adjacent timeline events."
    return "Inspect adjacent timeline events for the cause."


def _validate_handoff_packet(packet: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(packet, dict):
        raise ValueError("handoff packet must be a JSON object")
    run = packet.get("run")
    if not isinstance(run, dict) or not run.get("run_id"):
        raise ValueError("handoff packet must include run.run_id")
    return run


def _validate_compare_packet(packet: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(packet, dict):
        raise ValueError("compare packet must be a JSON object")
    if packet.get("kind") != "agent_black_box.compare_pair":
        raise ValueError("compare packet kind must be agent_black_box.compare_pair")
    if not packet.get("run_id"):
        raise ValueError("compare packet must include run_id")
    span = packet.get("span")
    if not isinstance(span, dict) or not span.get("span_id"):
        raise ValueError("compare packet must include span.span_id")
    pair = packet.get("pair")
    if not isinstance(pair, dict) or not (pair.get("type") or pair.get("label")):
        raise ValueError("compare packet must include pair.type or pair.label")
    artifacts = packet.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("compare packet must include artifacts")
    for side in ("left", "right"):
        artifact = artifacts.get(side)
        if not isinstance(artifact, dict):
            raise ValueError(f"compare packet must include artifacts.{side}")
        if "text" not in artifact:
            raise ValueError(f"compare packet must include artifacts.{side}.text")
    return packet


def _handoff_provenance(run: Dict[str, Any]) -> Dict[str, Any]:
    metadata = run.get("metadata") or {}
    return {
        "imported_from_bundle": metadata.get("imported_from_bundle"),
        "remapped_from_run_id": metadata.get("remapped_from_run_id"),
    }


def _handoff_attention(timeline: Dict[str, Any]) -> List[Dict[str, Any]]:
    attention: List[Dict[str, Any]] = []
    for span in timeline["spans"]:
        if span.get("status") not in {None, "", "ok", "running"}:
            attention.append(
                {
                    "kind": "span",
                    "id": span["span_id"],
                    "type": span["type"],
                    "status": span.get("status"),
                    "title": span.get("name"),
                    "ts": span.get("started_at"),
                }
            )
    for event in timeline["events"]:
        event_type = event.get("type") or ""
        message = event.get("message") or ""
        haystack = f"{event_type} {message}".lower()
        if any(marker in haystack for marker in ("error", "fail", "warn", "exception")):
            attention.append(
                {
                    "kind": "event",
                    "id": event["event_id"],
                    "type": event_type,
                    "span_id": event.get("span_id"),
                    "title": message or event_type,
                    "ts": event.get("ts"),
                }
            )
    for annotation in timeline["annotations"]:
        attention.append(
            {
                "kind": "annotation",
                "id": annotation["annotation_id"],
                "span_id": annotation.get("span_id"),
                "title": annotation["message"],
                "ts": annotation["created_at"],
            }
        )
    attention.sort(key=lambda item: item.get("ts") or "")
    return attention[:25]


def _compact_timeline_item(item: Dict[str, Any]) -> Dict[str, Any]:
    attributes = item.get("attributes") or {}
    refs = _refs_from_item(item)
    compact = {
        "kind": item.get("kind"),
        "id": item.get("span_id") or item.get("event_id"),
        "type": item.get("type"),
        "title": item.get("name") or item.get("message") or item.get("type"),
        "status": item.get("status"),
        "ts": item.get("ts") or item.get("started_at"),
        "refs": refs,
        "attribute_keys": sorted(attributes.keys()),
    }
    usage = usage_from_attributes(attributes)
    if usage:
        compact["usage"] = usage
    return compact


def _refs_from_item(item: Dict[str, Any]) -> Dict[str, Any]:
    attributes = item.get("attributes") or {}
    refs: Dict[str, Any] = {}
    for key in ("input_ref", "output_ref", "span_id", "parent_span_id"):
        if item.get(key):
            refs[key] = item[key]
    for key, value in attributes.items():
        if key.endswith("_ref") or key.endswith("_id"):
            refs[key] = value
    return refs


def _artifact_refs(refs: Dict[str, Any], artifacts: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    artifact_refs = []
    seen = set()
    for key in sorted(refs):
        artifact_id = refs[key]
        if artifact_id in seen or artifact_id not in artifacts:
            continue
        artifact = artifacts[artifact_id]
        artifact_refs.append(
            {
                "ref": key,
                "artifact_id": artifact_id,
                "kind": artifact.get("kind"),
                "media_type": artifact.get("media_type"),
                "size": artifact.get("size"),
                "redacted": bool(artifact.get("redacted")),
            }
        )
        seen.add(artifact_id)
    return artifact_refs


def _artifact_groups(timeline: Dict[str, Any]) -> List[Dict[str, Any]]:
    artifacts = {
        artifact.get("artifact_id"): artifact
        for artifact in timeline.get("artifacts") or []
        if artifact.get("artifact_id")
    }
    artifacts_by_span: Dict[str, List[Dict[str, Any]]] = {}
    for artifact in timeline.get("artifacts") or []:
        span_id = artifact.get("span_id")
        if span_id:
            artifacts_by_span.setdefault(span_id, []).append(artifact)

    events_by_span: Dict[str, List[Dict[str, Any]]] = {}
    for event in timeline.get("events") or []:
        span_id = event.get("span_id")
        if span_id:
            events_by_span.setdefault(span_id, []).append(event)

    groups: List[Dict[str, Any]] = []
    for span in timeline.get("spans") or []:
        span_id = span.get("span_id")
        refs = _refs_from_item(span)
        ref_sources = {key: "span" for key in refs}
        for event in events_by_span.get(span_id, []):
            for key, value in _refs_from_item(event).items():
                refs.setdefault(key, value)
                ref_sources.setdefault(key, event.get("type") or "event")

        related: List[Dict[str, Any]] = []
        seen = set()
        for ref in _artifact_refs(refs, artifacts):
            artifact_id = ref["artifact_id"]
            related.append(
                {
                    **ref,
                    "role": _artifact_role(ref.get("ref"), ref.get("kind")),
                    "source": ref_sources.get(ref.get("ref") or "", "span"),
                }
            )
            seen.add(artifact_id)

        for artifact in artifacts_by_span.get(span_id, []):
            artifact_id = artifact.get("artifact_id")
            if not artifact_id or artifact_id in seen:
                continue
            related.append(
                {
                    "ref": "span_artifact",
                    "artifact_id": artifact_id,
                    "kind": artifact.get("kind"),
                    "media_type": artifact.get("media_type"),
                    "size": artifact.get("size"),
                    "redacted": bool(artifact.get("redacted")),
                    "role": _artifact_role("span_artifact", artifact.get("kind")),
                    "source": "artifact.span_id",
                }
            )
            seen.add(artifact_id)

        if related:
            related.sort(key=lambda item: (_artifact_role_rank(item.get("role") or ""), item.get("kind") or ""))
            groups.append(
                {
                    "span_id": span_id,
                    "type": span.get("type"),
                    "name": span.get("name"),
                    "status": span.get("status"),
                    "ts": span.get("started_at"),
                    "artifact_count": len(related),
                    "artifacts": related,
                }
            )
    return groups


def _artifact_role(ref: Optional[str], kind: Optional[str]) -> str:
    ref = ref or ""
    kind = kind or ""
    if "schema" in ref or "schema" in kind:
        return "schema"
    if "request" in kind:
        return "request"
    if "response" in kind:
        return "response"
    if "input" in ref or "input" in kind:
        return "input"
    if "output" in ref or "output" in kind:
        return "output"
    if "transcript" in kind:
        return "transcript"
    if "briefing" in kind:
        return "briefing"
    if "packet" in kind:
        return "packet"
    return ref.replace("_ref", "") or "artifact"


def _artifact_role_rank(role: str) -> int:
    order = {
        "schema": 0,
        "request": 1,
        "input": 2,
        "response": 3,
        "output": 4,
        "transcript": 5,
        "packet": 6,
        "briefing": 7,
    }
    return order.get(role, 99)


def _compact_artifact(artifact: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "artifact_id": artifact["artifact_id"],
        "span_id": artifact.get("span_id"),
        "kind": artifact["kind"],
        "media_type": artifact["media_type"],
        "size": artifact["size"],
        "hash": artifact["hash"],
        "created_at": artifact["created_at"],
        "redacted": bool(artifact.get("redacted")),
    }


def _compact_fixture(fixture: Dict[str, Any]) -> Dict[str, Any]:
    expected = (fixture.get("fixture") or {}).get("expected") or {}
    return {
        "fixture_id": fixture["fixture_id"],
        "name": fixture["name"],
        "created_at": fixture["created_at"],
        "expected": expected,
    }


def _handoff_next_steps(
    timeline: Dict[str, Any],
    fixtures: List[Dict[str, Any]],
) -> List[str]:
    steps = [
        "Start with the debug path before scanning the full timeline.",
        "Review attention items for warnings, failures, and annotations.",
        "Open referenced artifacts for model/tool inputs and outputs.",
    ]
    if timeline["annotations"]:
        steps.append("Use annotations as human debugging hints.")
    if fixtures:
        steps.append("Replay an existing fixture to reproduce the observed behavior.")
    else:
        steps.append("Create a replay fixture if this run should become a regression case.")
    steps.append("Export the .abb bundle when a full portable trace is needed.")
    return steps


def _empty_bundle_id_map() -> Dict[str, Dict[str, str]]:
    return {
        "runs": {},
        "spans": {},
        "events": {},
        "artifacts": {},
        "annotations": {},
        "fixtures": {},
    }


def _bundle_id_map(trace: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    run = trace["run"]
    return {
        "runs": {run["run_id"]: new_id("run")},
        "spans": {span["span_id"]: new_id("span") for span in trace.get("spans", [])},
        "events": {event["event_id"]: new_id("evt") for event in trace.get("events", [])},
        "artifacts": {
            artifact["artifact_id"]: new_id("blob") for artifact in trace.get("artifacts", [])
        },
        "annotations": {
            annotation["annotation_id"]: new_id("ann")
            for annotation in trace.get("annotations", [])
        },
        "fixtures": {
            fixture["fixture_id"]: new_id("fix") for fixture in trace.get("fixtures", [])
        },
    }


def _flatten_bundle_id_map(id_map: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    flattened: Dict[str, str] = {}
    for group in id_map.values():
        flattened.update(group)
    return flattened


def _rewrite_bundle_refs(value: Any, id_map: Dict[str, str]) -> Any:
    if isinstance(value, str):
        return id_map.get(value, value)
    if isinstance(value, list):
        return [_rewrite_bundle_refs(item, id_map) for item in value]
    if isinstance(value, dict):
        return {
            id_map.get(key, key) if isinstance(key, str) else key: _rewrite_bundle_refs(item, id_map)
            for key, item in value.items()
        }
    return value


def _remap_bundle_trace(
    trace: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Dict[str, str]]]:
    id_map = _bundle_id_map(trace)
    original_run_id = trace["run"]["run_id"]
    remapped = _rewrite_bundle_refs(trace, _flatten_bundle_id_map(id_map))
    metadata = remapped["run"].setdefault("metadata", {})
    metadata["remapped_from_run_id"] = original_run_id
    return remapped, id_map
