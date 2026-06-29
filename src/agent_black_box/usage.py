from __future__ import annotations

from typing import Any, Dict, Optional


def extract_usage(payload: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        usage = payload.get("token_usage")
    if not isinstance(usage, dict) and isinstance(payload.get("usage_metadata"), dict):
        usage = payload.get("usage_metadata")
    if not isinstance(usage, dict) and isinstance(payload.get("llm_output"), dict):
        llm_output = payload["llm_output"]
        usage = llm_output.get("token_usage") or llm_output.get("usage")
    if not isinstance(usage, dict):
        return None

    input_tokens = _first_int(usage, "input_tokens", "prompt_tokens")
    output_tokens = _first_int(usage, "output_tokens", "completion_tokens", "output_token_count")
    total_tokens = _first_int(usage, "total_tokens")
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens

    normalized: Dict[str, Any] = {}
    if input_tokens is not None:
        normalized["input_tokens"] = input_tokens
    if output_tokens is not None:
        normalized["output_tokens"] = output_tokens
    if total_tokens is not None:
        normalized["total_tokens"] = total_tokens
    if usage.get("input_tokens_details"):
        normalized["input_tokens_details"] = usage["input_tokens_details"]
    if usage.get("output_tokens_details"):
        normalized["output_tokens_details"] = usage["output_tokens_details"]
    if usage.get("prompt_tokens_details"):
        normalized["input_tokens_details"] = usage["prompt_tokens_details"]
    if usage.get("completion_tokens_details"):
        normalized["output_tokens_details"] = usage["completion_tokens_details"]
    return normalized or None


def usage_from_attributes(attributes: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    usage = attributes.get("usage")
    return usage if isinstance(usage, dict) else None


def format_usage(usage: Optional[Dict[str, Any]]) -> str:
    if not usage:
        return ""
    parts = []
    if usage.get("input_tokens") is not None:
        parts.append(f"in={usage['input_tokens']}")
    if usage.get("output_tokens") is not None:
        parts.append(f"out={usage['output_tokens']}")
    if usage.get("total_tokens") is not None:
        parts.append(f"total={usage['total_tokens']}")
    return "tokens " + ", ".join(parts) if parts else ""


def _first_int(values: Dict[str, Any], *keys: str) -> Optional[int]:
    for key in keys:
        value = values.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
    return None
