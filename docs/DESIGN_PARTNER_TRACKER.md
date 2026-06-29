# Design Partner Tracker

Use this to track the first local alpha loop from send to decision. Keep it
local unless you intentionally copy rows into another system. For the first
three sends, pair this tracker with
[DESIGN_PARTNER_INTAKE.md](DESIGN_PARTNER_INTAKE.md) and
[DESIGN_PARTNER_FIRST_SEND_PACKET.md](DESIGN_PARTNER_FIRST_SEND_PACKET.md).

## Status Values

- `candidate`: person or team fits the wedge, not contacted yet.
- `sent`: design-partner kit sent.
- `installed`: reviewer installed and ran `abb doctor`.
- `workflow_started`: reviewer began [FIRST_USER_WORKFLOW.md](FIRST_USER_WORKFLOW.md).
- `workflow_completed`: reviewer completed the main workflow.
- `feedback_returned`: reviewer returned [DESIGN_PARTNER_FEEDBACK_FORM.md](DESIGN_PARTNER_FEEDBACK_FORM.md) or live notes.
- `blocked`: reviewer hit a blocker that needs follow-up.
- `paused`: do not continue until a stop condition or trust issue is resolved.
- `done`: loop completed and decision is recorded.

## Tracker Fields

Use [DESIGN_PARTNER_TRACKER.csv](DESIGN_PARTNER_TRACKER.csv) for copy/paste.

| field | meaning |
| --- | --- |
| partner_id | Short local identifier, such as `dp-001`. |
| contact | Name, handle, or team. |
| segment | Agent founder, infra engineer, app developer, researcher, or other. |
| artifact_sent | Zip filename sent to the reviewer. |
| artifact_sha256 | `design_partner_kit` checksum from `dist/release-manifest.json`. |
| sent_at | Date sent. |
| status | One of the status values above. |
| current_step | Current workflow step or blocker location. |
| installed_at | Date install was confirmed. |
| workflow_completed_at | Date workflow was completed. |
| feedback_path | Local path to returned feedback form or notes. |
| support_packet_path | Local path to `abb support RUN_ID` packet, if shared. |
| handoff_path | Local path to `.handoff.json`, if shared. |
| bundle_path | Local path to `.abb` bundle, only when full payload sharing is approved. |
| blocker | One-line blocker or friction point. |
| next_follow_up_at | Date to follow up. |
| owner | Person responsible for the loop. |
| decision | `iterate`, `pause`, `ready_next_partner`, or `ship_next_alpha`. |
| notes | Short free-form note. |

## Operating Loop

1. Rank possible names with [DESIGN_PARTNER_INTAKE.csv](DESIGN_PARTNER_INTAKE.csv).
2. Before sending, create a row with `candidate`.
3. After sending the zip, set `status=sent`, record `artifact_sent`, `artifact_sha256`, and `sent_at`.
4. When they run `abb doctor`, set `status=installed` and record any warning in `blocker`.
5. When they begin the workflow, set `status=workflow_started` and set `current_step`.
6. If they stop, set `status=blocked`, record `blocker`, and ask for the smallest support artifact listed in [DESIGN_PARTNER_HANDOFF.md](DESIGN_PARTNER_HANDOFF.md).
7. When feedback returns, save the form under `.abb-feedback/`, set `status=feedback_returned`, and record `feedback_path`.
8. Summarize returned forms:

```bash
python3 scripts/feedback-summary.py .abb-feedback --output .abb-feedback/summary.json --markdown .abb-feedback/summary.md
```

9. Record the decision:
   - `iterate`: product/docs need a fix before the next send.
   - `pause`: privacy, redaction, or trust issue.
   - `ready_next_partner`: send to the next person.
   - `ship_next_alpha`: cut a new alpha package.
10. After three sends, use the cohort rubric in
   [DESIGN_PARTNER_FIRST_SEND_PACKET.md](DESIGN_PARTNER_FIRST_SEND_PACKET.md) to
   choose the next release step.

## Stop Conditions

Immediately set `status=paused` when:

- A known secret appears unredacted.
- The reviewer cannot install without repeated live help.
- The workflow fails before producing a useful run.
- A `.handoff.json` or support packet includes more data than expected.
- The reviewer is unsure what is local versus shareable.

## Example Row

| partner_id | contact | segment | artifact_sent | artifact_sha256 | sent_at | status | current_step | installed_at | workflow_completed_at | feedback_path | support_packet_path | handoff_path | bundle_path | blocker | next_follow_up_at | owner | decision | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dp-001 | NAME | agent founder | agent-black-box-0.1.0-design-partner.zip | SHA256 | 2026-06-29 | sent | install |  |  |  |  |  |  |  | 2026-07-02 | YOUR_NAME |  | First alpha send. |
