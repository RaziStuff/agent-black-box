from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Tuple


API_MANIFEST_VERSION = "0.1"

API_ENDPOINTS: List[Dict[str, Any]] = [
    {
        "id": "dashboard",
        "category": "Discovery",
        "method": "GET",
        "path": "/",
        "summary": "Open the local browser dashboard.",
        "returns": "HTML dashboard",
        "cli": "abb start",
    },
    {
        "id": "health",
        "category": "Discovery",
        "method": "GET",
        "path": "/health",
        "summary": "Check daemon reachability and local data directory.",
        "returns": "health object",
        "cli": "abb status",
    },
    {
        "id": "endpoints",
        "category": "Discovery",
        "method": "GET",
        "path": "/v1/endpoints",
        "summary": "Read this machine-readable local API manifest.",
        "returns": "api manifest",
        "cli": "abb endpoints --json",
    },
    {
        "id": "openapi",
        "category": "Discovery",
        "method": "GET",
        "path": "/v1/openapi.json",
        "summary": "Read the OpenAPI 3.1 description for local HTTP clients and agent tools.",
        "returns": "OpenAPI 3.1 document",
        "cli": "abb endpoints --openapi",
    },
    {
        "id": "agent-kit.create",
        "category": "Discovery",
        "method": "POST",
        "path": "/v1/agent-kit",
        "summary": "Create a portable local integration kit with API contracts and HTTP clients.",
        "body": "optional output, force, url, zip, and zip_output",
        "returns": "agent-kit manifest",
        "cli": "abb agent-kit --json",
    },
    {
        "id": "runs.list",
        "category": "Runs",
        "method": "GET",
        "path": "/v1/runs",
        "summary": "List recent recorded runs.",
        "query": ["limit"],
        "returns": "list of run records",
        "cli": "abb runs --json",
    },
    {
        "id": "runs.create",
        "category": "Runs",
        "method": "POST",
        "path": "/v1/runs",
        "summary": "Create a run from an SDK, adapter, or non-Python client.",
        "body": "run fields such as name, source, tags, and metadata",
        "returns": "created run record",
        "cli": "abb record --name NAME -- COMMAND",
    },
    {
        "id": "runs.get",
        "category": "Runs",
        "method": "GET",
        "path": "/v1/runs/{run_id}",
        "summary": "Read one run record.",
        "returns": "run record",
        "cli": "abb show RUN_ID --json",
    },
    {
        "id": "runs.timeline",
        "category": "Runs",
        "method": "GET",
        "path": "/v1/runs/{run_id}/timeline",
        "summary": "Read a full run timeline with spans, events, artifacts, annotations, fixtures, and links.",
        "returns": "timeline object",
        "cli": "abb show RUN_ID --json",
    },
    {
        "id": "runs.links",
        "category": "Runs",
        "method": "GET",
        "path": "/v1/runs/{run_id}/links",
        "summary": "List source and investigation links for handoff and compare-created runs.",
        "returns": "linked run records",
        "cli": "abb show RUN_ID",
    },
    {
        "id": "runs.end",
        "category": "Runs",
        "method": "POST",
        "path": "/v1/runs/{run_id}/end",
        "summary": "Mark a run complete.",
        "body": "{\"status\":\"ok\"}",
        "returns": "updated run record",
        "cli": "SDK recorder end_run",
    },
    {
        "id": "runs.export",
        "category": "Runs",
        "method": "POST",
        "path": "/v1/runs/{run_id}/export",
        "summary": "Export a run as JSONL, Markdown, handoff JSON, or a portable .abb bundle.",
        "body": "{\"format\":\"jsonl|markdown|handoff|abb\"}",
        "returns": "export path and format",
        "cli": "abb export RUN_ID --format FORMAT",
    },
    {
        "id": "spans.create",
        "category": "Capture",
        "method": "POST",
        "path": "/v1/spans",
        "summary": "Start a span for a model call, tool call, graph node, or agent step.",
        "body": "run_id, name, type, attributes, optional parent_span_id",
        "returns": "created span record",
        "cli": "Python SDK span(...)",
    },
    {
        "id": "spans.end",
        "category": "Capture",
        "method": "POST",
        "path": "/v1/spans/{span_id}/end",
        "summary": "End a span and optionally attach output refs or final attributes.",
        "body": "status, attributes, optional output_ref",
        "returns": "updated span record",
        "cli": "Python SDK span context exit",
    },
    {
        "id": "events.create",
        "category": "Capture",
        "method": "POST",
        "path": "/v1/events",
        "summary": "Append an event to a run or span.",
        "body": "run_id, type, message, optional span_id and attributes",
        "returns": "created event record",
        "cli": "Python SDK event helpers",
    },
    {
        "id": "artifacts.create",
        "category": "Capture",
        "method": "POST",
        "path": "/v1/artifacts",
        "summary": "Store a local artifact body and return an artifact reference.",
        "body": "run_id, optional span_id, kind, media_type, content",
        "returns": "created artifact record",
        "cli": "Python SDK artifact helpers",
    },
    {
        "id": "batch.create",
        "category": "Capture",
        "method": "POST",
        "path": "/v1/batch",
        "summary": "Create runs, spans, events, and annotations in one local request.",
        "body": "runs, spans, events, annotations arrays",
        "returns": "created records grouped by type",
        "cli": "SDK and adapter internals",
    },
    {
        "id": "runs.artifacts",
        "category": "Artifacts",
        "method": "GET",
        "path": "/v1/runs/{run_id}/artifacts",
        "summary": "List artifact metadata for a run.",
        "returns": "list of artifact records",
        "cli": "abb artifacts RUN_ID --json",
    },
    {
        "id": "artifacts.read",
        "category": "Artifacts",
        "method": "GET",
        "path": "/v1/artifacts/{artifact_id}",
        "summary": "Read one artifact payload.",
        "returns": "raw artifact bytes",
        "cli": "abb artifact ARTIFACT_ID",
    },
    {
        "id": "annotations.list",
        "category": "Annotations",
        "method": "GET",
        "path": "/v1/runs/{run_id}/annotations",
        "summary": "List annotations for a run.",
        "returns": "list of annotations",
        "cli": "abb annotations RUN_ID --json",
    },
    {
        "id": "annotations.create",
        "category": "Annotations",
        "method": "POST",
        "path": "/v1/annotations",
        "summary": "Add an annotation to a run or span.",
        "body": "run_id, message, optional span_id",
        "returns": "created annotation",
        "cli": "abb annotate RUN_ID MESSAGE",
    },
    {
        "id": "search",
        "category": "Search And Diff",
        "method": "GET",
        "path": "/v1/search",
        "summary": "Search run names, sources, tags, annotations, and timeline text.",
        "query": ["q"],
        "returns": "matching run records",
        "cli": "abb search QUERY --json",
    },
    {
        "id": "diff",
        "category": "Search And Diff",
        "method": "GET",
        "path": "/v1/diff",
        "summary": "Compare two runs and find normalized divergence.",
        "query": ["run_a", "run_b"],
        "returns": "diff object",
        "cli": "abb diff RUN_A RUN_B --json",
    },
    {
        "id": "fixtures.list",
        "category": "Fixtures",
        "method": "GET",
        "path": "/v1/fixtures",
        "summary": "List replay fixtures.",
        "query": ["limit"],
        "returns": "list of fixture records",
        "cli": "abb fixture list --json",
    },
    {
        "id": "fixtures.create",
        "category": "Fixtures",
        "method": "POST",
        "path": "/v1/runs/{run_id}/fixture",
        "summary": "Create a replay fixture from a run.",
        "body": "optional name",
        "returns": "created fixture",
        "cli": "abb fixture create RUN_ID --name NAME",
    },
    {
        "id": "fixtures.get",
        "category": "Fixtures",
        "method": "GET",
        "path": "/v1/fixtures/{fixture_id}",
        "summary": "Read one replay fixture.",
        "returns": "fixture object",
        "cli": "abb fixture show FIXTURE_ID --json",
    },
    {
        "id": "compare.export",
        "category": "Compare",
        "method": "GET",
        "path": "/v1/runs/{run_id}/compare-export",
        "summary": "Export one comparable request/response or input/output pair for another agent.",
        "query": ["span or span_id", "pair=auto|request-response|input-output", "format=json|markdown|md"],
        "returns": "compare pair JSON or Markdown",
        "cli": "abb compare-export RUN_ID --format json",
    },
    {
        "id": "compare.ingest",
        "category": "Compare",
        "method": "POST",
        "path": "/v1/compare/ingest",
        "summary": "Create a focused investigation run from a compare-pair JSON file.",
        "body": "path, optional name",
        "returns": "created compare investigation",
        "cli": "abb compare-ingest PATH --json",
    },
    {
        "id": "compare.evidence",
        "category": "Compare",
        "method": "GET",
        "path": "/v1/runs/{run_id}/compare-evidence",
        "summary": "Read compare investigation packet, briefing, left body, or right body without copying artifact IDs.",
        "query": ["part=packet|briefing|left|right", "format=json|text|txt", "raw=1"],
        "returns": "evidence summary, JSON evidence object, or text body",
        "cli": "abb compare-evidence RUN_ID --left",
    },
    {
        "id": "handoffs.ingest",
        "category": "Handoffs",
        "method": "POST",
        "path": "/v1/handoffs/ingest",
        "summary": "Create a follow-up investigation run from a handoff JSON file.",
        "body": "path, optional name",
        "returns": "created handoff investigation",
        "cli": "abb handoff --ingest PATH --json",
    },
    {
        "id": "bundles.import",
        "category": "Bundles",
        "method": "POST",
        "path": "/v1/bundles/import",
        "summary": "Import a portable .abb bundle into the local store.",
        "body": "path, on_conflict=fail|skip|remap",
        "returns": "import result",
        "cli": "abb bundle import PATH --on-conflict remap",
    },
    {
        "id": "proxy.openai",
        "category": "Proxy",
        "method": "POST",
        "path": "/proxy/openai/{path}",
        "summary": "Record OpenAI-compatible requests while forwarding them to the configured upstream.",
        "body": "OpenAI-compatible request body",
        "returns": "upstream response with local trace side effects",
        "cli": "abb start; export OPENAI_BASE_URL=http://127.0.0.1:43188/proxy/openai",
    },
]


