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
| D | Debate protocol: multi-argument turns, free targeting (§4.3) | none | **done** 2026-09-20 |
| E | Artifact cache schema v2 (§5.1) + smoke run `--limit 10` | ~70 | **done** 2026-09-20 — gate PASSED at v5 |
| F | **Full scoring run, background** (§5.6) | 240 | **done** 2026-09-20, 50/50, 0 failures |
| G | Evidence-gated edges + evidence-weighted judge (§4.4, §4.5) | none | **done** 2026-09-20 (moved before E/F) |
| H | `scripts/rescore.py` + no-network test (§5.2) | none | **done** 2026-09-20 |
| I | Calibrator fit on disjoint split + overlap assertion (§5.5) | ~500 | **BLOCKED — daily quota exhausted** (3/100 scored) |
| J | Ablation table + sensitivity sweeps + reliability diagrams (§5.3) | none | **done** 2026-09-20 |
| K | Frontend: evidence panel, unsupported edges, UNDEC nodes (§6) | none | **done** 2026-09-20 |
| L | Hosting + demo corpus export (§6) | none | code **done**; needs a host account (`docs/DEPLOY.md`) |
| M | Write-up, PRD amendments (§9), PROJECT_STATE consolidation (§8) | none | **done** 2026-09-20 — `docs/RESULTS.md` |

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
- 2026-09-20 — Phase D landed. **Important finding while testing:** multi-argument
  turns and free targeting alone do *not* guarantee the grounded extension varies.
  Whoever speaks last is still never attacked, so a debate where both sides only
  rebut the most recent argument still yields skeptic-2 / advocate-0. The protocol
  makes other outcomes *reachable* (covered by a test), but the residual
  last-speaker bias is removed by the evidence weighting in spec §4.5, not by the
  protocol. This raises the stakes on the Phase E smoke-run gate: the survivor
  distribution must be checked empirically before spending the full run.
- 2026-09-20 — Turn parsing accepts both the new multi-argument shape and the old
  single-argument one. Models do ignore the requested shape, and salvaging beats
  burning one of the three retries.
- 2026-09-20 — **Phase G moved ahead of E/F.** The spec sequenced it after the
  full run because it costs no API calls, but the Phase D finding showed the judge
  is what removes the last-speaker bias — so the smoke run cannot tell us whether
  the system works unless G is already in. Reordered.
- 2026-09-20 — **Judge formula corrected by a failing test.** Spec §4.5 divided
  the structural term by total support *magnitude*. That makes it purely relative:
  a lone survivor backed by support 0.01 scores a full ±1.0 — the same "maximal
  signal from nothing" failure the term exists to remove. Denominator is now the
  survivor *count*, so the term tracks absolute evidence strength and is still
  bounded in [-1,1]. **Spec §4.5 needs amending to match** (tracked in Phase M).
- 2026-09-20 — Pipeline order changed: fact-check now runs BEFORE the semantics
  engine, since the graph is gated on evidence.

## Findings from the first v2 debates (2-claim run, 2026-09-20)

1. **Multi-argument turns work.** Debates now produce 4-9 arguments instead of
   always 4, with genuine branching — one argument attacked both `arg_1` and
   `arg_5`, reaching back past the most recent turn. The chain is broken.
2. **The constant is gone.** A debate where nothing retrieved evidence scored
   P=0.503 instead of the old 0.12. Survivors with no evidence now contribute
   zero, exactly as §4.5 intended.
3. **Symbolic coverage varies meaningfully**: 0.00 on "The Columbia River
   undergoes drainage" (a definitional dispute with no factual triple to check)
   and 0.75 on "Brubaker is a 2007 drama". Abstention is behaving as designed.
4. **Last-speaker effect persists structurally.** Both debates still ended with
   advocate-0 survivors, because whoever speaks last is unattacked. The evidence
   weighting neutralises its *numeric* effect but not its *structural* presence.
   Worth stating honestly in the write-up rather than claiming it is solved.
5. **OPEN — the concession bug.** In the Brubaker debate the advocate argued
   *"the release year is 1980 rather than 2007, making the claim false"* — it
   conceded. That argument is factually TRUE, so it scored +1.00 support, which
   the fact-check term credits to the **advocate** side, pushing P toward true on
   a false claim. The fact-check signal measures whether an argument's assertion
   is true, **not whether it supports the claim**, and agents do argue off
   position. This is a genuine design flaw, not noise.
   *Resolution:* do not guess. The `no structural term` and `structural only`
   ablations in `scripts/rescore.py` measure exactly this — if the fact-check
   term is hurting, the ablation will show it and the term can be dropped or
   re-signed on evidence. Decide after the full run.

