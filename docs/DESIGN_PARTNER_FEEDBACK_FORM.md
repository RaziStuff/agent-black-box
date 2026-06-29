# Design Partner Feedback Form

Thank you for trying Agent Black Box. Fill this out after completing
[FIRST_USER_WORKFLOW.md](FIRST_USER_WORKFLOW.md), or after the first point where
you get stuck.

## Reviewer

- Name:
- Date:
- OS:
- Python version:
- Did you use the design-partner zip or source checkout?:
- Did you set `ABB_HOME`, `ABB_DAEMON_URL`, or `ABB_AUTH_TOKEN`?:

## Setup

- Did `sh install.sh` work?:
- Did `. .venv/bin/activate` work?:
- Did `abb doctor` work?:
- Doctor status: ok / warning / error
- First confusing setup step:

Paste any setup error:

```text

```

## Workflow Completion

Mark each item:

- [ ] Ran `abb endpoints --json`
- [ ] Ran `abb endpoints --openapi`
- [ ] Ran `abb agent-kit --zip`
- [ ] Ran `abb init`
- [ ] Ran `python3 examples/openai_wrapper_agent.py`
- [ ] Ran `python3 examples/langchain_callback_agent.py`
- [ ] Ran `python3 examples/langgraph_node_agent.py`
- [ ] Ran `python3 examples/tool_call_agent.py`
- [ ] Ran `abb record --name first-debug-run -- python3 examples/basic_agent.py`
- [ ] Inspected a run with `abb show RUN_ID`
- [ ] Added an annotation
- [ ] Created a fixture and replayed it
- [ ] Exported and ingested a compare pair
- [ ] Exported and ingested a handoff packet
- [ ] Exported and imported a `.abb` bundle
- [ ] Created `abb support RUN_ID`
- [ ] Opened the browser dashboard with `abb start`
- [ ] Tried the HTTP client example while the daemon was running

## Scores

Use 1 to 5, where 1 is poor and 5 is excellent.

- Install clarity:
- First-run clarity:
- `abb show` usefulness:
- Debug Path usefulness:
- Artifact inspection usefulness:
- Compare export/ingest usefulness:
- Handoff packet usefulness:
- Browser dashboard usefulness:
- Privacy/local-first clarity:
- Overall likelihood you would use this again:

## Most Useful Moment

What was the first moment where Agent Black Box made the run easier to
understand?

```text

```

## First Confusing Moment

What command, page, output, or concept caused the first confusion?

```text

```

## Debugging Value

Answer briefly:

- Did `abb show RUN_ID` tell you what happened?:
- Did the Debug Path point to the right thing first?:
- Could you find the relevant artifact without scanning every artifact?:
- Did grouped request/response, input/output, or schema/input artifacts help?:
- Did compare ingest make a focused follow-up investigation obvious?:
- Did handoff ingest make source and investigation runs easy to follow?:

## Privacy And Sharing

- Did the local storage boundary feel clear?:
- Did you understand the difference between `.handoff.json`, `abb support RUN_ID`, and `.abb` bundles?:
- Was there anything you would hesitate to share back?:
- Did you see any secret or sensitive value that should have been redacted?:

## Support Artifacts

If something broke, attach the smallest useful artifact you can share:

- `abb doctor --json`
- `abb support RUN_ID`
- `abb handoff RUN_ID`
- `.abb/exports/RUN_ID.handoff.json`

Only attach `.abb/exports/RUN_ID.abb` if you can share full artifact payloads.

Support packet path:

```text

```

## Open Notes

Anything else we should know before the next alpha build?

```text

```