def api_manifest(base_url: str = "http://127.0.0.1:43188") -> Dict[str, Any]:
    normalized_base_url = base_url.rstrip("/") if base_url else "http://127.0.0.1:43188"
    return {
        "manifest_version": API_MANIFEST_VERSION,
        "service": "agent-black-box",
        "base_url": normalized_base_url,
        "authentication": {
            "mode": "optional_bearer",
            "header": "Authorization: Bearer <ABB_AUTH_TOKEN>",
            "note": "Required only when the daemon is started with --token or ABB_AUTH_TOKEN.",
        },
        "endpoints": deepcopy(API_ENDPOINTS),
    }


def openapi_spec(base_url: str = "http://127.0.0.1:43188") -> Dict[str, Any]:
    manifest = api_manifest(base_url)
    paths: Dict[str, Any] = {}
    for endpoint in manifest["endpoints"]:
        operation = _openapi_operation(endpoint)
        paths.setdefault(endpoint["path"], {})[endpoint["method"].lower()] = operation

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Agent Black Box Local API",
            "version": manifest["manifest_version"],
            "description": "Local-first HTTP API for recording, inspecting, comparing, handing off, and importing agent traces.",
        },
        "servers": [
            {
                "url": manifest["base_url"],
                "description": "Local Agent Black Box daemon",
            }
        ],
        "security": [{"BearerAuth": []}, {}],
        "paths": paths,
        "components": {
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "Optional. Required only when abb start uses --token or ABB_AUTH_TOKEN.",
                }
            },
            "schemas": {
                "JsonObject": {
                    "type": "object",
                    "additionalProperties": True,
                },
                "JsonArray": {
                    "type": "array",
                    "items": {},
                },
                "Error": {
                    "type": "object",
                    "properties": {
                        "error": {"type": "string"},
                        "message": {"type": "string"},
                    },
                    "additionalProperties": True,
                },
            },
        },
    }


