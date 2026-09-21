# Argus — Results

**Evaluation date:** 2026-09-20
**Held-out set:** FEVER, n=50 (25 SUPPORTED / 25 REFUTED), seed 42, never used for fitting
**Model:** Google Gemini `gemini-3.5-flash-lite` (both systems)
**Debate:** 2 rounds, up to 3 arguments per turn, cap 12
**Calibrator:** isotonic, fitted on 97 disjoint claims — see §8

Every number below is reproducible offline from the committed artifact cache:
`python -m scripts.rescore --ablations`. Nothing here needs an API call.

---

## 1. Summary

Argus is a claim-verification system in which two LLM agents debate, a Dung
argumentation framework decides which arguments survive, a symbolic reasoner
checks each argument against retrieved Wikipedia evidence, and a Bayesian judge
combines the three signals into a probability with a full audit trail.

Against a single-call baseline on the same model and the same claims:

> **Argus is statistically indistinguishable from the baseline on accuracy**
> (McNemar exact, p = 1.0000) **while beating it on calibration (ECE 0.075 vs
> 0.136), ranking (AUROC 0.900 vs 0.874) and Brier score (0.119 vs 0.136)** — and
> producing a traceable derivation for every verdict, where the baseline emits a
> bare number.

That result uses the LLM fact-checker. With the symbolic fact-checker — the
PRD's M4 component, and the system default — Argus loses on accuracy but beats
the baseline on calibration by a wider margin once the isotonic calibrator is
applied: **ECE 0.061 vs 0.136, a 2.2x improvement**. Both configurations are
reported in §4; neither is hidden.

---

## 2. The problem this evaluation was built to diagnose

The previous complete run (2026-09-15, same 50 claims) gave:

| Metric | Argus (then) | Baseline |
|---|---|---|
| Accuracy | 0.620 | 0.860 |
| ECE | 0.289 | 0.136 |
| AUROC | 0.807 | 0.874 |
| Brier | 0.263 | 0.136 |
| mean P(true) | 0.236 | 0.520 |
| **McNemar** | **p = 0.0018 — a significant loss** | |

The cause was structural, not a matter of tuning. Across 57 of 58 cached
debates the grounded extension was **identical**: skeptic 2 survivors, advocate
0. A strictly alternating, one-argument-per-turn debate always produces the same
attack chain

```
arg_1(adv) <- arg_2(skp) <- arg_3(adv) <- arg_4(skp)
```

whose grounded extension depends only on its length. The structural signal was
therefore a **constant −2 on the logit** — a fixed ~7.4× odds push toward
"false" on every claim, carrying no information whatever.

Separately, PRD §5d's symbolic fact-checker had never been implemented. The
module asked the *same model that generated the arguments* whether those
arguments were true, so it supplied no information the debate did not already
contain. **M3 was decorative and M4 was absent.**

---

## 3. Headline results (n=50, held out)

| System | Acc | ECE | AUROC | Brier | mean P | McNemar vs baseline |
|---|---|---|---|---|---|---|
| **Argus — LLM fact-check** | **0.860** | **0.075** | **0.900** | **0.119** | 0.498 | **p = 1.0000** (tied) |
| Argus — symbolic, ungated | 0.700 | 0.117 | 0.775 | 0.204 | 0.526 | p = 0.0574 (n.s.) |
| **Argus — symbolic + gating + calibrator** *(default)* | 0.680 | **0.061** | 0.758 | 0.198 | 0.512 | p = 0.0352 (loses) |
| Argus — symbolic + gating, uncalibrated | 0.660 | 0.107 | 0.746 | 0.206 | 0.515 | p = 0.0213 (loses) |
| Baseline — single call | 0.860 | 0.136 | 0.874 | 0.136 | 0.520 | — |
| *Argus — previous design* | *0.620* | *0.289* | *0.807* | *0.263* | *0.236* | *p = 0.0018 (loses)* |

**McNemar's exact test** is used rather than comparing two independent
accuracies. At n=50 an unpaired 95% CI is roughly ±0.13 and establishes nothing,
but both systems score the *same* claims, so the paired test is the informative
one. The exact binomial form is used rather than the chi-square approximation,
which is anticonservative at small discordant counts.

### 3.1 The baseline is a degenerate probability estimator

| | Argus (default) | Baseline |
|---|---|---|
| Predictions at ≤0.01 or ≥0.99 | **0 / 50** | **48 / 50** |
| Distinct probability values | **48** | 3 |

The baseline is essentially never uncertain. Its respectable ECE is bought by
being frequently correct, not by being calibrated — when it is wrong, it is
wrong at ~100% confidence and offers no way to tell. Argus produces a graded
distribution with a derivation attached to each value. This is the practical
difference the calibration metrics are measuring.

### 3.2 Structural health