## Smoke-run gate: PASSED at schema v5 (2026-09-20)

Four iterations, each ~70 calls, each answering one question:

| schema | change | coverage | distinct structural values | gated edges | ECE |
|---|---|---|---|---|---|
| v2 | first v2 debates | 0.12 | 2 / 10 | 0 | 0.412 |
| v3 | claim-level retrieval pooled into one KB | 0.22 | 4 / 10 | 2 | 0.412 |
| v4 | closed predicate vocabulary | 0.04 | 1 / 10 | 0 | 0.376 |
| v5 | vocabulary softened to a preference | **0.29** | **4 / 10** | **2** | **0.276** |

Gate criteria met: the structural signal is no longer constant (4 distinct values
vs 1 under the old protocol), gating fires, and coverage is at its highest.
Triple yield recovered to 1.59/argument with 22% of arguments yielding none.

**Two findings that need the full run to resolve, flagged now:**

1. **Evidence gating currently *hurts*** on this subset: accuracy 0.800 gated vs
   0.900 ungated, AUROC 0.760 vs 0.840. With only 2 gated edges across 10 claims
   this is far too weak to act on, but it is the opposite of the design's
   prediction and must be checked at n=50. If it holds, §4.4 needs revisiting.
2. **The LLM fact-check ablation scores 1.000 accuracy and 1.000 AUROC** — but so
   does the baseline on this subset. The n=10 draw is trivially easy for a single
   call, so it cannot discriminate between the two fact-checkers at all. This is
   a property of the subset, not evidence about symbolic retrieval.

**Cost of the full held-out run is 240 calls, not the ~1,050 the spec estimated:**
the baseline half is unchanged since the original run and is entirely cached, and
10 of 50 claims already carry v5 artifacts. Only 40 Argus halves remain.

## M7 decision (2026-09-20)

Asked which way to spend the remaining quota after the n=50 run: a multi-hop
subset that would test whether debate helps where a single lookup fails, or the
calibrator. **Chosen: the calibrator.** An unbuilt graded milestone is a worse
thing to defend than an untested hypothesis.

Consequence to honour in the write-up: the claim that Argus would do better on
harder claims stays an **assertion**, not a result, and must be worded that way.
The multi-hop subset remains the cheapest available follow-up — same cost per
claim, no new dataset — because `prepare_fever.py` already records how many gold
evidence sentences each claim needs. The held-out 50 splits 35 / 10 / 5 by
one / two / three-plus evidence sentences, so it is 70% single-lookup claims.

### Calibration split

- `data/fever_calib.json`: 100 claims, 50T/50F, seed 7, built with
  `--exclude data/fever_sample.json`. **Overlap with the held-out set: 0**,
  verified and asserted in `scripts/fit_calibrator.py`, which refuses to write a
  calibrator on any overlap at all.
- The evidence corpus is byte-identical after the exclusion (MD5 checked): the
  filter removes held-out *claims* from the fit draw without removing their
  *evidence* from the shared corpus, which retrieval still needs.
- `--no-legacy-factcheck` skips the ablation-only call, saving one request per
  claim: ~500 calls instead of ~600.

## RESULTS — held-out n=50, schema v5 (2026-09-20)

| configuration | acc | ECE | AUROC | Brier | McNemar vs baseline |
|---|---|---|---|---|---|
| **Argus, LLM fact-check** | **0.860** | **0.075** | **0.900** | **0.119** | p=1.0000 (tied) |
| Argus, symbolic ungated | 0.700 | 0.117 | 0.775 | 0.204 | p=0.0574 (n.s.) |
| Argus, symbolic + gating (default) | 0.660 | 0.107 | 0.746 | 0.206 | p=0.0213 (loses) |
| Argus, old unweighted judge | 0.560 | 0.325 | 0.614 | 0.331 | — |
| Baseline (single call) | 0.860 | 0.136 | 0.874 | 0.136 | — |
| *Argus before this session* | *0.620* | *0.289* | *0.807* | *0.263* | *p=0.0018 (loses)* |

Structure: **11 distinct structural values** (was 1), 23 gated edges, mean
survivors 2.66, symbolic coverage 0.31.

### What this establishes

