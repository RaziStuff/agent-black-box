# Design Partner Intake

Use this before sending the first Agent Black Box local alpha kit. The goal is
to choose the three highest-signal design partners, not the easiest three people
to message.

This is a local operator artifact. Keep real names, handles, and notes local
unless you intentionally copy them into another system.

## Files

- [DESIGN_PARTNER_INTAKE.csv](DESIGN_PARTNER_INTAKE.csv): candidate score sheet.
- [DESIGN_PARTNER_TRACKER.csv](DESIGN_PARTNER_TRACKER.csv): selected partner loop tracker.
- [DESIGN_PARTNER_FIRST_SEND_PACKET.md](DESIGN_PARTNER_FIRST_SEND_PACKET.md): send plan, copy, follow-ups, and decision rubric.

After filling the intake CSV, rank candidates from the source checkout:

```bash
python3 scripts/rank-design-partners.py docs/DESIGN_PARTNER_INTAKE.csv --markdown .abb-send/design-partner-ranking.md --json-output .abb-send/design-partner-ranking.json
```

The ranking output goes under `.abb-send/`, which is ignored by git and intended
for local operator notes.

## Candidate Segments

Pick one top candidate from each segment if possible:

- `agent founder`: building an agent product and debugging real agent behavior weekly.
- `agent infra engineer`: owns evals, observability, local tooling, support, or agent platforms.
- `local automation builder`: uses CLI, Python, notebooks, or local scripts for real workflows.

Only use `other` when the person is unusually strong on active agent pain and
local-first need.

## Score Fields

Score each field from 0 to 3.

| field | 0 | 1 | 2 | 3 |
| --- | --- | --- | --- | --- |
| active_agent_workflow | No active agent work. | Occasional experiments. | Active project in the last month. | Active project in the last 14 days. |
| debugging_pain | No clear pain. | Mild curiosity. | Recurring debugging friction. | Acute pain from traces, tools, retries, prompts, or handoff. |
| terminal_comfort | Avoids terminal. | Needs live help. | Can run copied commands. | Comfortable with Python/CLI/local tools. |
| local_first_need | Prefers hosted SaaS. | Neutral. | Some privacy/local need. | Strong local/private/debugging boundary need. |
| feedback_availability | Unlikely to respond. | Can skim only. | Can spend 20 minutes. | Can spend 20 to 40 minutes and return artifacts. |
| wedge_fit | Wants broad product ideas. | Interested but not the wedge. | Fits one core use case. | Directly tests run inspection, debug path, handoff, support, or agent-kit. |
| privacy_fit | Cannot share anything. | Unclear sharing boundary. | Can share redacted notes. | Can reason about support/handoff artifacts safely. |
| relationship_strength | Cold or low trust. | Weak tie. | Warm tie. | High-trust candid reviewer. |

## Dealbreakers

Do not send the first alpha if any of these are true:

- `active_agent_workflow` is `0`.
- `terminal_comfort` is `0`.
- `privacy_fit` is `0`.
- They need a hosted product, team admin, billing, or production SLA before trying anything.
- They mainly want to review the UI instead of debugging an agent workflow.

The ranking script marks candidates as `disqualified` for hard dealbreakers and
`low_signal` when the total score is too low for the first loop.

## Total Score

The script computes:

```text
total_score =
  active_agent_workflow
+ debugging_pain
+ terminal_comfort
+ local_first_need
+ feedback_availability
+ wedge_fit
+ privacy_fit
+ relationship_strength
```

Maximum score: `24`.

Use this interpretation:

- `20-24`: ideal first-loop candidate.
- `16-19`: strong candidate.
- `12-15`: maybe later; use only if segment coverage needs it.
- `0-11`: too low-signal for the first loop.

## Selection Rule

1. Remove `disqualified` candidates.
2. Prefer the top scorer in each core segment.
3. If a segment has no strong candidate, pick the next highest total score.
4. Do not select more than three people for the first send.
5. Copy the selected contacts into [DESIGN_PARTNER_TRACKER.csv](DESIGN_PARTNER_TRACKER.csv).
6. Generate checksum-filled send drafts:

```bash
python3 scripts/prepare-design-partner-send.py --owner YOUR_NAME --json
```

7. Replace placeholders in `.abb-send/design-partner-send-queue.md` with the selected contact names.

## Intake Columns

Use these columns exactly so the ranking script can parse the sheet:

```csv
candidate_id,contact,segment,source,active_agent_workflow,debugging_pain,terminal_comfort,local_first_need,feedback_availability,wedge_fit,privacy_fit,relationship_strength,notes
```

## Example Decision

If two candidates tie, pick the one with:

- higher `debugging_pain`,
- then higher `wedge_fit`,
- then better segment coverage,
- then stronger relationship.

If the best three people all come from the same segment, send to only the top
one from that segment first and keep the others as backups. The first loop needs
coverage across use cases more than it needs three versions of the same opinion.
