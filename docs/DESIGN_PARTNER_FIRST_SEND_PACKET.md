# Design Partner First Send Packet

Use this packet to run the first three Agent Black Box design-partner sends.
The goal is to learn whether the local-first debugging wedge is real for people
building agents now, not to collect general praise or product ideas.

## Outcome

By the end of this loop, there should be:

- One ranked intake report from [DESIGN_PARTNER_INTAKE.csv](DESIGN_PARTNER_INTAKE.csv).
- Three rows in [DESIGN_PARTNER_TRACKER.csv](DESIGN_PARTNER_TRACKER.csv).
- One sent `agent-black-box-0.1.0-design-partner.zip` checksum per row.
- At least two completed workflows or concrete blockers.
- At least two returned feedback forms, live notes, handoff packets, or support packets.
- One recorded decision per partner: `iterate`, `pause`, `ready_next_partner`, or `ship_next_alpha`.
- One cohort decision for the next release step.

## The Wedge To Test

Agent Black Box should help an agent builder answer these questions faster than
raw logs, screenshots, or chat history:

- What happened in this agent run?
- What should I inspect first?
- Which request, response, tool input, tool output, or graph node explains the failure?
- Can I package enough context for another agent or human without sharing the whole local store?
- Does the local-first boundary feel clear and trustworthy?

Do not optimize this loop for public launch readiness. Optimize it for proof
that a small, real user can install the kit, record or inspect a run, and decide
whether Agent Black Box belongs in their agent debugging workflow.

## Partner Selection

Send to exactly three design partners first. Pick one from each segment if
possible.

Before choosing names, fill [DESIGN_PARTNER_INTAKE.csv](DESIGN_PARTNER_INTAKE.csv)
and rank candidates:

```bash
python3 scripts/rank-design-partners.py docs/DESIGN_PARTNER_INTAKE.csv --markdown .abb-send/design-partner-ranking.md --json-output .abb-send/design-partner-ranking.json
```

Copy the selected contacts into [DESIGN_PARTNER_TRACKER.csv](DESIGN_PARTNER_TRACKER.csv)
before generating outbound drafts.

| partner_id | segment | best fit | main question |
| --- | --- | --- | --- |
| `dp-001` | agent founder | Building an agent product, debugging tool calls, retries, prompts, or model outputs weekly. | Does this save debugging time on a real agent run? |
| `dp-002` | agent infra engineer | Owns evals, observability, local tooling, agent platforms, or support workflows. | Are handoff, compare, support, and local API surfaces agent-ready? |
| `dp-003` | local automation builder | Uses CLI/Python agents, notebooks, or scripts for real workflows. | Is the first workflow understandable without knowing the codebase? |

Strong fit signals:

- They have run an agent workflow in the last 14 days.
- They have felt pain from missing traces, unclear tool failures, or hard-to-share debug context.
- They are comfortable running terminal commands and local Python tools.
- They care about local/private debugging rather than a hosted dashboard first.
- They can spend 20 to 40 minutes on the workflow.
- They can return a redacted feedback form, `.handoff.json`, or support packet if something breaks.

Do not send in this first loop if:

- They do not currently build, operate, or heavily use agents.
- They need a hosted SaaS, team admin, billing, or production SLA before trying anything.
- They are not comfortable with a terminal.
- Their environment forbids installing local tools or sharing even redacted feedback.
- They mainly want a polished UI review rather than a debugging workflow test.

## Before Sending

Run this from the source checkout:

```bash
python3 scripts/build-release.py
python3 scripts/release-readiness.py
```

Open `dist/release-manifest.json` and copy the `design_partner_kit` SHA-256.
Use that exact checksum in the message and tracker row.

Or generate checksum-filled outbound drafts and tracker rows:

```bash
python3 scripts/prepare-design-partner-send.py --owner YOUR_NAME --json
```

The generated files are written under `.abb-send/`, which is local operator
output. Replace contact placeholders before sending.

Create or update the three tracker rows before sending:

