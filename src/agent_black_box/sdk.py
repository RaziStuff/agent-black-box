from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import functools
import json
import os
import time
import traceback
from typing import Any, Callable, Dict, Iterator, Optional, TypeVar
from urllib import request
from urllib.error import HTTPError, URLError


F = TypeVar("F", bound=Callable[..., Any])

_current_run_id: ContextVar[Optional[str]] = ContextVar("abb_run_id", default=None)
_current_span_id: ContextVar[Optional[str]] = ContextVar("abb_span_id", default=None)


class ABBClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.base_url = (base_url or os.environ.get("ABB_DAEMON_URL") or "http://127.0.0.1:43188").rstrip("/")
        self.token = token if token is not None else os.environ.get("ABB_AUTH_TOKEN")
        self.timeout = timeout if timeout is not None else float(os.environ.get("ABB_TIMEOUT", "1.5"))
        self.enabled = os.environ.get("ABB_ENABLED", "true").lower() not in {"0", "false", "no"}

    def post(self, path: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        try:
            data = json.dumps(payload, sort_keys=True).encode("utf-8")
            req = request.Request(
                self.base_url + path,
                data=data,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            if self.token:
                req.add_header("Authorization", f"Bearer {self.token}")
            with request.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
            return None

    def get(self, path: str) -> Optional[Any]:
        if not self.enabled:
            return None
        try:
            req = request.Request(self.base_url + path, method="GET")
            if self.token:
                req.add_header("Authorization", f"Bearer {self.token}")
            with request.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
            return None


def get_client() -> ABBClient:
    return ABBClient()


@contextmanager
def record(
    name: str,
    *,
    tags: Optional[list] = None,
    metadata: Optional[Dict[str, Any]] = None,
    agent: Optional[Dict[str, Any]] = None,
    source: str = "python-sdk",
) -> Iterator[Optional[str]]:
    client = get_client()
    active_run_id = os.environ.get("ABB_ACTIVE_RUN_ID")
    run_id: Optional[str] = None
    span_id: Optional[str] = None
    run_token = None
    span_token = None
    status = "ok"

    if active_run_id:
        run_id = active_run_id
        span = client.post(
            "/v1/spans",
            {
                "run_id": run_id,
                "parent_span_id": _current_span_id.get(),
                "type": "agent.run",
                "name": name,
                "attributes": {"source": source, "tags": tags or [], "metadata": metadata or {}},
            },
        )
        if span:
            span_id = span.get("span_id")
    else:
        run = client.post(
            "/v1/runs",
            {
                "name": name,
                "source": source,
                "agent": agent or {"name": name},
                "tags": tags or [],
                "metadata": metadata or {},
            },
        )
        if run:
            run_id = run.get("run_id")

    if run_id:
        run_token = _current_run_id.set(run_id)
    if span_id:
        span_token = _current_span_id.set(span_id)

    try:
        yield run_id
    except Exception as exc:
        status = "error"
        if run_id:
            record_event(
                "error",
                message=str(exc),
                attributes={"traceback": traceback.format_exc()},
            )
        raise
    finally:
        if span_id:
            client.post("/v1/spans/%s/end" % span_id, {"status": status})
        elif run_id and not active_run_id:
            client.post("/v1/runs/%s/end" % run_id, {"status": status})
        if span_token is not None:
            _current_span_id.reset(span_token)
        if run_token is not None:
            _current_run_id.reset(run_token)


@contextmanager
def span(
    name: str,
    *,
    type: str = "agent.step",
    attributes: Optional[Dict[str, Any]] = None,
) -> Iterator[Optional[str]]:
    client = get_client()
    run_id = _current_run_id.get() or os.environ.get("ABB_ACTIVE_RUN_ID")
    parent_span_id = _current_span_id.get()
    span_id: Optional[str] = None
    token = None
    status = "ok"

    if run_id:
        created = client.post(
            "/v1/spans",
            {
                "run_id": run_id,
                "parent_span_id": parent_span_id,
                "type": type,
                "name": name,
                "attributes": attributes or {},
            },
        )
        if created:
            span_id = created.get("span_id")
            token = _current_span_id.set(span_id)

    try:
        yield span_id
    except Exception as exc:
        status = "error"
        if run_id:
            record_event(
                "error",
                message=str(exc),
                attributes={"span": name, "traceback": traceback.format_exc()},
            )
        raise
    finally:
        if span_id:
            client.post("/v1/spans/%s/end" % span_id, {"status": status})
        if token is not None:
            _current_span_id.reset(token)


def record_event(
    type: str,
    *,
    message: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    run_id = _current_run_id.get() or os.environ.get("ABB_ACTIVE_RUN_ID")
    if not run_id:
        return None
    return get_client().post(
        "/v1/events",
        {
            "run_id": run_id,
            "span_id": _current_span_id.get(),
            "type": type,
            "message": message,
            "attributes": attributes or {},
        },
    )


def annotate(message: str) -> Optional[Dict[str, Any]]:
    run_id = _current_run_id.get() or os.environ.get("ABB_ACTIVE_RUN_ID")
    if not run_id:
        return None
    return get_client().post(
        "/v1/annotations",
        {"run_id": run_id, "span_id": _current_span_id.get(), "message": message},
    )


def tool(func: F) -> F:
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        with span(
            func.__name__,
            type="tool.call",
            attributes={
                "tool": func.__name__,
                "args_count": len(args),
                "kwargs": sorted(kwargs.keys()),
            },
        ):
            try:
                result = func(*args, **kwargs)
                record_event(
                    "tool.completed",
                    message=func.__name__,
                    attributes={"duration_ms": round((time.perf_counter() - start) * 1000, 2)},
                )
                return result
            except Exception:
                record_event(
                    "tool.failed",
                    message=func.__name__,
                    attributes={"duration_ms": round((time.perf_counter() - start) * 1000, 2)},
                )
                raise

    return wrapper  # type: ignore[return-value]

