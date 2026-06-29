from dataclasses import dataclass
import re
from typing import Any, Dict, List, Tuple


SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "auth",
    "bearer",
    "cookie",
    "password",
    "private_key",
    "secret",
    "ssh_key",
    "token",
}


@dataclass
class RedactionHit:
    rule: str
    count: int


SECRET_PATTERNS = [
    (
        "bearer_token",
        re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE),
        "Bearer [redacted]",
    ),
    (
        "openai_key",
        re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
        "sk-[redacted]",
    ),
    (
        "private_key",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        "-----BEGIN PRIVATE KEY-----[redacted]-----END PRIVATE KEY-----",
    ),
    (
        "key_value_secret",
        re.compile(
            r"\b(api[_-]?key|token|secret|password)"
            r"(\s*[:=]\s*[\"']?)([^\"'\s,;]+)",
            re.IGNORECASE,
        ),
        None,
    ),
]


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in SENSITIVE_KEYS or normalized.endswith("_token") or normalized.endswith("_secret")


def redact_text(value: str) -> Tuple[str, List[RedactionHit]]:
    text = value
    hits: List[RedactionHit] = []

    for rule, pattern, replacement in SECRET_PATTERNS:
        if replacement is None:
            text, count = pattern.subn(lambda match: f"{match.group(1)}{match.group(2)}[redacted]", text)
        else:
            text, count = pattern.subn(replacement, text)
        if count:
            hits.append(RedactionHit(rule=rule, count=count))

    return text, hits


def redact_payload(payload: Any) -> Tuple[Any, List[Dict[str, Any]]]:
    hits: List[Dict[str, Any]] = []

    def walk(value: Any, path: str) -> Any:
        if isinstance(value, dict):
            output = {}
            for key, child in value.items():
                key_text = str(key)
                child_path = f"{path}.{key_text}" if path else key_text
                if _is_sensitive_key(key_text):
                    hits.append({"rule": "sensitive_key", "path": child_path, "count": 1})
                    output[key] = "[redacted]"
                else:
                    output[key] = walk(child, child_path)
            return output

        if isinstance(value, list):
            return [walk(child, f"{path}[{index}]") for index, child in enumerate(value)]

        if isinstance(value, str):
            redacted, text_hits = redact_text(value)
            for hit in text_hits:
                hits.append({"rule": hit.rule, "path": path, "count": hit.count})
            return redacted

        return value

    return walk(payload, ""), hits
