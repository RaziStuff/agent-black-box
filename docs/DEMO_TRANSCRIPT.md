# Demo Transcript

This transcript shows the smallest useful Agent Black Box loop: check local
setup, record one run, inspect it, and delete it. It does not require an API key
or hosted service.

The commands below were run from a source checkout with an isolated `ABB_HOME`.
Run IDs and timestamps will differ on your machine.

## 1. Doctor

```bash
python3 abb.py doctor
```

Expected shape:

```text
Agent Black Box doctor
Status: warning (0 errors, 1 warnings)
Version: 0.1.0
Python: 3.9.6
Platform: macOS-14.1-arm64-arm-64bit
Data dir: /private/tmp/abb-readme-demo-20260703

Checks:
- [ok] python: Python 3.9.6
- [ok] storage: Local store is writable
- [ok] cli: CLI entrypoint is available
- [warning] daemon: Daemon is not running at http://127.0.0.1:43188
- [ok] openai_proxy: OpenAI-compatible proxy can record when traffic is routed through the daemon
```

The daemon warning is normal until `abb start` is running. The first proof only
needs local storage and the CLI.

## 2. Record

```bash
python3 abb.py record --name sixty-second-demo -- python3 examples/basic_agent.py
```

Expected shape:

```text
Recorded run: run_524ec4800c4540b0b7f476b9
Hi Ada Lovelace, thanks for flagging this. I found the duplicate charge and routed it for manual_review.
```

## 3. List Runs

```bash
python3 abb.py runs
```

Expected shape:

```text
run_524ec4800c4540b0b7f476b9  ok        2026-07-02T22:58:02.808Z  2026-07-02T22:58:02.943Z  sixty-second-demo
```

Copy the newest `run_...` value.

## 4. Inspect The Run

```bash
python3 abb.py show run_524ec4800c4540b0b7f476b9
```

Expected shape:

```text
sixty-second-demo (run_524ec4800c4540b0b7f476b9)
Status: ok  Source: cli-record
Summary: 0 model calls, 0 tool calls, 0 graph nodes, 1 warnings, 0 errors, 1 artifacts
Debug Path:
1. [warning] Warning: Temporary SDK collector could not start; recording shell command only. @ 2026-07-02T22:58:02.811Z refs: span_id=span_0380e19ba49f4eaa813cf7d1
   Why: The run emitted a warning before or during execution.
   Next: Inspect the linked span and adjacent timeline events.

- 2026-07-02T22:58:02.811Z [shell.command] python3 examples/basic_agent.py
- 2026-07-02T22:58:02.811Z [warning.detected] Temporary SDK collector could not start; recording shell command only.
- 2026-07-02T22:58:02.943Z [shell.completed] Command exited with 0
```

The warning means the temporary SDK collector was unavailable, so Agent Black Box
recorded the shell command path instead. The run is still captured, inspectable,
and deletable.

## 5. Delete The Local Run

```bash
python3 abb.py delete run_524ec4800c4540b0b7f476b9 --yes --json
```

Expected shape:

```json
{
  "counts": {
    "artifact_objects": 1,
    "artifacts": 1,
    "events": 2,
    "runs": 1,
    "spans": 1
  },
  "deleted": true,
  "run_id": "run_524ec4800c4540b0b7f476b9"
}
```

The full JSON also includes artifact hashes and removed local object paths.

## What This Proves

- Agent Black Box can run locally without an API key.
- A command can be recorded as a run.
- `abb show` gives a compact summary and Debug Path.
- Local trace data can be removed with `abb delete RUN_ID --yes`.

For the full alpha workflow, continue with
[FIRST_USER_WORKFLOW.md](FIRST_USER_WORKFLOW.md).
