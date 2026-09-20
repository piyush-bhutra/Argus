# Argus — Evidence-Grounded Redesign

**Status:** approved design, not yet implemented
**Date:** 2026-09-20
**Supersedes as work queue:** `ARGUS_HANDOFF.md` (2026-09-20, kept for its evaluation analysis)
**Does not supersede:** `debate_system_prd.md` (spec, to be amended per §9), `PROJECT_STATE.md` (decision record)

---

## 1. Problem

Argus is functionally complete end to end and 52 tests pass, but on the one valid
FEVER evaluation run (n=50, seed 42, 2 rounds, 2026-09-15) the single-LLM baseline
beats it decisively:

| Metric | Argus | Baseline |
|---|---|---|
| Accuracy @ 0.5 | 0.620 | 0.860 |
| ECE (10 bins) | 0.289 | 0.136 |
| AUROC | 0.807 | 0.874 |
| Brier | 0.263 | 0.136 |
| mean P(true) | 0.236 | 0.520 |

The project's thesis — that structured debate is better calibrated than one model
call — currently measures as false.

### 1.1 Root cause: the argumentation engine computes a constant

Decomposing all 58 cached rows in `data/eval_results.json`:

```
advocate survivors:  0 -> 57 debates,  1 -> 1 debate
skeptic  survivors:  2 -> 57 debates,  1 -> 1 debate
structural_signal:  -2 -> 57 debates,  0 -> 1 debate
```

`orchestrator.run_debate` alternates strictly, emits exactly one argument per turn,
and the prompt offers only a singular `attacks_argument_id`. Every 2-round debate
therefore produces the identical attack chain:

```
arg_1(adv) <- arg_2(skp) <- arg_3(adv) <- arg_4(skp)
```

The grounded extension of a chain is fully determined by its length: `arg_4` is
unattacked so it is IN, `arg_3` is OUT, `arg_2` is IN, `arg_1` is OUT. Skeptic 2,
advocate 0, every time.

`structural_signal` therefore carries **zero information**. It is a constant `-2`
on the logit — a fixed e^2 (~7.4x) odds push toward "false" on every claim. Argus's
AUROC of 0.807 comes entirely from the fact-check and confidence terms.

This is stronger than the diagnosis in `ARGUS_HANDOFF.md` §3, which describes a
"+1 skeptic bonus" from turn order. The real figure is -2 and it is total, not
partial. Correspondingly, handoff item 1.1 (normalise the structural term to
[-1,1]) would only reduce the constant from -2 to -1; the term would remain
information-free.

### 1.2 Root cause: the fact-checker supplies no independent evidence

PRD §5d specifies triple extraction, BM25 retrieval over the FEVER evidence corpus,
and forward-chaining contradiction detection. PRD line 18 names that forward
chaining as milestone **M4 Reasoning**.

`app/services/fact_checker.py` implements none of it. It asks the same Gemini model
that just generated the arguments whether those arguments are true. M4 has no
implementation at all, and Argus has no information the baseline lacks.

### 1.3 Milestone reality

| Milestone | PRD requires | Built | Load-bearing |
|---|---|---|---|
| M3 Knowledge Representation | Dung AF + symbolic triple KB | AF only | No — AF returns a constant |
| M4 Reasoning | Forward-chaining contradiction | nothing | No — missing |
| M5 Uncertainty | Bayesian aggregation of 3 signals | yes, 1 signal constant | Partly |
| M7 Learning | Isotonic calibration on FEVER | not fitted | No |

Three of four core milestones are decoration. This is the substantive problem the
redesign addresses; the benchmark loss is a symptom of it.

### 1.4 Offline confirmation (zero API calls)

Because the structural term is exactly recoverable from the cache,
`logit(raw) - structural` recovers the fact-check + confidence residual exactly.
Rescoring all 50 claims offline:

| Variant | acc | ECE | AUROC | Brier | mean P |
|---|---|---|---|---|---|
| Argus today | 0.620 | 0.289 | 0.807 | 0.263 | 0.236 |
| Baseline | 0.860 | 0.136 | 0.874 | 0.136 | 0.520 |
| drop structural | 0.760 | 0.089 | 0.835 | 0.167 | 0.552 |
| normalised, w=0.25 | 0.740 | **0.052** | 0.835 | 0.166 | 0.511 |
| normalised, w=0.5 | 0.740 | 0.064 | 0.831 | 0.169 | 0.470 |
| normalised, w=1.0 | 0.740 | 0.113 | 0.826 | 0.187 | 0.387 |

