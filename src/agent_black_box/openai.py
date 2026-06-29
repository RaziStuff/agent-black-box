from __future__ import annotations

import json
import os
import time
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple, Union
from urllib import error, request

from .storage import ABBStore
from .usage import extract_usage


Transport = Callable[[str, str, Dict[str, str], bytes, float], Tuple[int, Dict[str, str], bytes]]


class OpenAIError(Exception):
    pass


class OpenAIMissingCredentialError(OpenAIError):
    pass


class OpenAIHTTPError(OpenAIError):
    def __init__(self, status_code: int, body: Union[str, bytes], run_id: str):
        self.status_code = status_code
        self.body = body
        self.run_id = run_id
        super().__init__(f"OpenAI-compatible request failed with HTTP {status_code} (ABB run {run_id})")


class OpenAIObject:
    def __init__(self, data: Any):
        self._data = data

    def __getitem__(self, key: Any) -> Any:
        return _wrap(self._data[key])

    def __iter__(self) -> Iterator[Any]:
        if isinstance(self._data, dict):
            return iter(self._data)
        if isinstance(self._data, list):
            return (_wrap(item) for item in self._data)
        return iter(())

    def __len__(self) -> int:
        return len(self._data) if hasattr(self._data, "__len__") else 0

    def __contains__(self, key: Any) -> bool:
        return key in self._data if isinstance(self._data, (dict, list, str)) else False

    def __getattr__(self, name: str) -> Any:
        if isinstance(self._data, dict) and name in self._data:
            return _wrap(self._data[name])
        raise AttributeError(name)

    def get(self, key: str, default: Any = None) -> Any:
        if not isinstance(self._data, dict):
            return default
        return _wrap(self._data.get(key, default))

    def items(self) -> Any:
        if not isinstance(self._data, dict):
            return {}.items()
        return self._data.items()

    def keys(self) -> Any:
        if not isinstance(self._data, dict):
            return {}.keys()
        return self._data.keys()

    def values(self) -> Any:
        if not isinstance(self._data, dict):
            return {}.values()
        return (_wrap(value) for value in self._data.values())

    def to_dict(self) -> Any:
        return self._data

    def __repr__(self) -> str:
        return repr(self._data)


class OpenAIResult(OpenAIObject):
    def __init__(self, data: Any, *, run_id: str, status_code: int, headers: Dict[str, str]):
        super().__init__(data)
        self.abb_run_id = run_id
        self.abb_status_code = status_code
        self.abb_response_headers = headers