```csv
dp-001,AGENT_FOUNDER_NAME,agent founder,agent-black-box-0.1.0-design-partner.zip,SHA256,,candidate,send founder email,,,,,,,,,YOUR_NAME,,replace contact then send founder draft
dp-002,AGENT_INFRA_NAME,agent infra engineer,agent-black-box-0.1.0-design-partner.zip,SHA256,,candidate,send infra email,,,,,,,,,YOUR_NAME,,replace contact then send infra draft
dp-003,LOCAL_AUTOMATION_NAME,local automation builder,agent-black-box-0.1.0-design-partner.zip,SHA256,,candidate,send automation dm,,,,,,,,,YOUR_NAME,,replace contact then send automation draft
```

After the message is sent, change each row to `status=sent`, set `sent_at`, and
set `next_follow_up_at` to the next business day.

## What To Attach

Attach only:

- `dist/agent-black-box-0.1.0-design-partner.zip`

Include this checksum block in the message:

```text
Artifact: agent-black-box-0.1.0-design-partner.zip
SHA-256: SHA256
```

Do not ask for a source checkout unless the partner is collaborating on the
implementation. Do not ask for a full `.abb` bundle first. Ask for
`docs/DESIGN_PARTNER_FEEDBACK_FORM.md`, `abb support RUN_ID`, or a `.handoff.json`
packet before any full trace archive.

## Email For Agent Founders

Subject: Local alpha: debug one real agent run with Agent Black Box

Hi NAME,

I am testing a local-first tool called Agent Black Box with three design
partners. It records AI agent runs on your machine so you can inspect what
happened, find the first useful debug point, compare request/response or
input/output artifacts, and export a compact handoff packet for another agent or
human.

I am not looking for a polished product review yet. I am trying to learn whether
this makes debugging one real agent workflow faster than logs and screenshots.

I attached:

- `agent-black-box-0.1.0-design-partner.zip`

Checksum:

```text
SHA-256: SHA256
```

To try it:

```bash
unzip agent-black-box-0.1.0-design-partner.zip
cd agent-black-box-0.1.0-design-partner
sh install.sh
. .venv/bin/activate
abb doctor
```

Then follow `docs/FIRST_USER_WORKFLOW.md`. If you only have 20 minutes, run the
demo workflow and tell me the first command or page that either helped or
confused you.

The most useful return artifacts are:

- `docs/DESIGN_PARTNER_FEEDBACK_FORM.md`
- `abb support RUN_ID`
- `abb handoff RUN_ID`

Privacy notes:

- Agent Black Box stores data locally by default in `.abb/`.
- `.handoff.json` files are compact summaries and do not include full artifact payloads.
- `.abb` bundles include artifact payloads and should be inspected before sharing.

Thank you,
YOUR_NAME

## Email For Infra Or Platform Engineers

Subject: Can you sanity-check a local-first agent trace handoff?

Hi NAME,

I am running a tiny design-partner loop for Agent Black Box, a local-first flight
recorder for agent runs. The wedge I want to test with you is whether the trace,
compare, support, handoff, and local API surfaces are useful enough for agents
and platform engineers to debug without sending data to a hosted service.

I attached the local alpha kit:

- `agent-black-box-0.1.0-design-partner.zip`

Checksum:

```text
SHA-256: SHA256
```

Install path:

```bash
unzip agent-black-box-0.1.0-design-partner.zip
cd agent-black-box-0.1.0-design-partner
sh install.sh
. .venv/bin/activate
abb doctor
abb endpoints --json
abb endpoints --openapi
```

Then follow `docs/FIRST_USER_WORKFLOW.md`, especially compare export, handoff
export, handoff ingest, support packet creation, and `abb agent-kit --zip`.

I am looking for blunt feedback on:

- Whether the local API and agent kit are easy for another agent to consume.
- Whether `.handoff.json` contains enough context without becoming a full trace archive.
- Whether support packets are the right default artifact when something breaks.
- Whether the privacy boundary is clear.

Useful return artifacts:

- `docs/DESIGN_PARTNER_FEEDBACK_FORM.md`
- `abb support RUN_ID`
- `abb export RUN_ID --format handoff`

Thank you,
YOUR_NAME

## Short DM

I have the first local alpha of Agent Black Box ready for three design partners.
It is a local-first flight recorder for AI agent runs: record locally, inspect
what happened, find the first debug point, and export a compact handoff/support
packet.

