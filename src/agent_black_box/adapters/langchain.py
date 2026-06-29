from __future__ import annotations

import json
import traceback
from typing import Any, Dict, Optional

from ..storage import ABBStore
from ..usage import extract_usage


class AgentBlackBoxCallbackHandler:
    """Dependency-free LangChain-style callback handler.

    The class intentionally does not inherit from LangChain base classes. It exposes
    the common callback method names so it can be passed into LangChain callback
    lists when LangChain is installed, while remaining testable without LangChain.
    """

    def __init__(
        self,
        name: str = "LangChain run",
        *,
        data_dir: Optional[str] = None,
        store: Optional[ABBStore] = None,
        tags: Optional[list] = None,
        metadata: Optional[Dict[str, Any]] = None,
        auto_end_run: bool = True,
    ):
        self.name = name
        self.tags = ["langchain", *(tags or [])]
        self.metadata = {"framework": "langchain", **(metadata or {})}
        self.auto_end_run = auto_end_run
        self._store = store or ABBStore(data_dir)
        self._owns_store = store is None
        self._run_id: Optional[str] = None
        self._root_callback_id: Optional[str] = None
        self._spans: Dict[str, str] = {}

    @property
    def abb_run_id(self) -> Optional[str]:
        return self._run_id

    def close(self) -> None:
        if self._owns_store:
            self._store.close()

    def __enter__(self) -> "AgentBlackBoxCallbackHandler":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

    def on_chain_start(
        self,
        serialized: Any,
        inputs: Any,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        callback_id = _callback_id(run_id, "chain")
        abb_run_id = self._ensure_run(_name_from_serialized(serialized) or self.name)
        if parent_run_id is None and self._root_callback_id is None:
            self._root_callback_id = callback_id
        artifact = self._artifact(
            abb_run_id,
            None,
            "chain.input",
            {"serialized": _safe_data(serialized), "inputs": _safe_data(inputs)},
        )
        span = self._store.start_span(
            {
                "run_id": abb_run_id,
                "parent_span_id": self._parent_span_id(parent_run_id),
                "type": "chain.run",
                "name": _name_from_serialized(serialized) or "LangChain chain",
                "input_ref": artifact["artifact_id"],
                "attributes": self._attributes("chain", callback_id, parent_run_id, kwargs),
            }
        )
        self._spans[callback_id] = span["span_id"]

    def on_chain_end(self, outputs: Any, *, run_id: Any = None, **kwargs: Any) -> None:
        callback_id = _callback_id(run_id, "chain")
        self._complete_span(callback_id, "chain.output", outputs, "chain.completed", kwargs)
        if self.auto_end_run and callback_id == self._root_callback_id and self._run_id:
            self._store.end_run(self._run_id, status="ok")

    def on_chain_error(self, error: BaseException, *, run_id: Any = None, **kwargs: Any) -> None:
        callback_id = _callback_id(run_id, "chain")
        self._fail_span(callback_id, error, "chain.failed", kwargs)
        if self.auto_end_run and callback_id == self._root_callback_id and self._run_id:
            self._store.end_run(self._run_id, status="error")

    def on_llm_start(
        self,
        serialized: Any,
        prompts: Any,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        self._start_model_span("llm", serialized, prompts, run_id, parent_run_id, kwargs)

    def on_chat_model_start(
        self,
        serialized: Any,
        messages: Any,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        self._start_model_span("chat_model", serialized, messages, run_id, parent_run_id, kwargs)

    def on_llm_end(self, response: Any, *, run_id: Any = None, **kwargs: Any) -> None:
        callback_id = _callback_id(run_id, "llm")
        payload = _safe_data(response)
        usage = extract_usage(payload)
        self._complete_span(callback_id, "model.response", payload, "model.completed", kwargs, usage=usage)

    def on_llm_error(self, error: BaseException, *, run_id: Any = None, **kwargs: Any) -> None:
        self._fail_span(_callback_id(run_id, "llm"), error, "model.failed", kwargs)

    def on_tool_start(
        self,
        serialized: Any,
        input_str: Any,
        *,
        run_id: Any = None,
        parent_run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        callback_id = _callback_id(run_id, "tool")
        abb_run_id = self._ensure_run()
        artifact = self._artifact(
            abb_run_id,
            None,
            "tool.input",
            {"serialized": _safe_data(serialized), "input": _safe_data(input_str)},
        )
        span = self._store.start_span(
            {
                "run_id": abb_run_id,
                "parent_span_id": self._parent_span_id(parent_run_id),
                "type": "tool.call",
                "name": _name_from_serialized(serialized) or "LangChain tool",
                "input_ref": artifact["artifact_id"],
                "attributes": self._attributes("tool", callback_id, parent_run_id, kwargs),
            }
        )
        self._spans[callback_id] = span["span_id"]

    def on_tool_end(self, output: Any, *, run_id: Any = None, **kwargs: Any) -> None:
        self._complete_span(_callback_id(run_id, "tool"), "tool.output", output, "tool.completed", kwargs)

    def on_tool_error(self, error: BaseException, *, run_id: Any = None, **kwargs: Any) -> None:
        self._fail_span(_callback_id(run_id, "tool"), error, "tool.failed", kwargs)

    def on_agent_action(self, action: Any, *, run_id: Any = None, **kwargs: Any) -> None:
        self._event(_callback_id(run_id, "agent"), "agent.action", action, kwargs)

    def on_agent_finish(self, finish: Any, *, run_id: Any = None, **kwargs: Any) -> None:
        self._event(_callback_id(run_id, "agent"), "agent.finish", finish, kwargs)

    def _start_model_span(
        self,
        callback_type: str,
        serialized: Any,
        inputs: Any,
        run_id: Any,
        parent_run_id: Any,
        kwargs: Dict[str, Any],
    ) -> None:
        callback_id = _callback_id(run_id, "llm")
        abb_run_id = self._ensure_run()
        artifact = self._artifact(
            abb_run_id,
            None,
            "model.request",
            {"serialized": _safe_data(serialized), "inputs": _safe_data(inputs)},
        )
        span = self._store.start_span(
            {
                "run_id": abb_run_id,
                "parent_span_id": self._parent_span_id(parent_run_id),
                "type": "model.call",
                "name": _name_from_serialized(serialized) or "LangChain model",
                "input_ref": artifact["artifact_id"],
                "attributes": {
                    **self._attributes(callback_type, callback_id, parent_run_id, kwargs),
                    "provider": "langchain",
                    "model": _model_from_serialized(serialized),
                },
            }
        )
        self._spans[callback_id] = span["span_id"]

    def _complete_span(
        self,
        callback_id: str,
        artifact_kind: str,
        output: Any,
        event_type: str,
        kwargs: Dict[str, Any],
        usage: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self._run_id:
            return
        span_id = self._spans.get(callback_id)
        artifact = self._artifact(self._run_id, span_id, artifact_kind, output)
        attributes = {"output_ref": artifact["artifact_id"], "kwargs": _safe_data(kwargs)}
        end_attributes: Dict[str, Any] = {"output_ref": artifact["artifact_id"]}
        if usage:
            attributes["usage"] = usage
            end_attributes["usage"] = usage
        self._store.add_event(
            {
                "run_id": self._run_id,
                "span_id": span_id,
                "type": event_type,
                "message": event_type,
                "attributes": attributes,
            }
        )
        if span_id:
            self._store.end_span(span_id, status="ok", output_ref=artifact["artifact_id"], attributes=end_attributes)

    def _fail_span(
        self,
        callback_id: str,
        error: BaseException,
        event_type: str,
        kwargs: Dict[str, Any],
    ) -> None:
        if not self._run_id:
            self._ensure_run()
        span_id = self._spans.get(callback_id)
        self._store.add_event(
            {
                "run_id": self._run_id,
                "span_id": span_id,
                "type": event_type,
                "message": str(error),
                "attributes": {
                    "error_type": error.__class__.__name__,
                    "traceback": "".join(traceback.format_exception(type(error), error, error.__traceback__)),
                    "kwargs": _safe_data(kwargs),
                },
            }
        )
        if span_id:
            self._store.end_span(span_id, status="error")

    def _event(self, callback_id: str, event_type: str, payload: Any, kwargs: Dict[str, Any]) -> None:
        abb_run_id = self._ensure_run()
        self._store.add_event(
            {
                "run_id": abb_run_id,
                "span_id": self._spans.get(callback_id),
                "type": event_type,
                "message": event_type,
                "attributes": {"payload": _safe_data(payload), "kwargs": _safe_data(kwargs)},
            }
        )

    def _artifact(self, run_id: str, span_id: Optional[str], kind: str, payload: Any) -> Dict[str, Any]:
        return self._store.add_artifact(
            run_id,
            span_id,
            kind,
            json.dumps(_safe_data(payload), indent=2, sort_keys=True),
            media_type="application/json",
        )

    def _ensure_run(self, name: Optional[str] = None) -> str:
        if self._run_id:
            return self._run_id
        run = self._store.create_run(
            {
                "name": name or self.name,
                "source": "langchain-adapter",
                "agent": {"framework": "langchain"},
                "tags": self.tags,
                "metadata": self.metadata,
            }
        )
        self._run_id = run["run_id"]
        return self._run_id

    def _parent_span_id(self, parent_run_id: Any) -> Optional[str]:
        return self._spans.get(str(parent_run_id)) if parent_run_id is not None else None

    def _attributes(
        self,
        callback_type: str,
        callback_id: str,
        parent_run_id: Any,
        kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "framework": "langchain",
            "callback_type": callback_type,
            "callback_run_id": callback_id,
            "parent_callback_run_id": str(parent_run_id) if parent_run_id is not None else None,
            "kwargs": _safe_data(kwargs),
        }


def _callback_id(value: Any, fallback_prefix: str) -> str:
    return str(value) if value is not None else f"{fallback_prefix}:default"


def _name_from_serialized(serialized: Any) -> Optional[str]:
    data = _safe_data(serialized)
    if isinstance(data, dict):
        if data.get("name"):
            return str(data["name"])
        if data.get("id"):
            value = data["id"]
            if isinstance(value, list) and value:
                return str(value[-1])
            return str(value)
        kwargs = data.get("kwargs")
        if isinstance(kwargs, dict):
            for key in ("model_name", "model", "name"):
                if kwargs.get(key):
                    return str(kwargs[key])
    return None


def _model_from_serialized(serialized: Any) -> Optional[str]:
    data = _safe_data(serialized)
    if isinstance(data, dict):
        kwargs = data.get("kwargs")
        if isinstance(kwargs, dict):
            for key in ("model_name", "model"):
                if kwargs.get(key):
                    return str(kwargs[key])
        if data.get("name"):
            return str(data["name"])
    return None


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
