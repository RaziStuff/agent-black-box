from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional
from urllib import request
from urllib.error import HTTPError, URLError


DEFAULT_URL = "http://127.0.0.1:43188"


class AgentBlackBoxHttpClient:
    def __init__(self, base_url: str, token: Optional[str] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def get(self, path: str) -> Any:
        return self._request("GET", path)

    def post(self, path: str, payload: Dict[str, Any]) -> Any:
        return self._request("POST", path, payload)

    def _request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        http_request = request.Request(
            self.base_url + path,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with request.urlopen(http_request, timeout=10) as response:
                raw = response.read()
                content_type = response.headers.get("Content-Type", "")
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed with HTTP {exc.code}: {body}") from exc
        except URLError as exc:
            raise RuntimeError(
                f"Cannot reach Agent Black Box at {self.base_url}. Start it with `abb start`."
            ) from exc
        if "application/json" in content_type:
            return json.loads(raw.decode("utf-8"))
        return raw.decode("utf-8", errors="replace")


def record_example_run(client: AgentBlackBoxHttpClient) -> Dict[str, Any]:
    openapi = client.get("/v1/openapi.json")
    if "/v1/runs" not in openapi.get("paths", {}):
        raise RuntimeError("Agent Black Box OpenAPI document did not include /v1/runs")

    run = client.post(
        "/v1/runs",
        {
            "name": "http-python-agent-demo",
            "source": "http-python-example",
            "tags": ["example", "http-client"],
            "metadata": {"client": "examples/http_agent_client.py"},
        },
    )
    run_id = run["run_id"]
    span = client.post(
        "/v1/spans",
        {
            "run_id": run_id,
            "type": "agent.step",
            "name": "call Agent Black Box over HTTP",
            "attributes": {"transport": "http", "language": "python"},
        },
    )
    span_id = span["span_id"]
    artifact = client.post(
        "/v1/artifacts",
        {
            "run_id": run_id,
            "span_id": span_id,
            "kind": "agent.note",
            "media_type": "application/json",
            "content": json.dumps(
                {
                    "client": "python",
                    "observation": "Recorded through the local HTTP API.",
                    "next_step": "Open the run in the browser or export a handoff packet.",
                },
                indent=2,
                sort_keys=True,
            ),
        },
    )
    client.post(
        "/v1/events",
        {
            "run_id": run_id,
            "span_id": span_id,
            "type": "agent.observation",
            "message": "Python HTTP example recorded a local artifact.",
            "attributes": {"artifact_id": artifact["artifact_id"]},
        },
    )
    client.post(
        f"/v1/spans/{span_id}/end",
        {
            "status": "ok",
            "output_ref": artifact["artifact_id"],
            "attributes": {"artifact_kind": artifact["kind"]},
        },
    )
    client.post(f"/v1/runs/{run_id}/end", {"status": "ok"})
    timeline = client.get(f"/v1/runs/{run_id}/timeline")
    return {
        "run_id": run_id,
        "span_id": span_id,
        "artifact_id": artifact["artifact_id"],
        "timeline_counts": {
            "spans": len(timeline.get("spans", [])),
            "events": len(timeline.get("events", [])),
            "artifacts": len(timeline.get("artifacts", [])),
        },
        "dashboard_url": f"{client.base_url}/",
        "timeline_url": f"{client.base_url}/v1/runs/{run_id}/timeline",
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record one Agent Black Box run through the localhost HTTP API."
    )
    parser.add_argument("--url", default=os.environ.get("ABB_DAEMON_URL", DEFAULT_URL))
    parser.add_argument("--token", default=os.environ.get("ABB_AUTH_TOKEN"))
    args = parser.parse_args(argv)

    client = AgentBlackBoxHttpClient(args.url, token=args.token)
    try:
        result = record_example_run(client)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