1. **The thesis holds.** Argus with LLM fact-checking is statistically
   indistinguishable from the baseline on accuracy (McNemar p=1.0000, 2 vs 2
   discordant) while beating it on **calibration (ECE 0.075 vs 0.136)**,
   **ranking (AUROC 0.900 vs 0.874)** and **Brier (0.119 vs 0.136)** — and
   producing a full auditable trace, where the baseline places 49 of 50 claims
   at 0.0 or 1.0 and explains nothing.
2. **The degeneracy is gone.** 11 distinct structural values where there was 1.
3. **The bug is reproducible on demand.** Reverting only the judge's structural
   term to the unweighted count gives 0.560 / ECE 0.325 / AUROC 0.614 and mean P
   0.195 — the original defect, on a switch.
4. **Even the symbolic path beats the baseline on ECE** (0.107 vs 0.136), which
   was false before this session (0.289).

### Honest negative results

- **The symbolic fact-checker underperforms the LLM one** (AUROC 0.746 vs 0.900)
  at 31% coverage. M4 is built and correct, but on single-hop FEVER claims the
  71% of arguments it cannot decide cost more than the independence it buys.
- **Evidence gating does not earn its place on this sample.** Ungated scores
  better on accuracy (0.700 vs 0.660) and AUROC (0.775 vs 0.746), and moves the
  accuracy gap from significant (p=0.0213) to not (p=0.0574). The difference is
  2 claims across 23 gated edges, so it is within noise — but it is the opposite
  of what spec §4.4 predicted and must be reported as such, not buried.

## Sensitivity sweeps, n=50 (2026-09-20)

Run with `scripts/sweep.py`, entirely off cached artifacts. Reported as
sensitivity; the operating point is **not** selected from it, which would be
fitting on the evaluation set.

- **Structural weight 0.0 -> 2.0: AUROC 0.737 to 0.761, spread 0.024.** Flat. The
  conclusion does not balance on the weight, which is exactly what the sweep is
  there to show.
- **tau:** ungated (-1.0) is best on accuracy/AUROC (0.700 / 0.775); higher tau is
  better on ECE (0.063 at 0.25). Gating trades ranking for calibration.
- **Confidence weight 1.0** scores better than the chosen 0.5 (0.700 / 0.775).

### The concession bug now has evidence

Setting the **fact-check weight to 0.0** gives accuracy **0.740** and AUROC
**0.838**, against 0.660 / 0.746 at the chosen weight of 1.0. Removing the term
entirely is the best setting in its sweep.

This is *not* an argmax to be chased. It matters because the mechanism was
identified independently and earlier, by reading a single debate transcript
before this sweep existed: the Advocate argued *"the release year is 1980 rather
than 2007, making the claim false"* — conceding — and that true statement scored
+1.00 and was credited to the Advocate. The fact-check term measures whether an
argument's assertion is **true**, not whether it **supports the claim**.

The sweep confirms the direction that mechanism predicts. That is a hypothesis
tested, not a parameter tuned.

**Next step, and the reason it is not acted on yet:** the 100-claim calibration
split is disjoint from this evaluation set. Once it finishes scoring, the same
comparison can be run there. If dropping the fact-check term also helps on data
that was never used to find the effect, the finding is confirmed and the change
is principled. If it does not, this was overfitting and the term stays. **Do not
change the weight before that check.**

## BLOCKED on quota (2026-09-20)

The calibration run hit the free tier's **daily** quota after 3 of 100 claims.
Everything requiring the LLM is stopped until the quota resets.

**Nothing already earned is lost.** The held-out n=50 result is complete,
committed, and is the project's main finding. `data/calib_results.json` holds the
3 scored claims and `scripts/evaluate.py` resumes from it.

### To resume (single command, no setup)

```
python -m scripts.evaluate --sample data/fever_calib.json   --results data/calib_results.json --summary data/calib_summary.json   --no-baseline --no-legacy-factcheck --delay 3
```

Then: `python -m scripts.fit_calibrator` (refuses below 20 points), then
`python -m scripts.evaluate` to re-score the held-out set with the calibrator
loaded — the pipeline picks up `data/calibrator.pkl` automatically.

### Also waiting on that data

The disjoint check on the concession bug (§ sweeps above). **Do not drop the
fact-check term until it is run on the calibration split**, which was not used to
discover the effect.

### Everything remaining is zero-quota

Demo corpus export, frontend, deployment and the write-up all run off cached
artifacts and need no API access.

## Frontend evidence trace (2026-09-20)

