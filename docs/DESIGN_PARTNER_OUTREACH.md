# Design Partner Outreach

Use this when inviting a first local alpha user to try Agent Black Box.
Use [DESIGN_PARTNER_INTAKE.md](DESIGN_PARTNER_INTAKE.md) before this file so the
first three names are selected by fit and signal, not convenience.
For the first three sends, use
[DESIGN_PARTNER_FIRST_SEND_PACKET.md](DESIGN_PARTNER_FIRST_SEND_PACKET.md) to
choose partners, pick the right message variant, schedule follow-ups, and record
the final decision.

## Short Email

Subject: Local alpha: Agent Black Box for debugging agent runs

Hi NAME,

We are testing a local-first tool called Agent Black Box. It records AI agent
runs on your machine so you can inspect what happened, compare request/response
or input/output pairs, export a compact handoff packet, and share a support
bundle without sending data to a hosted service.

This is an early local alpha. The goal is not polish; the goal is to learn
whether the first workflow helps a real agent builder debug faster.

I attached:

- `agent-black-box-0.1.0-design-partner.zip`

To try it:

```bash
unzip agent-black-box-0.1.0-design-partner.zip
cd agent-black-box-0.1.0-design-partner
sh install.sh
. .venv/bin/activate
abb doctor
```

Then follow:

- `docs/FIRST_USER_WORKFLOW.md`

Afterward, please fill out:

- `docs/DESIGN_PARTNER_FEEDBACK_FORM.md`

Privacy notes:

- Agent Black Box stores data locally by default in `.abb/`.
- `.handoff.json` files are compact summaries and do not include full artifact payloads.
- `.abb` bundles include artifact payloads and should be treated as full trace archives.
- Please inspect artifacts before sharing anything back.

The most useful feedback is the first place you got confused, the first command
that felt valuable, and whether the handoff/debug path helped you understand a
run faster than normal logs.

Thank you,
YOUR_NAME

## Short DM

I have a local alpha ready for Agent Black Box, a local-first flight recorder for
AI agents. It records runs locally, lets you inspect/debug them, and exports
agent-ready handoff/support packets.

I will send `agent-black-box-0.1.0-design-partner.zip`. After unzipping:

```bash
sh install.sh
. .venv/bin/activate
abb doctor
```

Then follow `docs/FIRST_USER_WORKFLOW.md` and fill
`docs/DESIGN_PARTNER_FEEDBACK_FORM.md`.

Expected time: 20 to 40 minutes for the demo workflow, longer only if you try it
on your own agent. Data stays local unless you choose to export/share a packet.

## Follow-Up After No Reply

Hi NAME, quick nudge on the Agent Black Box local alpha. The highest-signal path
is just:

```bash
sh install.sh
. .venv/bin/activate
abb doctor
python3 examples/openai_wrapper_agent.py
abb runs
```

If you only have 10 minutes, I would love answers to:

- Did install/doctor work without help?
- Did `abb show RUN_ID` make the run easier to understand?
- What was the first confusing command or concept?

## What To Attach

Attach:

- `dist/agent-black-box-0.1.0-design-partner.zip`

Optionally include checksum text:

```text
SHA-256: PASTE_FROM_DIST_RELEASE_MANIFEST
```

Do not ask the user to clone the source checkout unless they are collaborating
on the implementation.

## Internal Send Checklist

Before sending:

- Run `python3 scripts/build-release.py`.
- Run `python3 scripts/release-readiness.py`.
- Run `python3 scripts/rank-design-partners.py docs/DESIGN_PARTNER_INTAKE.csv --markdown .abb-send/design-partner-ranking.md`.
- Run `python3 scripts/prepare-design-partner-send.py --owner YOUR_NAME --json` to create checksum-filled drafts under `.abb-send/`.
- Confirm `dist/release-manifest.json` says `"verification": {"status": "passed" ...}`.
- Confirm the `design_partner_kit` SHA-256 in `dist/release-manifest.json`.
- Use [DESIGN_PARTNER_FIRST_SEND_PACKET.md](DESIGN_PARTNER_FIRST_SEND_PACKET.md) to paste the current checksum into the message, choose the partner segment, set the follow-up date, and apply the decision rubric.
- Add or update the partner row in [DESIGN_PARTNER_TRACKER.csv](DESIGN_PARTNER_TRACKER.csv) with `status=sent`.
- Send [DESIGN_PARTNER_HANDOFF.md](DESIGN_PARTNER_HANDOFF.md) only if the reviewer wants more context.
- Ask them to return [DESIGN_PARTNER_FEEDBACK_FORM.md](DESIGN_PARTNER_FEEDBACK_FORM.md), `abb support RUN_ID`, or a `.handoff.json` packet before a full `.abb` bundle.
- Summarize returned forms with `python3 scripts/feedback-summary.py FEEDBACK_DIR --markdown FEEDBACK_DIR/summary.md`.