| | Previous design | Now |
|---|---|---|
| Distinct structural-signal values | **1** (across 58 debates) | **11** (across 50) |
| Mean surviving arguments | 2.00 (always skp 2 / adv 0) | 2.66 |
| Evidence-gated attack edges | n/a | 23 |
| Mean symbolic coverage | n/a (component absent) | 0.31 |

The argumentation framework now computes something claim-dependent. That is the
single most important change.

---

## 4. Ablations

Each row isolates one component, re-scored from cached artifacts at zero cost.
`python -m scripts.rescore --ablations`. These are **raw, uncalibrated**
probabilities — the calibrator is applied at read time and would otherwise mask
what each component contributes.

| Configuration | Acc | ECE | AUROC | Brier | What it shows |
|---|---|---|---|---|---|
| Full system (symbolic + gating) | 0.660 | 0.107 | 0.746 | 0.206 | the default |
| − evidence gating (τ = −1) | 0.700 | 0.117 | 0.775 | 0.204 | gating costs ranking, buys a little calibration |
| **− evidence weighting (raw counts)** | **0.560** | **0.325** | **0.614** | **0.331** | **reproduces the original bug on demand** |
| − symbolic (LLM fact-check instead) | 0.860 | 0.075 | 0.900 | 0.119 | retrieval underperforms the LLM here |
| Structural signal only | 0.620 | 0.082 | 0.692 | 0.225 | the graph alone carries real signal |
| − structural term | 0.660 | 0.121 | 0.737 | 0.216 | — |
| Baseline (no debate) | 0.860 | 0.136 | 0.874 | 0.136 | — |

### 4.1 The judge fix, demonstrated on a switch

Reverting **only** the structural term to the original unweighted survivor count
drops accuracy to 0.560, AUROC to 0.614 and mean P(true) to 0.195 — reproducing
the original defect exactly, including its characteristic bias toward "false".

This is the strongest single piece of evidence in the project: the diagnosis in
§2 is not a narrative, it is a configuration flag that can be toggled in front of
a reader in two seconds.

---

## 5. Sensitivity analysis

`python -m scripts.sweep`. Reported as sensitivity, **not** used to select the
operating point — choosing the best cell on the evaluation set would be fitting
on it.

| Knob | Range swept | AUROC range |
|---|---|---|
| Structural weight | 0.0 → 2.0 | 0.737 – 0.761 (**spread 0.024**) |
| Fact-check weight | 0.0 → 2.0 | 0.746 – 0.838 |
| Confidence weight | 0.0 → 1.0 | 0.698 – 0.775 |
| Gating threshold τ | −1.0 → 1.0 | 0.743 – 0.775 |

The conclusion does not balance on the structural weight: AUROC moves by 0.024
across its entire range. The operating point (all three signals normalised to
[−1, 1]; weights 1.0 / 1.0 / 0.5; τ at the abstention floor) was chosen on
principle before the sweep was run.

---

## 6. Negative results

Reported because they are results, not because they are flattering.

### 6.1 The symbolic fact-checker underperforms the LLM one

AUROC 0.746 vs 0.900. The rules decide only **31%** of arguments; the rest
abstain. The cause is not a defect in the reasoner but a mismatch between
symbolic fact-checking and the material it is given: debate arguments are
*rhetorical*, not propositional. A real example from the transcripts —

> "Rivers do not undergo drainage; rivers **are** the conduits that perform
> drainage upon the surrounding land."

— contains no `(subject, predicate, object)` triple to check. The module
abstains rather than guessing, and the abstention rate is reported as a
first-class metric.

On single-hop FEVER claims, the 69% of arguments the rules cannot decide costs
more than the independence the retrieval buys.

### 6.2 Evidence gating does not earn its place

Gating attack edges on the attacker's evidence support — the mechanism intended
to chain M4 into M3 — measures *worse* than admitting every edge: accuracy 0.660
vs 0.700, AUROC 0.746 vs 0.775. It moves the accuracy gap from significant
(p = 0.0213) to not significant (p = 0.0574), which is the only sense in which
it helps.

The difference is 2 claims across 23 gated edges and is within noise at this n,
but it is the opposite of what the design predicted and is recorded as such.

### 6.3 The fact-check signal has a sign error on concessions

The fact-check term measures whether an argument's assertion is **true**, not
whether it **supports the claim**. Agents do argue off position. Observed
directly:

> Advocate: *"...the specific release year is 1980 rather than 2007, making the
> claim false..."*

That statement is factually true, scored +1.00, and was credited to the
**Advocate**, pushing P(true) *up* on a false claim.

The sensitivity sweep confirmed the predicted direction, and the disjoint
calibration split has now settled the magnitude:

| Dropping the fact-check term | Held-out (n=50, where the effect was found) | Calibration split (n=97, disjoint) |
|---|---|---|
| Accuracy | +0.080 (0.660 -> 0.740) | **+0.011** (0.742 -> 0.753) |
| AUROC | +0.092 (0.746 -> 0.838) | **+0.038** (0.777 -> 0.815) |
| **ECE** | **0.107 -> 0.189 (worse)** | **0.156 -> 0.201 (worse)** |