Fixing only the judge already beats the baseline on ECE by ~2.6x (0.052 vs 0.136),
and the result is flat in the weight across 0.25–1.0 — a sensitivity analysis that
requires no argmax fitting.

**Note:** these variants use a *count*-normalised structural term, which is the
simple fix, not the evidence-weighted term this design actually specifies (§4.5).
They are reported here as confirmation that the diagnosis in §1.1 is correct and as
a floor on what the redesign should achieve — not as the expected final numbers.

---

## 2. Goals

1. Make M3, M4, M5 and M7 genuinely load-bearing: every component must change the
   verdict in a measurable way, demonstrated by ablation.
2. Give Argus evidence the baseline does not have.
3. Make the argument graph a function of the claim and its evidence, not of turn order.
4. Produce a defensible, honestly framed evaluation with paired statistics.
5. Deploy a demo that does not depend on live LLM quota.

## 3. Non-goals

- Beating the baseline on raw FEVER accuracy at any cost. FEVER claims are
  single-hop memorised-knowledge lookups; a large accuracy win is not
  architecturally available and chasing it is not the objective.
- Open-domain retrieval over all of Wikipedia. Retrieval is over a pooled FEVER
  gold-evidence corpus, and is described as such.
- M6 debate-strategy planner. Out of scope.

---

## 4. Design

### 4.1 Evidence corpus and retrieval

`scripts/prepare_fever.py` currently discards evidence at line 84
(`rows = [(r["claim"], _label(r)) for r in ds ...]`). The source dataset,
`copenlu/fever_gold_evidence`, ships gold evidence sentences.

Changes:

- Retain the evidence field alongside `{claim, label}`.
- Emit a second artifact, `data/evidence_corpus.json`.
- Build the corpus from a **much larger draw than we score**: evidence pooled from
  ~5,000 FEVER claims while scoring ~150. A corpus containing only the scored
  claims' own evidence would be ~300 sentences, making retrieval trivially easy and
  the result optimistic. Realistic distractor density costs nothing extra because it
  comes from the same `load_dataset` call.
- Retrieval is BM25 via `rank_bm25`, already declared in `requirements.txt:6` and
  currently unused. No new dependency.
- Top-k evidence sentences per argument, k configurable, default k=5.

**Stated limitation:** this is retrieval over a pooled gold-evidence corpus, not
open-domain retrieval. The write-up says so explicitly.

**Risk:** the exact evidence field name in `copenlu/fever_gold_evidence` is
unverified. The loader must tolerate schema variants the way `_label()` already
does, and fail loudly rather than silently writing an empty corpus.

### 4.2 Symbolic fact-checker (M4)

**Division of labour: the LLM parses, the symbolic layer judges.**

One batched call per debate extracts `(subject, predicate, object)` triples from
every argument. This replaces today's batched "is this argument true?" call, so it
is cost-neutral. The model no longer renders a verdict — which is exactly what
removes the "same model asked twice" objection. Parsing is a task an LLM is
legitimately good at; judging is the task being taken away from it.

The KB is triples extracted from retrieved evidence sentences. Forward chaining runs
to fixpoint over an explicit rule base:

| Rule | Condition | Effect |
|---|---|---|
| functional contradiction | `(s,p,o1)` and `(s,p,o2)`, `o1 != o2`, `p` in the functional-predicate list | contradict |
| negation | `(s,NOT p,o)` against `(s,p,o)` | contradict |
| numeric mismatch | same subject+predicate, incompatible number or date | contradict |
| entailment | exact or synonym-normalised match | support |

"Functional" predicates are those that admit exactly one object for a given subject
(`born_in`, `capital_of`, `directed_by`, `died_in`, …). They are a small curated
list checked into the module, not inferred — inferring functionality from data is a
research problem of its own and out of scope. A predicate absent from the list never
fires the functional-contradiction rule.