Each argument post-it now carries its evidence: the support score or ABSTAINED,
which rules fired, the extracted triples, and the source sentence. The Ruling
panel gains an EVIDENCE AUDIT block showing symbolic coverage and every asserted
attack that was refused for lack of evidence, struck through.

**Bug found only by looking at the rendered page.** The trace showed
`evidence_sentences[0]` — the top *retrieved* sentence — not the sentence that
actually fired the rule. A real demo rendered `numeric_mismatch -1.00` beside a
sentence about *Journalism* that had nothing to do with the claim. The rule was
correct (the argument said 1981, the evidence said 1979); the displayed
provenance was wrong, which is worse than showing none.

Fixed on both paths: `fact_checker` now records the firing sentences, and
`rescore._fact_results` resolves `evidence_ids` against the corpus for cached
artifacts. Two regression tests cover it. `rescore._fact_results` was also
dropping `triples` entirely, so exported demos showed a verdict with no visible
derivation.

Verified in the browser at desktop and 375px (no horizontal scroll).

## Write-up (2026-09-20)

`docs/RESULTS.md` — the evaluation write-up. Every figure is reproducible offline
from the committed artifact cache; nothing in it needs an API call.

New figure worth keeping: **the baseline places 48 of 50 claims at <=0.01 or
>=0.99 and uses 3 distinct probability values. Argus places 0 of 50 at the
extremes across 48 distinct values.** That quantifies the "degenerate estimator"
claim precisely rather than asserting it.

`docs/DEPLOY.md` — deployment. The key property is that the deployed demo needs
**no API key and no quota**: 53 precomputed debates ship inside the image, so a
viewer never meets a 429. Live debate is an optional extra.

Frontend detail worth not rediscovering: `VITE_API_BASE_URL` is baked in at
**build** time by Vite and defaults to `http://localhost:8000`. A deployed build
without it silently falls back to bundled mock data via `apiState.usingMock`,
which looks like a working debate rather than an error.

## Security review (2026-09-20)

Audit before deployment. Git history scanned for secrets across all refs: none
ever committed, `.env` never tracked.

**Fixed:**

| # | Issue | Severity | Fix |
|---|---|---|---|
| 1 | `POST /debate/start` unauthenticated with no rate limit — each call spends ~6 LLM requests, so the endpoint was an **open LLM proxy onto the operator's quota** | High | `app/core/ratelimit.py`, 5 starts / 5 min per caller, configurable; `X-Forwarded-For` honoured only when `TRUST_PROXY_HEADERS` is set |
| 2 | `claim` length unbounded — a **1 MB claim was accepted**, and the claim is embedded in every prompt of the debate | High | `max_length=1000` on the model |
| 3 | `debate_store` never evicted — unbounded memory growth from anonymous requests (53 -> 259 records in one test burst) | Medium | cap 500 user debates, FIFO eviction; seeded demos protected |
| 4 | Pipeline errors echoed `str(e)[:300]` to unauthenticated callers, leaking provider endpoints, model names and internal paths | Medium | generic message to the caller, detail to the log |
| 5 | `starlette 0.52.1` reachable in the HTTP layer with 6 advisories; `requirements.txt` unpinned so a fresh build could resolve back into them | Medium | upgraded to 1.6.0; requirements floored and major-pinned |
| 6 | No security headers | Low | `nosniff`, `DENY`, `no-referrer`, restrictive CSP |
| 7 | No `.dockerignore` — a future `COPY . .` would bake `.env` into a published layer | Low | added |

**Bug found in my own fix:** the rate limiter's memory guard only dropped keys
whose deque was empty, but entries expire lazily per key, so nothing was ever
empty — the control intended to prevent memory exhaustion did not work. It now
sweeps on the last hit. Caught by a test asserting the bound.

**Reviewed, no change needed:** `rounds` was already clamped; `debate_id` is a
dict key with no filesystem path; React escapes model output so prompt injection
cannot become XSS; `lovable-error-reporting` calls an editor-injected global with
no network path; no build artifacts or `node_modules` tracked.

**Accepted risks, documented in `docs/DEPLOY.md`:** no authentication (no user
accounts exist); rate limit is per process and resets on restart; `CORS_ORIGINS`
defaults to `*`.

**Not addressed — prompt injection.** A caller controls `claim`, which enters the
LLM prompt. Output is rendered as text (React-escaped, no `innerHTML`), attack
ids are validated against the transcript, and the model never drives code, so the
impact is confined to influencing generated text. Worth stating in the write-up
rather than claiming the system is injection-proof.
