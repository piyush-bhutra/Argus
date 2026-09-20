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
| B | FEVER evidence retained + pooled corpus (spec §4.1) | none | **done** 2026-09-20 |
| C | BM25 retrieval + symbolic fact-checker + forward chaining (§4.2) | none | **done** 2026-09-20 |
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
- 2026-09-20 — Phase B landed. `copenlu/fever_gold_evidence` evidence is
  `[page, sent_id, text]` with FEVER wiki markup (`-LRB-` etc), now normalised.
  Corpus is 3,493 unique sentences pooled from 6,506 claims — smaller than the
  spec's ~5,000-claim estimate because the split shares evidence heavily. Gold
  density for the held-out 50 is ~1-in-37, judged adequate; **recall@k will be
  measured in Phase C and the pool enlarged across splits only if retrieval turns
  out to be saturated.** Regenerating the seed-42 sample produced byte-identical
  claims/labels/order, so the existing eval cache remains valid.
- 2026-09-20 — `.gitignore` amended: `fever_sample.json`, `evidence_corpus.json`
  and `eval_results.json` are now committed (spec §8).
- 2026-09-20 — Retrieval measured on the held-out 50: recall@1 0.641,
  **recall@5 0.836**, recall@10 0.866, recall@20 0.893. Not saturated, so the
  3,493-sentence pool is *not* too easy and stays as-is — the Phase B question is
  closed. k=5 adopted as the default (k=10 buys 0.03 recall for twice the noise
  into the rule engine). 5 of 50 claims retrieve no usable evidence at k=5, which
  is what the §4.2 abstention path exists for.
- 2026-09-20 — BM25 note: Okapi IDF is <=0 for terms in more than half the corpus,
  so such queries retrieve nothing. Harmless at 3,493 sentences; covered by a test
  so it is not rediscovered as a bug.
- 2026-09-20 — KB triples are stored canonical (normalised) by `derive_closure`;
  surface forms are recovered through the evidence id, not kept on the triple.
- 2026-09-20 — **Deviation from spec §4.2.** The spec said arguments the rules
  cannot decide fall back to "a lexical BM25 overlap score". Dropped: lexical
  overlap measures *relevance*, not *polarity*, so it cannot tell support from
  contradiction and a signed score derived from it would be fabricated. The
  fact-checker now abstains at 0.0 with `method="none"` instead, and symbolic
  coverage is reported. The legacy LLM score is still cached per §5.1, so the
  ablation can show whether an LLM fallback on abstention actually helps — if it
  does, it gets added on evidence rather than assumption.
- 2026-09-20 — Phase C landed. `tests/test_fact_checker.py` deleted: it encoded
  the LLM-as-judge contract that was deliberately replaced. Coverage moved to
  `tests/test_fact_checker_symbolic.py`.
- 2026-09-20 — Testing gotcha: `check_transcript` wraps the LLM call in
  `except Exception`, which swallows a test's `AssertionError` guard. "Must not
  call the model" tests count invocations instead of raising.