Each argument receives:

- `support_score` in [-1, 1]
- `provenance`: which evidence sentence, which rule fired, which triples matched
- `coverage_flag`: `symbolic` or `no_symbolic_match`

**Abstention is deliberate.** Strict triple matching has poor recall on natural
language. The module abstains (score 0.0, `no_symbolic_match`) rather than guessing.
Where it abstains, a lexical BM25 overlap score fills in, explicitly marked as the
weaker path.

**Symbolic coverage — the fraction of arguments the rule engine could decide — is
reported as a first-class metric, not a footnote.** An honest coverage number is a
result; a hidden one would be the gimmick this redesign removes.

Graceful degradation is preserved: any failure yields neutral scores and the
pipeline does not crash.

### 4.3 Debate protocol

Each turn emits 1–3 arguments instead of exactly one. Each argument carries an
`attacks` list which may target **any** prior argument, including multiple targets.

- LLM call count is unchanged (one call per turn, more content per response), so
  there is no additional quota cost.
- The graph gains real branching: mutual attacks, undefended subtrees, and `UNDEC`
  nodes, which under the current chain protocol never occur at all.
- `Argument.attacks` is already `List[str]`; the schema is unchanged. This is
  orchestrator parsing plus prompt changes.

Validation rejects:

- self-attacks
- forward references (attacking an argument that does not yet exist)
- same-side attacks (an advocate attacking an advocate)

A hard cap of 12 arguments per debate bounds graph size and cost (2 rounds x 2
agents x 3 arguments). Arguments beyond the cap are dropped with a logged warning
rather than failing the debate.

### 4.4 Evidence-gated attack edges

An asserted attack becomes an edge in the argumentation framework **only if the
attacking argument's evidence support clears a threshold tau**. Default `tau = 0.0`
(the attacker must be non-negatively supported), swept in §5.4. Note that
`tau = -1.0` admits every asserted edge and reproduces the ungated behaviour, which
is how the gating ablation in §5.3 is implemented.

Unsupported attacks are not discarded. They are recorded as `asserted_unsupported`
and surfaced in the trace and the frontend: "this agent attacked but had nothing
behind it" is informative, and it is the visible proof that evidence, not rhetoric,
drives the graph.

This chains M4 into M3, which is a deliberate deviation from the PRD — see §9.

### 4.5 Judge

The structural term stops counting survivors and weights them by evidence:

```
structural = ( sum(support of advocate survivors) - sum(support of skeptic survivors) )
             / max(epsilon, sum(|support| of all survivors))
```

bounded in [-1, 1].

This fixes both defects identified in §1.1 at once:

- **Scale mismatch** — the term is now bounded on the same scale as the fact-check
  and confidence terms.
- **Last-speaker advantage** — a final argument that survived on schedule but has no
  evidence behind it contributes approximately 0. No special-casing of turn order is
  required, which makes it defensible rather than ad hoc.

**Known and accepted: signal correlation.** The structural and fact-check terms both
now read evidence, so PRD §5e's assumption of three independent signals no longer
holds strictly. They remain distinct — structural is "what survived, weighted by
evidence"; fact-check is "overall evidence balance across all arguments including
those that died" — but they are correlated. This is documented openly rather than
hidden, all three signals are retained because M5 requires three, and the weight
sweep (§5.4) doubles as evidence that the conclusion is not knife-edge on it.

Weights are chosen on principle (all three normalised, equal weight), **never by
argmax on the evaluation set**.

---

## 5. Evaluation protocol

### 5.1 The cache becomes the product

`data/eval_results.json` currently stores a final probability plus the grounded
extension. It will store the full artifact per claim, at a bumped schema version,
with old probability-only rows remaining readable:

- every argument: `id`, `agent`, `round`, `text`, `self_confidence`
- asserted attack edges, and which were gated out
- retrieved evidence with BM25 scores
- extracted triples and which rules fired
- **both** fact-check scores: symbolic and legacy-LLM

Storing both scores costs one extra batched call per debate and makes the single most
important ablation — does symbolic retrieval beat asking the model twice — free and
re-runnable forever, instead of requiring a second multi-hour run.

