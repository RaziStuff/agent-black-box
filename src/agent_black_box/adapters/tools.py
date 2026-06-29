from __future__ import annotations

import functools
import inspect
import json
import time
import traceback
from typing import Any, Callable, Dict, Optional

from ..storage import ABBStore


class ToolCallRecorder:
    """Dependency-free recorder for plain Python and MCP-shaped tool calls."""

    def __init__(
        self,
        name: str = "Tool call run",
        *,
        data_dir: Optional[str] = None,
        store: Optional[ABBStore] = None,
        tags: Optional[list] = None,
        metadata: Optional[Dict[str, Any]] = None,
        source: str = "tool-adapter",
        auto_end_run: bool = True,
    ):
        self.name = name
        self.source = source
        self.tags = ["tools", *(tags or [])]
        self.metadata = {"adapter": "tool-call-recorder", **(metadata or {})}
        self.auto_end_run = auto_end_run
        self._store = store or ABBStore(data_dir)
        self._owns_store = store is None
        self._run_id: Optional[str] = None
        self._run_closed = False
        self._failed = False
        self._schema_refs: Dict[str, str] = {}

    @property
    def abb_run_id(self) -> Optional[str]:
        return self._run_id

    def close(self) -> None:
        if self.auto_end_run and self._run_id and not self._run_closed:
            self.end_run(status="error" if self._failed else "ok")
        if self._owns_store:
            self._store.close()

    def __enter__(self) -> "ToolCallRecorder":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if exc_type is not None:
            self._failed = True
        self.close()

    def end_run(self, status: str = "ok") -> None:
        if not self._run_id or self._run_closed:
            return
        self._store.end_run(self._run_id, status=status)
        self._run_closed = True

    def wrap_tool(
        self,
        func: Optional[Callable[..., Any]] = None,
        *,
        name: Optional[str] = None,
        schema: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Callable[..., Any]:
        """Wrap a tool function or return a decorator for one."""

        if func is None:
            return lambda inner: self.wrap_tool(
                inner,
                name=name,
                schema=schema,
                description=description,
                attributes=attributes,
            )

        tool_name = name or getattr(func, "__name__", None) or "tool"
        tool_schema = schema or _schema_from_signature(tool_name, func, description)
        tool_description = description or _doc_summary(func)
        base_attributes = {
            "function": _function_name(func),
            **(attributes or {}),
        }

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                span = self._start_tool(tool_name, args, kwargs, tool_schema, tool_description, base_attributes)
                started = time.perf_counter()
                try:
                    result = await func(*args, **kwargs)
                except Exception as exc:
                    self._fail_tool(span["span_id"], tool_name, exc, started)
                    raise
                self._complete_tool(span["span_id"], tool_name, result, started)
                return result

            return async_wrapper

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            span = self._start_tool(tool_name, args, kwargs, tool_schema, tool_description, base_attributes)
            started = time.perf_counter()
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                self._fail_tool(span["span_id"], tool_name, exc, started)
                raise
            if inspect.isawaitable(result):
                return self._complete_awaitable(span["span_id"], tool_name, result, started)
            self._complete_tool(span["span_id"], tool_name, result, started)
            return result

        return wrapper

    def record_tool_call(
        self,
        name: str,
        input: Any = None,
        output: Any = None,
        *,
        error: Any = None,
        schema: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Record a tool call that was executed elsewhere."""

        span = self._start_tool(
            name,
            (input,),
            {},
            schema,
            description,
            {"manual": True, **(attributes or {})},
        )
        started = time.perf_counter()
        if error is not None:
            self._fail_tool(span["span_id"], name, error, started)
        else:
            self._complete_tool(span["span_id"], name, output, started)
        return self._store.get_span(span["span_id"]) or span

    def record_mcp_tool_call(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        result: Any = None,
        *,
        error: Any = None,
        schema: Optional[Dict[str, Any]] = None,
        request_id: Any = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Record an MCP-style tools/call request and response."""

        return self.record_tool_call(
            name,
            input={"method": "tools/call", "id": request_id, "arguments": arguments or {}},
            output=result,
            error=error,
            schema=schema,
            attributes={"protocol": "mcp", "request_id": request_id, **(attributes or {})},
        )

    async def _complete_awaitable(self, span_id: str, tool_name: str, awaitable: Any, started: float) -> Any:
        try:
            result = await awaitable
        except Exception as exc:
            self._fail_tool(span_id, tool_name, exc, started)
            raise
        self._complete_tool(span_id, tool_name, result, started)
        return result

    def _start_tool(
        self,
        tool_name: str,
        args: tuple,
        kwargs: Dict[str, Any],
        schema: Optional[Dict[str, Any]],
        description: Optional[str],
        attributes: Dict[str, Any],
    ) -> Dict[str, Any]:
        run_id = self._ensure_run()
        schema_ref = None
        if schema:
            schema_ref = self._record_schema(run_id, tool_name, schema, description)
        input_artifact = self._artifact(
            run_id,
            None,
            "tool.input",
            {
                "tool": tool_name,
                "args": _safe_data(args),
                "kwargs": _safe_data(kwargs),
            },
        )
        span_attributes = {
            "tool": tool_name,
            "adapter": "ToolCallRecorder",
            "args_count": len(args),
            "kwargs": sorted(str(key) for key in kwargs),
            **_safe_data(attributes),
        }
        if schema_ref:
            span_attributes["schema_ref"] = schema_ref
        return self._store.start_span(
            {
                "run_id": run_id,
                "type": "tool.call",
                "name": tool_name,
                "input_ref": input_artifact["artifact_id"],
                "attributes": span_attributes,
            }
        )

    def _complete_tool(self, span_id: str, tool_name: str, output: Any, started: float) -> None:
        if not self._run_id:
            return
        output_artifact = self._artifact(
            self._run_id,
            span_id,
            "tool.output",
            {"tool": tool_name, "output": _safe_data(output)},
        )
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        self._store.add_event(
            {
                "run_id": self._run_id,
                "span_id": span_id,
                "type": "tool.completed",
                "message": tool_name,
                "attributes": {
                    "duration_ms": duration_ms,
                    "output_ref": output_artifact["artifact_id"],
                },
            }
        )
        self._store.end_span(
            span_id,
            status="ok",
            output_ref=output_artifact["artifact_id"],
            attributes={"duration_ms": duration_ms, "output_ref": output_artifact["artifact_id"]},
        )

    def _fail_tool(self, span_id: str, tool_name: str, error: Any, started: float) -> None:
        if not self._run_id:
            return
        self._failed = True
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        attributes = {
            "duration_ms": duration_ms,
            "tool": tool_name,
            "error_type": error.__class__.__name__ if isinstance(error, BaseException) else "ToolError",
        }
        if isinstance(error, BaseException):
            message = str(error)
            attributes["traceback"] = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        else:
            safe_error = _safe_data(error)
            message = safe_error.get("message") if isinstance(safe_error, dict) else str(safe_error)
            attributes["error"] = safe_error
        self._store.add_event(
            {
                "run_id": self._run_id,
                "span_id": span_id,
                "type": "tool.failed",
                "message": message,
                "attributes": attributes,
            }
        )
        self._store.end_span(span_id, status="error", attributes={"duration_ms": duration_ms})

    def _record_schema(
        self,
        run_id: str,
        tool_name: str,
        schema: Dict[str, Any],
        description: Optional[str],
    ) -> str:
        if tool_name in self._schema_refs:
            return self._schema_refs[tool_name]
        artifact = self._artifact(
            run_id,
            None,
            "tool.schema",
            {
                "tool": tool_name,
                "description": description,
                "schema": _safe_data(schema),
            },
        )
        self._store.add_event(
            {
                "run_id": run_id,
                "type": "tool.schema.recorded",
                "message": tool_name,
                "attributes": {"schema_ref": artifact["artifact_id"], "tool": tool_name},
            }
        )
        self._schema_refs[tool_name] = artifact["artifact_id"]
        return artifact["artifact_id"]

    def _artifact(self, run_id: str, span_id: Optional[str], kind: str, payload: Any) -> Dict[str, Any]:
        return self._store.add_artifact(
            run_id,
            span_id,
            kind,
            json.dumps(_safe_data(payload), indent=2, sort_keys=True),
            media_type="application/json",
        )

    def _ensure_run(self) -> str:
        if self._run_id:
            return self._run_id
        run = self._store.create_run(
            {
                "name": self.name,
                "source": self.source,
                "agent": {"framework": "tool-calls"},
                "tags": self.tags,
                "metadata": self.metadata,
            }
        )
        self._run_id = run["run_id"]
        self._run_closed = False
        return self._run_id


def _schema_from_signature(name: str, func: Callable[..., Any], description: Optional[str]) -> Dict[str, Any]:
    signature = inspect.signature(func)
    properties: Dict[str, Any] = {}
    required = []
    for param_name, param in signature.parameters.items():
        if param.kind in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}:
            properties[param_name] = {"type": "array" if param.kind == inspect.Parameter.VAR_POSITIONAL else "object"}
            continue
        properties[param_name] = _json_type(param.annotation)
        if param.default is inspect.Parameter.empty:
            required.append(param_name)
    input_schema: Dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        input_schema["required"] = required
    return {
        "name": name,
        "description": description or _doc_summary(func),
        "input_schema": input_schema,
    }


def _json_type(annotation: Any) -> Dict[str, Any]:
    if annotation is inspect.Parameter.empty:
        return {"type": "string"}
    origin = getattr(annotation, "__origin__", None)
    if annotation in {str, "str"}:
        return {"type": "string"}
    if annotation in {int, "int"}:
        return {"type": "integer"}
    if annotation in {float, "float"}:
        return {"type": "number"}
    if annotation in {bool, "bool"}:
        return {"type": "boolean"}
    if annotation in {dict, Dict} or origin is dict:
        return {"type": "object"}
    if annotation in {list, tuple} or origin in {list, tuple}:
        return {"type": "array"}
    return {"type": "string", "description": repr(annotation)}


def _doc_summary(func: Callable[..., Any]) -> Optional[str]:
    doc = inspect.getdoc(func)
    return doc.splitlines()[0] if doc else None


def _function_name(func: Callable[..., Any]) -> str:
    module = getattr(func, "__module__", "")
    qualname = getattr(func, "__qualname__", getattr(func, "__name__", "tool"))
    return f"{module}.{qualname}" if module else qualname


def _safe_data(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _safe_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_data(item) for item in value]
    if hasattr(value, "dict") and callable(value.dict):
        try:
            return _safe_data(value.dict())
        except Exception:
            pass
    if hasattr(value, "model_dump") and callable(value.model_dump):
        try:
            return _safe_data(value.model_dump())
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        public = {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_") and not callable(item)
        }
        if public:
            return _safe_data(public)
    return repr(value)
