# Public Design Partner Call

Agent Black Box is looking for the first three public design partners for the
local alpha.

Release:

https://github.com/RaziStuff/agent-black-box/releases/tag/v0.1.0

Recommended download:

https://github.com/RaziStuff/agent-black-box/releases/download/v0.1.0/agent-black-box-0.1.0-design-partner.zip

SHA-256:

```text
20e3f38638c03fd24a94199ef2d058313214055c1a05a7fb67f678f5cc91db62
```

## Who We Want

You are a strong fit if you are one of these:

- An agent founder debugging real agent behavior weekly.
- An agent infra or platform engineer working on evals, observability, support,
  traces, local tooling, or agent handoff.
- A local automation builder using Python, CLIs, notebooks, or scripts for real
  workflows.

You should be comfortable running local terminal commands and able to spend 20
to 40 minutes trying the alpha.

## What To Test

The useful path is:

```bash
unzip agent-black-box-0.1.0-design-partner.zip
cd agent-black-box-0.1.0-design-partner
sh install.sh
. .venv/bin/activate
abb doctor
```

Then follow `docs/FIRST_USER_WORKFLOW.md`.

The highest-signal checks are:

- Does install work without live help?
- Does `abb doctor` make the local setup state clear?
- Does `abb show RUN_ID` make a run easier to understand?
- Does the Debug Path point to the first useful thing?
- Do support packets and handoff packets feel useful and safe to share?
- Is `abb delete RUN_ID --yes` clear as the local data cleanup path?

## Privacy Boundary

Agent Black Box stores data locally by default in `.abb/`.

Please do not paste secrets, customer data, private trace payloads, API keys, or
full `.abb` bundles into public issues. The safest first feedback artifacts are:

```bash
abb doctor --json
abb support RUN_ID
abb handoff RUN_ID
```

Only share full `.abb` bundles if you have reviewed them and are comfortable
sharing local artifact payloads.

## How To Raise Your Hand

Open a design-partner application issue:

https://github.com/RaziStuff/agent-black-box/issues/new?template=design_partner_application.yml

If you already tried the alpha, open a feedback issue:

https://github.com/RaziStuff/agent-black-box/issues/new?template=alpha_feedback.yml

## Decision Rule

After the first three design partners:

- If two of three install and record a run without live help, widen to ten.
- If install fails for two of three, stop and fix onboarding.
- If install works but handoff, support, or delete are unclear, improve the
  first-run workflow before widening.