Can I send you `agent-black-box-0.1.0-design-partner.zip`? The useful path is 20
to 40 minutes:

```bash
sh install.sh
. .venv/bin/activate
abb doctor
```

Then follow `docs/FIRST_USER_WORKFLOW.md` and return
`docs/DESIGN_PARTNER_FEEDBACK_FORM.md` or `abb support RUN_ID` if you hit a
blocker. Data stays local unless you choose to export/share a packet.

## Ten Minute Ask

Use this for a busy partner who cannot do the full workflow yet.

```text
If you only have 10 minutes, please do this:

1. unzip agent-black-box-0.1.0-design-partner.zip
2. sh install.sh
3. . .venv/bin/activate
4. abb doctor
5. python3 examples/openai_wrapper_agent.py
6. abb runs
7. abb show RUN_ID

Then tell me:
- Did install/doctor work without help?
- Did abb show make the run easier to understand?
- What was the first confusing command, page, or concept?
```

## Follow-Up Schedule

| time | tracker update | action |
| --- | --- | --- |
| T+0 | `status=sent`, `next_follow_up_at=T+1` | Send the kit, checksum, and relevant message. |
| T+1 business day | If no reply, keep `status=sent`. | Ask whether unzip/install/doctor worked. |
| T+3 business days | If no install, set `current_step=install`. | Offer the ten minute ask. |
| T+3 after blocker | Set `status=blocked`, record `blocker`. | Ask for the smallest support artifact. |
| T+5 after workflow start | Set `current_step=feedback`. | Ask for the feedback form or live notes. |
| T+7 after feedback | Set `status=feedback_returned` or `done`. | Thank them and confirm the decision you recorded. |
| T+10 after no reply | Set `status=paused`. | Close the loop unless they re-engage. |

### No Reply Follow-Up

Subject: Quick nudge on Agent Black Box local alpha

Hi NAME,

Quick nudge on the Agent Black Box local alpha. If the full workflow is too much
right now, the highest-signal 10 minute path is:

```bash
sh install.sh
. .venv/bin/activate
abb doctor
python3 examples/openai_wrapper_agent.py
abb runs
abb show RUN_ID
```

The three things I most want to know are:

- Did install and `abb doctor` work without help?
- Did `abb show RUN_ID` make the run easier to understand?
- What was the first confusing command or concept?

Thanks,
YOUR_NAME

### Installed But Did Not Finish

Hi NAME,

Thank you for getting Agent Black Box installed. If you have another 10 to 15
minutes, the highest-signal next step is:

```bash
python3 examples/openai_wrapper_agent.py
abb runs
abb show RUN_ID
abb handoff RUN_ID
```

I am trying to learn whether the run summary, debug path, and handoff briefing
point you to the right thing without scanning raw logs.

### Blocked

Hi NAME,

Thanks for trying it. Please do not send a full `.abb` bundle yet. The smallest
useful debug artifacts are:

```bash
abb doctor --json
abb support RUN_ID
abb handoff RUN_ID
```

If there is no run ID yet, please send the exact command, exact error output,
your Python version, and whether this happened during install, doctor, CLI,
browser, SDK, HTTP API, proxy, or import/export.

### Workflow Done, Feedback Missing

Hi NAME,

Thank you for finishing the workflow. The most valuable follow-up is
`docs/DESIGN_PARTNER_FEEDBACK_FORM.md`, even if the answers are short.

The decision I am trying to make is whether to:

- fix docs/install before sending again,
- pause because privacy or redaction is unclear,
- send to the next design partner, or
- cut the next alpha package.

### Thank You And Decision

Hi NAME,

Thank you for the Agent Black Box feedback. I recorded this loop as:

```text
Partner decision: DECISION
Main learning: ONE_LINE_LEARNING
Next action: ONE_LINE_NEXT_ACTION
```

I will follow up only if I need to confirm a fix or if the next alpha directly
addresses the blocker you hit.

## Support Artifact Order

Ask for artifacts in this order:

1. Exact command and exact error output.
2. `abb doctor --json`.
3. `abb support RUN_ID`.
4. `abb handoff RUN_ID`.
5. `abb export RUN_ID --format handoff`.
6. Full `.abb` bundle only when the partner understands it includes artifact payloads.