def format_api_manifest(manifest: Dict[str, Any]) -> str:
    lines = [
        "Agent Black Box API",
        f"Manifest: {manifest['manifest_version']}",
        f"Base URL: {manifest['base_url']}",
        "Auth: optional bearer token via Authorization header",
        "",
    ]
    current_category = None
    for endpoint in manifest["endpoints"]:
        category = endpoint["category"]
        if category != current_category:
            if current_category is not None:
                lines.append("")
            lines.append(category)
            current_category = category
        lines.append(f"- {endpoint['method']} {endpoint['path']}")
        lines.append(f"  {endpoint['summary']}")
        if endpoint.get("query"):
            lines.append(f"  Query: {', '.join(endpoint['query'])}")
        if endpoint.get("body"):
            lines.append(f"  Body: {endpoint['body']}")
        if endpoint.get("returns"):
            lines.append(f"  Returns: {endpoint['returns']}")
        if endpoint.get("cli"):
            lines.append(f"  CLI: {endpoint['cli']}")
    return "\n".join(lines) + "\n"


def _openapi_operation(endpoint: Dict[str, Any]) -> Dict[str, Any]:
    operation: Dict[str, Any] = {
        "operationId": _operation_id(endpoint["id"]),
        "tags": [endpoint["category"]],
        "summary": endpoint["summary"],
        "description": _operation_description(endpoint),
        "parameters": _openapi_parameters(endpoint),
        "responses": _openapi_responses(endpoint),
    }
    if endpoint.get("body"):
        operation["requestBody"] = {
            "required": endpoint["method"] in {"POST", "PUT", "PATCH"},
            "description": endpoint["body"],
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/JsonObject"}
                }
            },
        }
    return operation


