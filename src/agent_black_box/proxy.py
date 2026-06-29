from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional, Tuple
from urllib import error, request

from .storage import ABBStore
from .usage import extract_usage


HOP_BY_HOP_HEADERS = {
    "connection",
    "content-length",
    "host",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def proxy_openai_request(
    store: ABBStore,
    method: str,
    path: str,
    query: str,
    headers: Dict[str, str],
    body: bytes,
) -> Tuple[int, Dict[str, str], bytes]:
    base_url = os.environ.get("ABB_OPENAI_BASE_URL", "https://api.openai.com").rstrip("/")
    upstream_path = path[len("/proxy/openai") :] or "/"
    if query:
        upstream_path = upstream_path + "?" + query
    upstream_url = base_url + upstream_path

    parsed_payload = _parse_json(body)
    model = parsed_payload.get("model") if isinstance(parsed_payload, dict) else None
    run_id = headers.get("X-ABB-Run-Id")
    created_run = False
    if not run_id or not store.get_run(run_id):
        run = store.create_run(
            {
                "name": f"OpenAI proxy {model or upstream_path}",
                "source": "openai-proxy",
                "agent": {"name": "openai-proxy"},
                "metadata": {"method": method, "path": upstream_path},
            }
        )
        run_id = run["run_id"]
        created_run = True

    request_artifact = store.add_artifact(
        run_id,
        None,
        "model.request",
        json.dumps(parsed_payload, indent=2, sort_keys=True) if parsed_payload is not None else body,
        media_type="application/json" if parsed_payload is not None else "application/octet-stream",
    )
    span = store.start_span(
        {
            "run_id": run_id,
            "type": "model.call",
            "name": f"OpenAI {model or upstream_path}",
            "input_ref": request_artifact["artifact_id"],
            "attributes": {
                "provider": "openai-compatible",
                "model": model,
                "method": method,
                "path": upstream_path,
                "stream_requested": bool(isinstance(parsed_payload, dict) and parsed_payload.get("stream")),
            },
        }
    )

    if isinstance(parsed_payload, dict) and parsed_payload.get("stream"):
        store.add_event(
            {
                "run_id": run_id,
                "span_id": span["span_id"],
                "type": "warning.detected",
                "message": "Proxy MVP buffers streaming responses before returning them.",
            }
        )

    started = time.perf_counter()
    try:
        upstream_headers = _upstream_headers(headers)
        if "Authorization" not in upstream_headers and os.environ.get("OPENAI_API_KEY"):
            upstream_headers["Authorization"] = f"Bearer {os.environ['OPENAI_API_KEY']}"
        if "Authorization" not in upstream_headers:
            raise MissingCredential("Missing Authorization header or OPENAI_API_KEY")

        req = request.Request(upstream_url, data=body, method=method, headers=upstream_headers)
        with request.urlopen(req, timeout=float(os.environ.get("ABB_PROXY_TIMEOUT", "120"))) as response:
            response_body = response.read()
            response_headers = _response_headers(dict(response.headers.items()))
            status = response.status
    except MissingCredential as exc:
        response_body = json.dumps({"error": str(exc)}).encode("utf-8")
        response_headers = {"content-type": "application/json"}
        status = 401
        store.add_event({"run_id": run_id, "span_id": span["span_id"], "type": "error", "message": str(exc)})
    except error.HTTPError as exc:
        response_body = exc.read()
        response_headers = _response_headers(dict(exc.headers.items()))
        status = exc.code
        store.add_event(
            {
                "run_id": run_id,
                "span_id": span["span_id"],
                "type": "error",
                "message": f"OpenAI upstream returned HTTP {exc.code}",
            }
        )
    except error.URLError as exc:
        response_body = json.dumps({"error": str(exc)}).encode("utf-8")
        response_headers = {"content-type": "application/json"}
        status = 502
        store.add_event({"run_id": run_id, "span_id": span["span_id"], "type": "error", "message": str(exc)})

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    parsed_response = _parse_json(response_body)
    usage = extract_usage(parsed_response)
    response_artifact = store.add_artifact(
        run_id,
        span["span_id"],
        "model.response",
        _decode_response(response_body),
        media_type=response_headers.get("content-type", "application/octet-stream"),
    )
    event_attributes: Dict[str, Any] = {
        "status_code": status,
        "duration_ms": duration_ms,
        "request_ref": request_artifact["artifact_id"],
        "response_ref": response_artifact["artifact_id"],
    }
    span_attributes: Dict[str, Any] = {"status_code": status, "duration_ms": duration_ms}
    if usage:
        event_attributes["usage"] = usage
        span_attributes["usage"] = usage
    store.add_event(
        {
            "run_id": run_id,
            "span_id": span["span_id"],
            "type": "model.completed" if status < 400 else "model.failed",
            "message": f"OpenAI proxy returned HTTP {status}",
            "attributes": event_attributes,
        }
    )
    store.end_span(
        span["span_id"],
        status="ok" if status < 400 else "error",
        output_ref=response_artifact["artifact_id"],
        attributes=span_attributes,
    )
    if created_run:
        store.end_run(run_id, status="ok" if status < 400 else "error")

    response_headers["x-abb-run-id"] = run_id
    return status, response_headers, response_body


class MissingCredential(Exception):
    pass


def _parse_json(body: bytes) -> Optional[Any]:
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _decode_response(body: bytes) -> Any:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return body
    parsed = _parse_json(body)
    if parsed is not None:
        return json.dumps(parsed, indent=2, sort_keys=True)
    return text


def _upstream_headers(headers: Dict[str, str]) -> Dict[str, str]:
    output: Dict[str, str] = {}
    for key, value in headers.items():
        lowered = key.lower()
        if lowered in HOP_BY_HOP_HEADERS or lowered.startswith("x-abb-"):
            continue
        output[key] = value
    if "Content-Type" not in output and "content-type" not in {key.lower() for key in output}:
        output["Content-Type"] = "application/json"
    return output


def _response_headers(headers: Dict[str, str]) -> Dict[str, str]:
    output: Dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in HOP_BY_HOP_HEADERS:
            continue
        output[key.lower()] = value
    return output
