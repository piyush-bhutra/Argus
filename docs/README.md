# Argus documentation

Start here. Four root documents overlapped and drifted apart before this index
existed, and a 37 KB snapshot of the superseded architecture sat beside the
current ones with nothing marking it stale.

## Current

| Document | What it is | Read it when |
|---|---|---|
| [`RESULTS.md`](RESULTS.md) | The evaluation write-up: headline comparison, ablations, sensitivity sweeps, negative results, limitations | You want to know what the system actually achieves |
| [`PLAN.md`](PLAN.md) | The live work queue, per-phase status, decisions log, open gates | You are picking the work up |
| [`DEPLOY.md`](DEPLOY.md) | Hosting: environment, checklist, known constraints | You are deploying it |
| [`../PROJECT_STATE.md`](../PROJECT_STATE.md) | Architecture and decision record; §4a covers the redesign | You want to know *why* something is the way it is |
| [`../debate_system_prd.md`](../debate_system_prd.md) | The original spec. **Appendix A** records every deviation and why | You want the requirement behind a component |
| [`superpowers/specs/2026-09-20-argus-evidence-grounded-redesign.md`](superpowers/specs/2026-09-20-argus-evidence-grounded-redesign.md) | The approved design for the redesign | You want the reasoning behind the current architecture |
| [`../DEMO.md`](../DEMO.md) | Review demo script | You are presenting it |

## Archived

[`archive/`](archive/) holds superseded documents. Each carries a banner saying
what replaced it and, where relevant, which of its claims measurement later
contradicted. They are kept as a record, not as guidance — **nothing in
`archive/` describes the current system.**

## Precedence

When two documents disagree, later and more specific wins:

1. `RESULTS.md` for anything measured
2. `PLAN.md` for current status and open questions
3. `debate_system_prd.md` **Appendix A** over its own body
4. `PROJECT_STATE.md` for architectural rationale
5. `archive/` — historical only