def _operation_id(endpoint_id: str) -> str:
    parts = endpoint_id.replace("-", ".").split(".")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _operation_description(endpoint: Dict[str, Any]) -> str:
    lines = [endpoint["summary"]]
    if endpoint.get("returns"):
        lines.append(f"Returns: {endpoint['returns']}.")
    if endpoint.get("cli"):
        lines.append(f"CLI equivalent: `{endpoint['cli']}`.")
    return "\n\n".join(lines)


def _openapi_parameters(endpoint: Dict[str, Any]) -> List[Dict[str, Any]]:
    parameters: List[Dict[str, Any]] = []
    for name in _path_parameter_names(endpoint["path"]):
        parameters.append(
            {
                "name": name,
                "in": "path",
                "required": True,
                "schema": {"type": "string"},
                "description": f"{name.replace('_', ' ').title()} value.",
            }
        )
    for query in endpoint.get("query", []):
        if " or " in query or "=" in query:
            name, description = _query_name_and_description(query)
        else:
            name, description = query, f"{query.replace('_', ' ').title()} query value."
        parameters.append(
            {
                "name": name,
                "in": "query",
                "required": False,
                "schema": {"type": "string"},
                "description": description,
            }
        )
    return parameters


def _path_parameter_names(path: str) -> List[str]:
    names = []
    rest = path
    while "{" in rest and "}" in rest:
        before, _, after_start = rest.partition("{")
        name, _, rest = after_start.partition("}")
        if before is not None and name:
            names.append(name)
    return names


def _query_name_and_description(query: str) -> Tuple[str, str]:
    name = query.split("=", 1)[0].split(" or ", 1)[0].strip()
    return name, query


def _openapi_responses(endpoint: Dict[str, Any]) -> Dict[str, Any]:
    success_status = _success_status_code(endpoint)
    media_type = "application/json"
    schema: Dict[str, Any] = {"$ref": "#/components/schemas/JsonObject"}
    if endpoint["path"] == "/":
        media_type = "text/html"
        schema = {"type": "string"}
    elif endpoint["path"].startswith("/v1/artifacts/"):
        media_type = "application/octet-stream"
        schema = {"type": "string", "contentEncoding": "binary"}
    elif endpoint["id"] in {"runs.list", "annotations.list", "fixtures.list", "search"}:
        schema = {"$ref": "#/components/schemas/JsonArray"}
    responses = {
        success_status: {
            "description": endpoint.get("returns") or "Success",
            "content": {
                media_type: {
                    "schema": schema,
                }
            },
        },
        "400": {
            "description": "Bad request",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/Error"}
                }
            },
        },
        "404": {
            "description": "Not found",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/Error"}
                }
            },
        },
    }
    if endpoint["id"] == "bundles.import":
        responses["200"] = deepcopy(responses[success_status])
        responses["200"]["description"] = "skipped import result when on_conflict=skip"
    return responses


def _success_status_code(endpoint: Dict[str, Any]) -> str:
    created_ids = {
        "agent-kit.create",
        "annotations.create",
        "artifacts.create",
        "bundles.import",
        "compare.ingest",
        "events.create",
        "fixtures.create",
        "handoffs.ingest",
        "runs.create",
        "runs.export",
        "spans.create",
    }
    return "201" if endpoint["id"] in created_ids else "200"
