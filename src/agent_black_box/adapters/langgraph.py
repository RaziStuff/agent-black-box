from __future__ import annotations

import functools
import inspect
import json
import traceback
from typing import Any, Callable, Dict, Optional

from ..storage import ABBStore


class LangGraphRecorder:
    """Dependency-free wrapper for LangGraph-style node functions.

    The recorder does not import LangGraph. It wraps ordinary node callables and
    records each node invocation as a local Agent Black Box span, so the same
    wrapper can be used in tests, plain Python demos, or real LangGraph builders.
    """

    def __init__(
        self,
        name: str = "LangGraph run",
        *,
        data_dir: Optional[str] = None,
        store: Optional[ABBStore] = None,
        tags: Optional[list] = None,
        metadata: Optional[Dict[str, Any]] = None,
        auto_end_run: bool = True,
    ):
        self.name = name
        self.tags = ["langgraph", *(tags or [])]
        self.metadata = {"framework": "langgraph", **(metadata or {})}
        self.auto_end_run = auto_end_run
        self._store = store or ABBStore(data_dir)
        self._owns_store = store is None
        self._run_id: Optional[str] = None
        self._run_closed = False
        self._failed = False

    @property
    def abb_run_id(self) -> Optional[str]:
        return self._run_id

    def close(self) -> None:
        if self.auto_end_run and self._run_id and not self._run_closed:
            self.end_run(status="error" if self._failed else "ok")
        if self._owns_store:
            self._store.close()

    def __enter__(self) -> "LangGraphRecorder":
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

    def wrap_node(
        self,
        func: Optional[Callable[..., Any]] = None,
        *,
        name: Optional[str] = None,
        node_type: str = "langgraph.node",
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Callable[..., Any]:
        """Wrap a node function or return a decorator for one."""

        if func is None:
            return lambda inner: self.wrap_node(
                inner,
                name=name,
                node_type=node_type,
                attributes=attributes,
            )

        node_name = name or getattr(func, "__name__", None) or "LangGraph node"
        node_attributes = {
            "function": _function_name(func),
            **(attributes or {}),
        }

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                span = self._start_node(node_name, node_type, args, kwargs, node_attributes)
                try:
                    result = await func(*args, **kwargs)
                except Exception as exc:
                    self._fail_node(span["span_id"], node_name, exc)
                    raise
                self._complete_node(span["span_id"], node_name, result)
                return result

            return async_wrapper

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            span = self._start_node(node_name, node_type, args, kwargs, node_attributes)
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                self._fail_node(span["span_id"], node_name, exc)
                raise
            if inspect.isawaitable(result):
                return self._complete_awaitable(span["span_id"], node_name, result)
            self._complete_node(span["span_id"], node_name, result)
            return result

        return wrapper

    def record_node(
        self,
        name: str,
        input_state: Any,
        output_state: Any = None,
        *,
        error: Optional[BaseException] = None,
        node_type: str = "langgraph.node",
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Record a node invocation when wrapping the function is not convenient."""

        span = self._start_node(name, node_type, (input_state,), {}, attributes or {})
        if error is not None:
            self._fail_node(span["span_id"], name, error)
        else:
            self._complete_node(span["span_id"], name, output_state)
        return self._store.get_span(span["span_id"]) or span

    async def _complete_awaitable(self, span_id: str, node_name: str, awaitable: Any) -> Any:
        try:
            result = await awaitable
        except Exception as exc:
            self._fail_node(span_id, node_name, exc)
            raise
        self._complete_node(span_id, node_name, result)
        return result

    def _start_node(
        self,
        node_name: str,
        node_type: str,
        args: tuple,
        kwargs: Dict[str, Any],
        attributes: Dict[str, Any],
    ) -> Dict[str, Any]:
        run_id = self._ensure_run()
        input_artifact = self._artifact(
            run_id,
            None,
            "langgraph.node.input",
            {
                "node": node_name,
                "state": _safe_data(args[0]) if args else None,
                "args": _safe_data(args[1:]),
                "kwargs": _safe_data(kwargs),
            },
        )
        return self._store.start_span(
            {
                "run_id": run_id,
                "type": node_type,
                "name": node_name,
                "input_ref": input_artifact["artifact_id"],
                "attributes": {
                    "framework": "langgraph",
                    "adapter": "LangGraphRecorder",
                    "node_name": node_name,
                    **_safe_data(attributes),
                },
            }
        )

    def _complete_node(self, span_id: str, node_name: str, output: Any) -> None:
        if not self._run_id:
            return
        output_artifact = self._artifact(
            self._run_id,
            span_id,
            "langgraph.node.output",
            {"node": node_name, "output": _safe_data(output)},
        )
        self._store.add_event(
            {
                "run_id": self._run_id,
                "span_id": span_id,
                "type": "langgraph.node.completed",
                "message": node_name,
                "attributes": {"output_ref": output_artifact["artifact_id"]},
            }
        )
        self._store.end_span(
            span_id,
            status="ok",
            output_ref=output_artifact["artifact_id"],
            attributes={"output_ref": output_artifact["artifact_id"]},
        )

    def _fail_node(self, span_id: str, node_name: str, error: BaseException) -> None:
        if not self._run_id:
            return
        self._failed = True
        self._store.add_event(
            {
                "run_id": self._run_id,
                "span_id": span_id,
                "type": "langgraph.node.failed",
                "message": str(error),
                "attributes": {
                    "node": node_name,
                    "error_type": error.__class__.__name__,
                    "traceback": "".join(traceback.format_exception(type(error), error, error.__traceback__)),
                },
            }
        )
        self._store.end_span(span_id, status="error")

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
                "source": "langgraph-adapter",
                "agent": {"framework": "langgraph"},
                "tags": self.tags,
                "metadata": self.metadata,
            }
        )
        self._run_id = run["run_id"]
        self._run_closed = False
        return self._run_id


def _function_name(func: Callable[..., Any]) -> str:
    module = getattr(func, "__module__", "")
    qualname = getattr(func, "__qualname__", getattr(func, "__name__", "node"))
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