Never request a full bundle when the problem can be diagnosed from doctor output,
a support packet, or a handoff packet.

## Partner-Level Rubric

Record one partner decision after feedback is returned or the partner is closed.

### `ready_next_partner`

Use this when:

- The partner installed with no live help or one small docs clarification.
- They recorded or inspected at least one run.
- They could explain what the run summary or debug path told them.
- They rated first useful command, debug path, or handoff usefulness as 4 or 5.
- Privacy/local-first clarity is 4 or 5.
- No stop condition occurred.

### `iterate`

Use this when:

- The partner sees value, but install/docs/workflow confusion slowed them down.
- They completed only part of the workflow because a command or concept was unclear.
- Any important score is 2 or 3, but privacy is not the blocker.
- The feedback identifies a fix that can be made before the next send.

### `pause`

Use this when:

- A known secret appears unredacted.
- The partner is unsure what data is local, shareable, or embedded in exported artifacts.
- A support packet, handoff packet, or bundle includes more data than expected.
- Install or workflow failure looks environment-wide, not partner-specific.
- The partner cannot safely share enough information to diagnose the issue.

### `ship_next_alpha`

Use this only after the partner has:

- Completed the workflow.
- Confirmed the debugging path is useful for a real or believable agent run.
- Confirmed the privacy boundary is clear.
- Returned feedback or live notes.
- Asked to use it again, try it on their own agent, or send it to another qualified agent builder.

## Cohort Decision Rubric

After three sends, summarize returned forms:

```bash
python3 scripts/feedback-summary.py .abb-feedback --output .abb-feedback/summary.json --markdown .abb-feedback/summary.md
```

Then make one cohort decision.

### Continue To Next Partners

Choose `ready_next_partner` for the cohort when:

- At least two of three partners install successfully.
- At least two inspect a run or reach a useful supportable blocker.
- At least one wants to try Agent Black Box on their own agent workflow.
- Average privacy/local-first clarity is 4 or higher among returned forms.
- No privacy, redaction, or bundle surprise stop condition occurs.

### Fix Before Sending Again

Choose `iterate` for the cohort when:

- Two partners hit the same docs, install, or workflow confusion.
- Average first useful command, debug path, or handoff score is below 4.
- The feedback shows value but the workflow is too hard to complete without help.
- A missing example, command label, or troubleshooting note would clearly improve the next send.

### Pause The Alpha

Choose `pause` for the cohort when:

- Any known secret appears unredacted.
- Two partners are confused about what data leaves their machine.
- Any partner shares a full bundle by accident because the docs were unclear.
- The release-readiness or smoke path fails in a normal local environment.
- The product cannot produce a useful support or handoff artifact after a failed workflow.

### Cut A New Alpha

Choose `ship_next_alpha` for the cohort only when:

- At least two partners complete the main workflow.
- At least two rate the core debugging value 4 or 5.
- At least one partner asks to use it on a real agent or with another agent.
- All P0/P1 issues from the loop are fixed or explicitly documented.
- The release gate passes after those fixes.

## Issue Priority

Use this priority when turning feedback into work:

| priority | meaning | examples |
| --- | --- | --- |
| P0 | Stop sending. | Secret exposure, misleading privacy boundary, broken install, data loss. |
| P1 | Fix before next send. | Same workflow blocker from two partners, broken support packet, confusing handoff contents. |
| P2 | Fix soon. | Better labels, missing command explanation, noisy output, unclear score prompt. |
| P3 | Polish. | Copy tweaks, nicer formatting, optional UI nicety. |

## Done Checklist

The first-send loop is done when:

- [ ] Three tracker rows exist.
- [ ] Each row has `artifact_sent`, `artifact_sha256`, `sent_at`, `status`, `next_follow_up_at`, and `owner`.
- [ ] Returned forms or live notes are saved under `.abb-feedback/`.
- [ ] `scripts/feedback-summary.py` has produced JSON and Markdown summaries.
- [ ] Support, handoff, or bundle paths are recorded for blockers.
- [ ] Each partner row has a decision.
- [ ] The cohort decision is written into the tracker notes or release notes.
- [ ] P0/P1 issues are fixed, documented, or explicitly used to pause the loop.