Everything downstream of the LLM then re-scores in seconds at zero cost: tau, the
three weights, top-k, the gating rule.

### 5.2 `scripts/rescore.py`

Reads cached artifacts, re-runs semantics + gating + judge only, writes a summary in
the same shape as `evaluate.py`. It must never touch the network. A test mocks
`call_grok` to raise, so any regression that reintroduces a call fails loudly.

### 5.3 Ablation table

The central result. Each row is a component justifying its existence. All six derive
from one scoring run because the artifacts carry everything.

| Configuration | What it tests |
|---|---|
| Full system | — |
| minus evidence gating (tau=-1, all edges admitted) | does gating the graph on evidence matter |
| minus evidence weighting (raw survivor counts) | reproduces the §1.1 bug deliberately; shows it *was* the bug |
| minus symbolic fact-check (LLM instead) | is retrieval better than asking the model twice |
| minus retrieval (shuffled evidence) | isolates retrieval *quality* from the rule engine |
| minus debate (single call) | the existing baseline |

The retrieval ablation assigns each argument evidence drawn from *another* claim
rather than an empty corpus. An empty corpus would make the rule engine abstain on
everything, which simultaneously disables retrieval, the rules and the evidence
weighting — measuring nothing in particular. Shuffled evidence keeps the rule engine
fully active and isolates exactly one variable: whether BM25 retrieved the *right*
sentences.

### 5.4 Metrics

Extend `evaluate.py` and the summary with:

- AUROC
- Brier score
- accuracy across a threshold sweep
- **McNemar's paired test** against the baseline — non-negotiable at this n.
  Unpaired CIs are approximately +/-0.13 and prove nothing, but both systems score
  the identical claims, so the paired comparison is far tighter and is the first
  thing a reviewer asks for.
- symbolic coverage
- sensitivity sweeps over tau, the three weights, and k, presented as sensitivity
  analysis rather than tuning

### 5.5 Split hygiene

- The seed-42 n=50 set stays **held out permanently**. It is rescored under the new
  protocol but never fits anything.
- A fresh 100-claim draw on a different seed fits the isotonic calibrator (M7).
- **Zero claim-text overlap is enforced by an assertion in the fitting code and by a
  test**, not by discipline. Fitting on evaluation claims is the one mistake that
  would invalidate every number in the write-up, so it must be impossible rather
  than merely avoided.

### 5.6 Cost

Approximately 7 LLM calls per claim: 4 turn calls, 1 batched triple extraction,
1 legacy fact-check retained for the ablation, 1 baseline. At ~150 claims that is
~1,050 calls, roughly 13 hours of unattended background time across free-tier quota
resets — comparable per-claim to the run already paid for. It runs once; afterwards
every remaining question is answered offline.

---

## 6. Hosting

**Constraint:** a live demo on a free Gemini tier will return 429 in front of
whoever is watching. The design accommodates that rather than hoping.

- The deployed artifact is driven by **precomputed debates**. The eval run leaves
  ~150 fully traced real FEVER debates — transcripts, graphs, evidence, provenance,
  verdicts — in the artifact cache. That becomes the demo corpus: visitors browse
  real debates with real argument graphs and real evidence chains, instantly, with
  no API dependency.
- Live debate remains available as an explicit opt-in, already degrading gracefully
  via `_friendly_error` in `app/services/pipeline.py:163`.
- `app/services/debate_store.py` already has the seeding path; this is mostly reuse.
- Backend: Render or Hugging Face Spaces free tier, native FastAPI, start command
  rather than Docker. Work required: start command, CORS origins for the deployed
  frontend, env vars as host secrets, demo-corpus export script.
- Frontend stays on its existing Cloudflare/Lovable path.

Frontend changes are substantive, not cosmetic:

- evidence panel with provenance
- `asserted_unsupported` edges rendered distinctly
- `UNDEC` nodes, which until now never occurred
- `frontend/src/lib/types.ts` tracks the schema changes

**Guardrail:** `frontend/AGENTS.md` notes the repo is connected to Lovable. Never
force-push or rewrite published history on the connected branch.

---

## 7. What we claim

Written before the numbers are known, so the framing is not chosen to flatter them:

