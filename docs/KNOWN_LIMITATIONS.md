# Known Limitations

Agent Black Box is in local alpha. It is useful for first-user debugging loops,
but it is not a packaged production observability product yet.

For common setup and workflow fixes, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Product Scope

- No signed desktop app.
- No hosted service, cloud sync, account system, or shared workspace.
- No package registry release.
- No multi-user access model beyond optional local bearer auth for the daemon.
- No hosted telemetry.

## Local Store

- Data lives in the configured local store, `.abb/` by default.
- There is no automatic retention policy or cleanup command yet.
- Large traces do not have pagination yet.
- `.abb` bundles include artifact payloads and should be handled as full trace archives.
- `.handoff.json` packets are compact summaries and do not embed full artifact payloads.

## Browser UI

- The browser dashboard is intentionally minimal and local-only.
- Browser upload is not implemented; bundle, handoff, and compare ingest use local filesystem paths.
- The rendered browser smoke requires Playwright and a browser engine. Without those optional dependencies it skips clearly unless strict mode is requested.

## HTTP And OpenAPI

- The OpenAPI document is intentionally broad-schema in this alpha. Most request and response bodies are represented as JSON objects while the route contract stabilizes.
- The Python and Node HTTP examples require a running daemon.
- The Node HTTP example requires Node.js 18 or newer because it uses built-in `fetch`.
- Localhost socket probes may be blocked by some sandboxed environments. Use the no-socket unit tests and run `scripts/http-client-smoke.py --required` in a normal local shell before release.

## Agent Follow-Up

- Handoff ingest creates a linked investigation run, but the follow-up agent still needs to add its own reasoning, spans, annotations, and artifacts.
- Compare ingest creates a focused investigation from one pair, not a full diagnosis.
- Replay fixtures are terminal-style summaries, not full deterministic execution replays.

## OpenAI Compatibility

- The import-swap wrapper targets `chat.completions.create(...)` and `responses.create(...)`.
- The OpenAI-compatible proxy buffers streaming responses in this alpha.
- Proxy traffic is only recorded when the user explicitly routes traffic through the local daemon.

## Redaction

- Obvious API keys, bearer tokens, passwords, and private keys are redacted.
- Redaction is defensive but not a substitute for human review. Inspect artifacts before sharing support packets or `.abb` bundles.
