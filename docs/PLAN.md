# Argus — Live Work Queue

**Design:** [`docs/superpowers/specs/2026-09-20-argus-evidence-grounded-redesign.md`](superpowers/specs/2026-09-20-argus-evidence-grounded-redesign.md) (approved 2026-09-20)
**Supersedes:** `ARGUS_HANDOFF.md` as the work queue.

Update the status column **in the same commit** as the code it describes.

## Critical path

The full scoring run is ~13 h of quota-gated background time and everything
downstream of it is free. So the priority is **reach the smoke run fast, start the
full run, then do offline work while it executes**. Phases A–E are the critical
path; F onwards run against cached artifacts.

| # | Phase | LLM calls | Status |
|---|---|---|---|
| A | Extended metrics: AUROC, Brier, threshold sweep, McNemar | none | **done** 2026-09-20 |
| B | FEVER evidence retained + pooled corpus (spec §4.1) | none | not started |
| C | BM25 retrieval + symbolic fact-checker + forward chaining (§4.2) | none | not started |
| D | Debate protocol: multi-argument turns, free targeting (§4.3) | none | not started |
| E | Artifact cache schema v2 (§5.1) + smoke run `--limit 10` | ~70 | not started |
| F | **Full scoring run, background** (§5.6) | ~1050 | not started |
| G | Evidence-gated edges + evidence-weighted judge (§4.4, §4.5) | none | not started |
| H | `scripts/rescore.py` + no-network test (§5.2) | none | not started |
| I | Calibrator fit on disjoint split + overlap assertion (§5.5) | none | not started |
| J | Ablation table + sensitivity sweeps + reliability diagrams (§5.3) | none | not started |
| K | Frontend: evidence panel, unsupported edges, UNDEC nodes (§6) | none | not started |
| L | Hosting + demo corpus export (§6) | none | not started |
| M | Write-up, PRD amendments (§9), PROJECT_STATE consolidation (§8) | none | not started |

G–J are deliberately *after* F: they read cached artifacts, so they cost nothing and
can be iterated while the run is still going.

## Gates

- **Before F:** the smoke run must show the survivor distribution actually varies.
  If it is still ~constant, stop — the §4.3 protocol change did not work and
  spending 13 h would be wasted. (Spec §10.)
- **Before I:** zero claim-text overlap between the calibrator-fit split and the
  seed-42 held-out set, asserted in code and covered by a test.

## Decisions log

- 2026-09-20 — Spec approved. B+C chosen: multi-argument turns *and* evidence-gated
  attack edges. Rationale in spec §4.3–4.4.
- 2026-09-20 — `data/eval_results.json` to be committed; it is hours of quota-gated
  API time and the input to every ablation. Requires amending `.gitignore:61`.
- 2026-09-20 — Phase A landed. McNemar on the existing n=50 run gives p=0.0018
  (14 discordant pairs, 13 baseline-only). The baseline's win is **statistically
  significant**, correcting `ARGUS_HANDOFF.md` §2.4 which claimed the difference was
  unsupported by statistics. The gap is real and must be fixed, not reframed.
  AUROC 0.807 / Brier 0.263 reproduce the handoff's hand-computed values exactly.