class OpenAI:
    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        data_dir: Optional[str] = None,
        store: Optional[ABBStore] = None,
        timeout: Optional[float] = None,
        default_headers: Optional[Dict[str, str]] = None,
        transport: Optional[Transport] = None,
    ):
        self.api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY")
        self.base_url = (base_url or os.environ.get("ABB_OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.timeout = timeout if timeout is not None else float(os.environ.get("ABB_OPENAI_TIMEOUT", "120"))
        self.default_headers = default_headers or {}
        self._store = store or ABBStore(data_dir)
        self._owns_store = store is None
        self._transport = transport or _urllib_transport
        self.chat = _ChatResource(self)
        self.responses = _ResponsesResource(self)

    def close(self) -> None:
        if self._owns_store:
            self._store.close()

    def __enter__(self) -> "OpenAI":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def _post_json(self, path: str, payload: Dict[str, Any], resource: str) -> OpenAIResult:
        model = payload.get("model")
        run = self._store.create_run(
            {
                "name": f"OpenAI {resource} {model or path}",
                "source": "openai-wrapper",
                "agent": {"name": "openai-wrapper"},
                "metadata": {"method": "POST", "path": path, "resource": resource},
            }
        )
        run_id = run["run_id"]
        request_body = json.dumps(payload, sort_keys=True).encode("utf-8")
        request_artifact = self._store.add_artifact(
            run_id,
            None,
            "model.request",
            json.dumps(payload, indent=2, sort_keys=True),
            media_type="application/json",
        )
        span = self._store.start_span(
            {
                "run_id": run_id,
                "type": "model.call",
                "name": f"OpenAI {resource} {model or path}",
                "input_ref": request_artifact["artifact_id"],
                "attributes": {
                    "provider": "openai-compatible",
                    "model": model,
                    "method": "POST",
                    "path": path,
                    "resource": resource,
                    "stream_requested": bool(payload.get("stream")),
                },
            }
        )
        if payload.get("stream"):
            self._store.add_event(
                {
                    "run_id": run_id,
                    "span_id": span["span_id"],
                    "type": "warning.detected",
                    "message": "OpenAI wrapper MVP buffers streaming responses before returning them.",
                }
            )

        started = time.perf_counter()
        status = 0
        response_headers: Dict[str, str] = {}
        response_body = b""
        try:
            if not self.api_key:
                raise OpenAIMissingCredentialError("Missing api_key or OPENAI_API_KEY")
            status, response_headers, response_body = self._transport(
                "POST",
                _join_api_url(self.base_url, path),
                self._headers(),
                request_body,
                self.timeout,
            )
            if status >= 400:
                raise OpenAIHTTPError(status, _decode_body(response_body), run_id)
        except OpenAIMissingCredentialError as exc:
            response_body = json.dumps({"error": str(exc)}).encode("utf-8")
            response_headers = {"content-type": "application/json"}
            status = 401
            self._store.add_event({"run_id": run_id, "span_id": span["span_id"], "type": "error", "message": str(exc)})
            self._finish_recording(run_id, span["span_id"], request_artifact["artifact_id"], response_body, response_headers, status, started)
            raise
        except OpenAIHTTPError:
            self._store.add_event(
                {
                    "run_id": run_id,
                    "span_id": span["span_id"],
                    "type": "error",
                    "message": f"OpenAI-compatible upstream returned HTTP {status}",
                }
            )
            self._finish_recording(run_id, span["span_id"], request_artifact["artifact_id"], response_body, response_headers, status, started)
            raise
        except (error.URLError, TimeoutError, OSError) as exc:
            response_body = json.dumps({"error": str(exc)}).encode("utf-8")
            response_headers = {"content-type": "application/json"}
            status = 502
            self._store.add_event({"run_id": run_id, "span_id": span["span_id"], "type": "error", "message": str(exc)})
            self._finish_recording(run_id, span["span_id"], request_artifact["artifact_id"], response_body, response_headers, status, started)
            raise OpenAIError(f"OpenAI-compatible request failed: {exc}") from exc

        self._finish_recording(run_id, span["span_id"], request_artifact["artifact_id"], response_body, response_headers, status, started)
        parsed = _parse_body(response_body)
        return OpenAIResult(parsed, run_id=run_id, status_code=status, headers=response_headers)

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "agent-black-box-openai-wrapper/0.1",
        }
        headers.update(self.default_headers)
        return headers

    def _finish_recording(
        self,
        run_id: str,
        span_id: str,
        request_artifact_id: str,
        response_body: bytes,
        response_headers: Dict[str, str],
        status: int,
        started: float,
    ) -> None:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        parsed_response = _parse_body(response_body)
        usage = extract_usage(parsed_response)
        response_artifact = self._store.add_artifact(
            run_id,
            span_id,
            "model.response",
            _decode_body(parsed_response),
            media_type=_header(response_headers, "content-type") or "application/json",
        )
        event_attributes: Dict[str, Any] = {
            "status_code": status,
            "duration_ms": duration_ms,
            "request_ref": request_artifact_id,
            "response_ref": response_artifact["artifact_id"],
        }
        span_attributes: Dict[str, Any] = {"status_code": status, "duration_ms": duration_ms}
        if usage:
            event_attributes["usage"] = usage
            span_attributes["usage"] = usage
        self._store.add_event(
            {
                "run_id": run_id,
                "span_id": span_id,
                "type": "model.completed" if status < 400 else "model.failed",
                "message": f"OpenAI wrapper returned HTTP {status}",
                "attributes": event_attributes,
            }
        )
        self._store.end_span(
            span_id,
            status="ok" if status < 400 else "error",
            output_ref=response_artifact["artifact_id"],
            attributes=span_attributes,
        )
        self._store.end_run(run_id, status="ok" if status < 400 else "error")


class _ChatResource:
    def __init__(self, client: OpenAI):
        self.completions = _ChatCompletionsResource(client)


class _ChatCompletionsResource:
    def __init__(self, client: OpenAI):
        self._client = client

    def create(self, **payload: Any) -> OpenAIResult:
        return self._client._post_json("/chat/completions", payload, "chat.completions")


class _ResponsesResource:
    def __init__(self, client: OpenAI):
        self._client = client

    def create(self, **payload: Any) -> OpenAIResult:
        return self._client._post_json("/responses", payload, "responses")


def _urllib_transport(
    method: str,
    url: str,
    headers: Dict[str, str],
    body: bytes,
    timeout: float,
) -> Tuple[int, Dict[str, str], bytes]:
    req = request.Request(url, data=body, method=method, headers=headers)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return response.status, dict(response.headers.items()), response.read()
    except error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()


def _join_api_url(base_url: str, path: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return base + path
    return base + "/v1" + path


def _parse_body(body: bytes) -> Any:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return {"raw_base16": body.hex()}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def _decode_body(body_or_parsed: Any) -> Any:
    parsed = _parse_body(body_or_parsed) if isinstance(body_or_parsed, bytes) else body_or_parsed
    if isinstance(parsed, (dict, list)):
        return json.dumps(parsed, indent=2, sort_keys=True)
    return parsed


def _header(headers: Dict[str, str], name: str) -> Optional[str]:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None


def _wrap(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return OpenAIObject(value)
    return value