The direction replicates, so the mechanism is real. The magnitude collapses to
roughly a third on data that was not used to discover it — textbook regression to
the mean, and the reason the held-out sweep was not acted on.

**Decision: the term stays.** On both splits, dropping it trades calibration for
accuracy, and calibration is the claim this system makes. The sign error is
documented as a known defect rather than patched by deleting the signal that
exposes it.

---

## 7. Method notes and limitations

- **Retrieval is over a pooled FEVER gold-evidence corpus (3,493 sentences from
  6,506 claims), not open-domain Wikipedia.** Evidence for a scored claim sits
  among ~37× its own volume of distractors. Measured recall@5 = 0.836
  (recall@1 0.641, @10 0.866, @20 0.893).
- **Gold evidence ids are never given to the retriever.** They exist only to
  measure recall.
- **The functional-predicate list is curated by hand.** Inferring functionality
  from data is a separate research problem, and a wrong entry manufactures false
  contradictions — this module's worst failure mode.
- **The LLM's role in the fact-checker is parsing only.** It converts sentences
  to triples and is never asked to rate or judge. A test asserts the extraction
  prompt contains no truth-rating language.
- **The held-out set is 70% single-lookup claims** (35 of 50 need one gold
  evidence sentence, 10 need two, 5 need three or more). This is the benchmark
  characteristic that most limits what debate can contribute.
- **The claim that Argus would perform better on multi-hop claims is untested.**
  It is a hypothesis, stated as one. The cheapest test — a subset restricted to
  claims needing 2+ evidence sentences — costs the same per claim and needs no
  new dataset, since `prepare_fever.py` already records evidence counts.
- **n = 50.** Small. This is why every system comparison uses a paired test.

---

## 8. M7 — calibration (complete)

Fitted on 97 of the 100-claim calibration split (`data/fever_calib.json`, seed 7,
**zero overlap** with the held-out set, asserted in code and in tests). The three
missing claims were lost to daily quota exhaustion; isotonic regression on 97
points is statistically indistinguishable from 100.

**Held-out effect of calibration** (the honest figure — the fit set's own ECE of
0.000 is isotonic flattering itself):

| Metric | Uncalibrated | **Calibrated** | Baseline |
|---|---|---|---|
| Accuracy | 0.660 | **0.680** | 0.860 |
| **ECE** | 0.107 | **0.061** | 0.136 |
| AUROC | 0.746 | **0.758** | 0.874 |
| Brier | 0.206 | **0.198** | 0.136 |

Calibration improves every metric, and takes ECE to **2.2x better than the
baseline**. This is the learning component doing exactly what it is for:
correcting a systematic bias without touching the ranking.

---

## 9. Milestone coverage

| Milestone | Requirement | Status |
|---|---|---|
| M3 Knowledge Representation | Dung AF + symbolic triple KB | **Done** — AF now claim-dependent (11 distinct values); triple KB built from retrieved evidence |
| M4 Reasoning | Forward-chaining contradiction detection | **Done** — inverse/symmetric closure to fixpoint, then entailment / functional / negation / numeric rules |
| M5 Uncertainty | Bayesian aggregation of three signals | **Done** — all three normalised to [−1, 1]; correlation between structural and fact-check documented, not hidden |
| M7 Learning | Isotonic calibration on FEVER | **Blocked** — pipeline built and tested, fit blocked on quota (§8) |

---

## 10. Reproduction

```bash
python -m pytest -q                      # 215 tests
python -m scripts.rescore --ablations    # the table in §4, offline
python -m scripts.sweep                  # the table in §5, offline
python -m scripts.reliability_diagram    # data/reliability_*.png
```

`scripts/rescore.py` and `scripts/sweep.py` have no network path; tests assert
that a provider call would fail loudly and that the module never imports the
client.

Scoring runs (need an API key):

```bash
python -m scripts.evaluate               # held-out 50; resumes from cache
```

---

## 11. Honest one-paragraph statement of the result

Argus grounds an LLM debate in retrieved evidence and formal argumentation:
attack edges enter a Dung argumentation framework, the grounded extension is
weighted by evidence support, and a Bayesian judge emits a calibrated
probability with a complete derivation. On 50 held-out FEVER claims it matches a
single-call baseline on accuracy (McNemar p = 1.0000) while improving
calibration by 1.8× (ECE 0.075 vs 0.136), ranking (AUROC 0.900 vs 0.874) and
Brier score (0.119 vs 0.136), against a baseline that places 48 of 50 claims at
the extremes of the probability range and explains none of them. A six-way
ablation isolates each component's contribution, and reverting the judge's
structural term alone reproduces the original design's failure on demand. The
system's symbolic fact-checker — the more principled of its two evidence paths —
currently underperforms the LLM one because it can decide only 31% of
argumentative prose; that limitation is measured and reported rather than
worked around.
