# Troubleshooting

Use this when a local alpha workflow does not behave as expected.

If a missing behavior looks intentional rather than broken, check
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

## Start With Doctor

```bash
abb doctor
abb doctor --json
```

The human output gives the quickest read. The JSON output is useful for support
packets, scripts, and other agents.

## Daemon Is Not Running

Symptoms:

- `abb doctor` reports `Daemon is not running`.
- `abb status` cannot reach the daemon.
- HTTP clients fail with `Cannot reach Agent Black Box`.

Fix:

```bash
abb start
```

Then open:

```text
http://127.0.0.1:43188
```

If a different port is needed:

```bash
abb start --port 43189
export ABB_DAEMON_URL=http://127.0.0.1:43189
```

## Localhost Probe Is Blocked

Some sandboxed environments block binding or probing local ports.

Use no-socket checks first:

```bash
PYTHONPYCACHEPREFIX=.pycache python3 -m unittest discover -s tests
python3 examples/http_agent_client.py --help
```

Run the live HTTP client smoke in a normal local shell:

```bash
python3 scripts/http-client-smoke.py --required
```

## Node Client Skips

`examples/js-agent-client.mjs` requires Node.js 18 or newer because it uses
built-in `fetch`.

Check:

```bash
node --version
```

If Node is unavailable, use the Python HTTP client:

```bash
python3 examples/http_agent_client.py
```

For release environments where Node is expected:

```bash
python3 scripts/http-client-smoke.py --required --node-required
```

## Browser Smoke Skips

The rendered browser smoke requires Playwright and a browser engine.

Non-strict smoke:

```bash
python3 scripts/browser-smoke.py
```

Strict release check:

```bash
ABB_BROWSER_SMOKE_REQUIRED=1 python3 scripts/browser-smoke.py
```

If it skips, the CLI and storage tests can still pass. Run the strict browser
smoke only in an environment with Playwright installed.

## Auth Token Fails

If the daemon was started with a token:

```bash
abb start --token TOKEN
```

HTTP clients must send:

```text
Authorization: Bearer TOKEN
```

For the examples:

```bash
python3 examples/http_agent_client.py --token TOKEN
node examples/js-agent-client.mjs --token TOKEN
```

Or set:

```bash
export ABB_AUTH_TOKEN=TOKEN
```

## No Runs Show Up

Check the data directory:

```bash
abb doctor
echo "$ABB_HOME"
```

By default, Agent Black Box stores data in `.abb/` under the current working
directory. If you used `--data-dir` or `ABB_HOME`, make sure every command uses
the same store.

## Compare Export Fails

Compare export needs a span with a natural pair, such as request/response or
input/output artifacts.

Try an OpenAI wrapper demo first:

```bash
python3 examples/openai_wrapper_agent.py
OPENAI_RUN_ID="$(abb runs --json | python3 -c 'import json,sys; runs=json.load(sys.stdin); print(next(run["run_id"] for run in runs if run["source"] == "openai-wrapper"))')"
abb compare-export "$OPENAI_RUN_ID" --format json
```

## Handoff Or Compare Ingest Fails

Ingest commands read local filesystem paths. Confirm the path exists and points
to the expected JSON file:

```bash
ls .abb/exports
abb handoff --ingest .abb/exports/RUN_ID.handoff.json
abb compare-ingest .abb/exports/RUN_ID.SPAN_ID.request-response.compare.json
```

## Bundle Import Fails

By default, importing the same run twice fails to avoid accidentally overwriting
local data.

Use one of:

```bash
abb bundle import RUN_ID.abb --on-conflict skip
abb bundle import RUN_ID.abb --on-conflict remap
```

Use `skip` for idempotent repeated imports. Use `remap` to import a second copy
as a new independent run.

## Support Packet To Share

For the smallest useful support context:

```bash
abb support RUN_ID
```

The support packet includes `README.txt`, `briefing.txt`, structured handoff and
timeline files, `doctor.json`, `TROUBLESHOOTING.txt`, and
`KNOWN_LIMITATIONS.txt`.

Only include full artifact payloads when the reviewer can receive the whole
trace archive:

```bash
abb support RUN_ID --include-bundle
```

Before sharing, inspect sensitive artifacts:

```bash
abb artifacts RUN_ID
abb artifact ARTIFACT_ID
```
