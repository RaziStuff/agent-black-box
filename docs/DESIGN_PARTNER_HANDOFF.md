# Design Partner Handoff

Use this when giving Agent Black Box to a first local alpha user or a small
design-partner loop.

## What To Send

Send the generated design-partner kit first:

- `dist/agent-black-box-0.1.0-design-partner.zip`

It contains the wheel, source tarball, checksum manifest, first-user docs, no-network examples, and `install.sh`.

Use [DESIGN_PARTNER_FIRST_SEND_PACKET.md](DESIGN_PARTNER_FIRST_SEND_PACKET.md)
for the first three-partner send plan, exact copy, follow-up schedule, and
decision rubric.
Use [DESIGN_PARTNER_INTAKE.md](DESIGN_PARTNER_INTAKE.md) and
[DESIGN_PARTNER_INTAKE.csv](DESIGN_PARTNER_INTAKE.csv) to rank candidate names
before the first send.
Use [DESIGN_PARTNER_OUTREACH.md](DESIGN_PARTNER_OUTREACH.md) for a ready-to-send email or DM.
Use [DESIGN_PARTNER_TRACKER.md](DESIGN_PARTNER_TRACKER.md) and
[DESIGN_PARTNER_TRACKER.csv](DESIGN_PARTNER_TRACKER.csv) to track sends,
blockers, returned artifacts, and decisions.

If you are sharing files from the source checkout instead, send these files:

- [FIRST_USER_WORKFLOW.md](FIRST_USER_WORKFLOW.md)
- [DESIGN_PARTNER_INTAKE.md](DESIGN_PARTNER_INTAKE.md)
- [DESIGN_PARTNER_FIRST_SEND_PACKET.md](DESIGN_PARTNER_FIRST_SEND_PACKET.md)
- [DESIGN_PARTNER_FEEDBACK_FORM.md](DESIGN_PARTNER_FEEDBACK_FORM.md)
- [DESIGN_PARTNER_TRACKER.md](DESIGN_PARTNER_TRACKER.md)
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)

Optional for agent-heavy users:

- [AGENT_INTEGRATION_PROMPT.md](AGENT_INTEGRATION_PROMPT.md)
- [API_REFERENCE.md](API_REFERENCE.md)

## Setup Command

Ask them to unzip the design-partner kit and start with:

```bash
sh install.sh
. .venv/bin/activate
abb doctor
abb endpoints --json
abb endpoints --openapi
abb init
```

For source-checkout collaborators, use:

```bash
scripts/dev-install.sh
. .venv/bin/activate
abb doctor
abb endpoints --json
abb endpoints --openapi
abb init
```

Expected:

- `abb doctor` reports local storage as ok.
- The daemon may be a warning until they run `abb start`.
- `abb endpoints --json` and `abb endpoints --openapi` print local API discovery output.
- `abb init` writes a local guide under `.abb/init/`.
- The kit's `release-manifest.json` lists SHA-256 checksums for the wheel and source tarball.

## Fast Demo

For a one-command demo:

```bash
scripts/alpha-demo.sh
```

This records local demo runs, creates a compare investigation, creates a handoff
investigation, exports/imports a bundle, and prints a reviewer summary.

## Full User Path

Ask them to complete [FIRST_USER_WORKFLOW.md](FIRST_USER_WORKFLOW.md), especially:

- Record the demo agent.
- Inspect `abb show RUN_ID`.
- Export and ingest a compare pair.
- Export and ingest a handoff packet.
- Start `abb start` and inspect the browser dashboard.
- Try `python3 examples/http_agent_client.py` while the daemon is running.
- Export and import a portable `.abb` bundle.

## Feedback Questions

Ask the reviewer to fill [DESIGN_PARTNER_FEEDBACK_FORM.md](DESIGN_PARTNER_FEEDBACK_FORM.md).
If you are collecting feedback live, ask:

- Could you install and run `abb doctor` without help?
- Did the first useful command feel obvious?
- Did `abb show RUN_ID` tell you what happened?
- Did the debug path tell you what to inspect first?
- Could you find the relevant artifact without scanning the raw artifact list?
- Did compare export and compare ingest feel useful for handing one decision to another agent?
- Did the handoff briefing give enough context for another agent to continue?
- Did linked source and investigation runs make sense?
- Did the local API discovery output help if you were not using the Python SDK?
- Did the privacy boundary feel clear?
- What command, page, or concept caused the first moment of confusion?

## Feedback Triage

When completed feedback forms come back, save them under a local folder such as
`.abb-feedback/` and summarize them:

```bash
python3 scripts/feedback-summary.py .abb-feedback --output .abb-feedback/summary.json --markdown .abb-feedback/summary.md
```

Use the Markdown report for human review and the JSON summary for issue triage.
Pause the next send if the report flags setup failures, redaction concerns, or
low privacy/local-first clarity scores.

Update [DESIGN_PARTNER_TRACKER.csv](DESIGN_PARTNER_TRACKER.csv) with the returned
feedback path, support packet path, blocker, follow-up date, and decision.
Use the partner-level and cohort rubrics in
[DESIGN_PARTNER_FIRST_SEND_PACKET.md](DESIGN_PARTNER_FIRST_SEND_PACKET.md) before
sending to the next reviewer.

## What To Ask For When Something Breaks

Ask for the smallest useful artifact:

```bash
abb doctor --json
abb support RUN_ID
abb handoff RUN_ID
abb export RUN_ID --format handoff
```

`abb support RUN_ID` includes local copies of the troubleshooting and
known-limitations notes, so it is the best single folder to send when the
reviewer is not sitting inside this repo.

Ask for a full `.abb` bundle only when the user can share artifact payloads:

```bash
abb bundle export RUN_ID
abb support RUN_ID --include-bundle
```

Ask them to include:

- The exact command they ran.
- The exact error output.
- Whether the issue happened in CLI, browser, SDK, HTTP API, proxy, or import/export.
- Whether `ABB_HOME`, `ABB_DAEMON_URL`, or `ABB_AUTH_TOKEN` was set.
- Whether they followed a section in [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Privacy Reminder

Tell users:

- Data stays in the configured local store by default.
- `.handoff.json` files are compact summaries and do not embed full artifact payloads.
- `.abb` bundles include artifact payloads and should be treated as full trace archives.
- `abb support RUN_ID` does not include the full bundle unless `--include-bundle` is used.
- They should inspect artifacts before sharing anything outside their machine.

## Stop Conditions

Pause the alpha loop if any of these happen:

- A known secret appears unredacted in demo or user artifacts.
- `scripts/smoke.sh` fails in a normal local shell.
- Bundle import cannot recover a trace in a fresh local store.
- Handoff ingest cannot create a linked investigation run.
- The browser cannot open a recorded run in an environment where browser smoke is expected to pass.
- The first user cannot complete the workflow without repeated manual explanation.