> Argus grounds an LLM debate in retrieved evidence and formal argumentation. Attack
> edges enter the argumentation framework only when the attacker is supported by
> evidence retrieved from a FEVER corpus and verified by forward chaining over
> extracted triples; the grounded extension is then weighted by that evidence to
> produce a calibrated probability with a fully auditable trace. Against a
> single-call baseline it achieves [accuracy], [AUROC] and ECE [x] vs [y] — the
> baseline being a degenerate estimator that places 49 of 50 claims at 0.0 or 1.0 and
> is therefore never uncertain, including when it is wrong. An ablation over six
> configurations isolates the contribution of each component.

If the accuracy gap survives, it is reported plainly with McNemar's p-value, and the
conclusion is that structure buys calibration and auditability rather than raw
accuracy on single-hop claims. That is a real result.

---

## 8. Documentation durability

Standing requirement: the plan must survive session termination, and docs update in
the **same commit** as the code they describe.

| Artifact | Purpose |
|---|---|
| `docs/superpowers/specs/2026-09-20-argus-evidence-grounded-redesign.md` | this design |
| `docs/PLAN.md` | live work queue with per-phase status; supersedes `ARGUS_HANDOFF.md` |
| `docs/adr/` | ADRs for artifact cache schema, LLM-parses/symbols-judge, evidence-gated edges |
| `debate_system_prd.md` | amended per §9 |
| `PROJECT_STATE.md` | stale 2026-09-10 header fixed, §4 brought current |
| `PROJECT_SNAPSHOT.md` | consolidated into `PROJECT_STATE.md` rather than left to drift |

**`data/eval_results.json` must be committed.** `.gitignore:61` ignores `data/*` and
the cache is not in the exception list, so hours of quota-gated API time currently
exist on exactly one machine — and after this redesign the cache is the input to
every rescore and every ablation. Amend the exception list.

---

## 9. PRD amendments required

`debate_system_prd.md` is updated where this design deviates:

1. **§5c/§5d coupling.** The PRD treats the argumentation engine and the
   fact-checker as independent inputs to the judge. This design chains the
   fact-checker into the AF via evidence-gated attack edges (§4.4). Rationale: it is
   what makes M3 load-bearing.
2. **Debate protocol.** One argument per turn becomes 1–3 arguments per turn with
   free attack targeting (§4.3). Rationale: a strictly alternating single-attack
   debate produces a chain whose grounded extension is determined by the schedule,
   not by argument quality (§1.1).
3. **§5e signal independence.** The three judge signals are no longer independent;
   structural and fact-check both read evidence (§4.5). Documented, not hidden.
4. **§5d scope.** The LLM's role is narrowed from judging to triple extraction
   (§4.2).

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| Symbolic recall is low; coverage embarrassing | Abstention is designed in; coverage reported honestly as a result. Lexical fallback keeps the pipeline useful. |
| Evidence field name in the dataset differs | Tolerant loader following the existing `_label()` pattern; fail loudly, never write an empty corpus silently. |
| Multi-argument turns degrade JSON parse reliability | Existing 3-attempt retry and concede-on-failure path already handles this; validation rejects malformed edges. |
| Quota exhaustion mid-run | `evaluate.py` is already resumable and per-half config-stamped; unchanged. |
| Graph still degenerate after the protocol change | Measurable immediately from artifacts — check the survivor distribution before spending the full run. Gate the full run on a `--limit 10` smoke run showing varied structure. |
| Accuracy still below baseline | Anticipated and pre-framed (§7). The calibration and ablation results stand on their own. |

---

## 11. Implementation order

Detailed plan to follow in `docs/PLAN.md` via the writing-plans skill. Sequence:

1. Artifact cache schema + `rescore.py` + extended metrics (no LLM calls)
2. Judge fix, validated offline against the existing cache
3. Evidence corpus + BM25 retrieval (no LLM calls)
4. Symbolic fact-checker + forward chaining
5. Debate protocol change
6. Smoke run (`--limit 10`), verify graph structure actually varies
7. Full scoring run in background
8. Calibrator fit on the disjoint split
9. Ablations, sensitivity sweeps, reliability diagrams
10. Frontend schema updates
11. Hosting + demo corpus export
12. Write-up
