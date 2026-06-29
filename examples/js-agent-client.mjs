const DEFAULT_URL = "http://127.0.0.1:43188";

function optionValue(name, fallback) {
  const index = process.argv.indexOf(name);
  if (index >= 0 && process.argv[index + 1]) return process.argv[index + 1];
  return fallback;
}

if (process.argv.includes("--help") || process.argv.includes("-h")) {
  console.log(`Usage: node examples/js-agent-client.mjs [--url URL] [--token TOKEN]

Record one Agent Black Box run through the localhost HTTP API.

Options:
  --url URL       Agent Black Box daemon URL. Defaults to ABB_DAEMON_URL or ${DEFAULT_URL}
  --token TOKEN   Bearer token. Defaults to ABB_AUTH_TOKEN.
`);
  process.exit(0);
}

class AgentBlackBoxHttpClient {
  constructor(baseUrl, token) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.token = token;
  }

  async get(path) {
    return this.request("GET", path);
  }

  async post(path, payload) {
    return this.request("POST", path, payload);
  }

  async request(method, path, payload) {
    const headers = { Accept: "application/json" };
    const options = { method, headers };
    if (payload !== undefined) {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(payload);
    }
    if (this.token) headers.Authorization = `Bearer ${this.token}`;
    let response;
    try {
      response = await fetch(`${this.baseUrl}${path}`, options);
    } catch (error) {
      throw new Error(`Cannot reach Agent Black Box at ${this.baseUrl}. Start it with abb start. ${error.message}`);
    }
    const text = await response.text();
    if (!response.ok) {
      throw new Error(`${method} ${path} failed with HTTP ${response.status}: ${text}`);
    }
    const contentType = response.headers.get("content-type") || "";
    return contentType.includes("application/json") ? JSON.parse(text) : text;
  }
}

async function recordExampleRun(client) {
  const openapi = await client.get("/v1/openapi.json");
  if (!openapi.paths || !openapi.paths["/v1/runs"]) {
    throw new Error("Agent Black Box OpenAPI document did not include /v1/runs");
  }

  const run = await client.post("/v1/runs", {
    name: "http-js-agent-demo",
    source: "http-js-example",
    tags: ["example", "http-client"],
    metadata: { client: "examples/js-agent-client.mjs" },
  });
  const runId = run.run_id;
  const span = await client.post("/v1/spans", {
    run_id: runId,
    type: "agent.step",
    name: "call Agent Black Box over HTTP",
    attributes: { transport: "http", language: "javascript" },
  });
  const spanId = span.span_id;
  const artifact = await client.post("/v1/artifacts", {
    run_id: runId,
    span_id: spanId,
    kind: "agent.note",
    media_type: "application/json",
    content: JSON.stringify(
      {
        client: "javascript",
        observation: "Recorded through the local HTTP API.",
        next_step: "Open the run in the browser or export a handoff packet.",
      },
      null,
      2,
    ),
  });
  await client.post("/v1/events", {
    run_id: runId,
    span_id: spanId,
    type: "agent.observation",
    message: "JavaScript HTTP example recorded a local artifact.",
    attributes: { artifact_id: artifact.artifact_id },
  });
  await client.post(`/v1/spans/${spanId}/end`, {
    status: "ok",
    output_ref: artifact.artifact_id,
    attributes: { artifact_kind: artifact.kind },
  });
  await client.post(`/v1/runs/${runId}/end`, { status: "ok" });
  const timeline = await client.get(`/v1/runs/${runId}/timeline`);
  return {
    run_id: runId,
    span_id: spanId,
    artifact_id: artifact.artifact_id,
    timeline_counts: {
      spans: timeline.spans?.length || 0,
      events: timeline.events?.length || 0,
      artifacts: timeline.artifacts?.length || 0,
    },
    dashboard_url: `${client.baseUrl}/`,
    timeline_url: `${client.baseUrl}/v1/runs/${runId}/timeline`,
  };
}

if (typeof fetch !== "function") {
  console.error("This example needs Node.js 18 or newer, where fetch is built in.");
  process.exit(1);
}

const url = optionValue("--url", process.env.ABB_DAEMON_URL || DEFAULT_URL);
const token = optionValue("--token", process.env.ABB_AUTH_TOKEN || "");

recordExampleRun(new AgentBlackBoxHttpClient(url, token))
  .then((result) => {
    console.log(JSON.stringify(result, null, 2));
  })
  .catch((error) => {
    console.error(error.message);
    process.exit(1);
  });
