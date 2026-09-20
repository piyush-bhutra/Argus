# PRD — Multi-Agent Debate System for Verified Claims
*(working name: Verdikt — rename freely)*

## 1. Overview

**One-liner:** Two LLM agents (Advocate, Skeptic) debate a factual claim across structured rounds; a formal argumentation engine, a symbolic fact-checker, and a calibrated Bayesian judge combine to produce a truth-probability verdict with a fully auditable trace — instead of asking one model to just answer.

**Problem statement:** Single-model fact verification is opaque and poorly calibrated — LLMs are frequently overconfident on false claims. This project tests whether structured, adversarial multi-agent debate plus formal argumentation semantics plus calibrated aggregation produces measurably better-calibrated, more explainable truth judgments than a single LLM call, evaluated against a real labeled dataset.

**Course syllabus mapping:**

| Module | Component |
|---|---|
| M1 Agents | Advocate/Skeptic/Judge as distinct agents with a defined percept-action loop |
| M2 Search (adversarial) | Argument-graph evaluation ~ minimax-style attack/defense depth |
| M3 Knowledge Representation | Argument attack graph (Dung's AF); fact triples as a symbolic KB |
| M4 Reasoning | Forward-chaining contradiction detection against the KB |
| M5 Uncertainty | Bayesian aggregation of grounded-extension outcome + fact-check support + agent confidence |
| M7 Learning | Calibration model (isotonic/Platt) trained + evaluated on FEVER labels |

*(M6 Planning is intentionally thin — round/turn management is simple, not a planning problem. If your prof wants explicit planning coverage, we can add a "debate strategy planner" that sequences which arguments to raise next based on the opponent's weak points — flag it and I'll scope that as an extension.)*

## 2. Goals / Non-Goals

**Goals**
- Working end-to-end debate → verdict pipeline on a real dataset, not toy examples
- Demonstrable ECE (calibration error) improvement over a single-LLM baseline
- Fully inspectable transcript + argument graph for the demo/viva
- Clean repo structure Antigravity/Codex can extend without hand-holding every file

**Non-goals (MVP)**
- Not scaling to real-time/production traffic
- Not fine-tuning any models
- Not supporting arbitrary open-domain claims beyond the eval dataset's domain
- Not building a full first-order theorem prover — KB chaining stays deliberately scoped (§5c)

## 3. Assumptions (flag if wrong — changes §10's milestones)
- Solo build, ~2-3 week timeline (per picking option 11 over 12)
- Grok API as the LLM provider for all agents
- FEVER (or LIAR, see §6) as the eval dataset

## 4. Architecture

```
+-------------+     +-------------+
|  Advocate   |     |  Skeptic    |
|  Agent (LLM)|     |  Agent (LLM)|
+------+------+     +------+------+
       |  arguments        |  arguments
       v                   v
+-----------------------------------+
|     Debate Orchestrator            |  <- manages rounds, turn order
+-----------------+-------------------+
                   v
+-----------------------------------+
|  Argument Graph (Dung's AF)        |  nodes=arguments, edges=attacks
|  Semantics Engine (grounded ext)   |
+-----------------+-------------------+
                   v
+-----------------------------------+     +------------------------+
|  Fact-Check / KB Chaining Module   |<--->| Evidence corpus (FEVER)|
+-----------------+-------------------+     +------------------------+
                   v
+-----------------------------------+
|  Bayesian Judge + Calibration      |  -> final P(claim true) + explanation
+-----------------+-------------------+
                   v
+-----------------------------------+
|  FastAPI backend                   |
+-----------------+-------------------+
                   v
+-----------------------------------+
|  React dashboard (transcript,      |
|  argument graph viz, verdict)      |
+-------------------------------------+
```

## 5. Core Components

### a. Debate Orchestrator
- Manages N rounds (default 3) between Advocate and Skeptic
- Each turn: agent receives claim + full transcript so far + its own role prompt, returns a structured argument object (schema in §8)
- Terminates early if an agent has no new argument to raise (concedes)

### b. Advocate / Skeptic Agents
- Thin wrapper around the Grok API (integration notes in §13)
- Role-specific system prompts; Advocate argues the claim is TRUE, Skeptic argues FALSE
- Each returned argument includes: claim text, which prior argument it attacks (or null if opening), and a self-reported confidence (0-1) — treat this as a raw, uncalibrated signal for the Bayesian layer, not ground truth

### c. Argument Representation & Semantics Engine
- Implement Dung's Abstract Argumentation Framework: arguments = nodes, "attacks" = directed edges
- Compute the **grounded extension** via the standard fixpoint labeling algorithm (IN/OUT/UNDEC) — real, gradable CS, not a wrapper around an LLM call
- Output: which arguments survive (are "in" the grounded extension) per side — a structural signal independent of rhetoric

### d. Fact-Checking / KB Chaining Module
- Scope deliberately tight: extract simple (subject, predicate, object) triples from each argument (basic dependency parse, or ask Grok to extract structured triples)
- Retrieve top-k evidence sentences from the FEVER evidence corpus via BM25 (`rank_bm25` — lightweight, no heavy indexing infra)
- Forward-chaining: if a retrieved evidence triple directly contradicts or entails an argument's triple, propagate a support/contradict flag — this is the M4 reasoning component, scoped so it's buildable in days, not weeks
- Output feeds the Bayesian judge as a check on the debate, not a replacement for it

### e. Bayesian Judge + Calibration
- Combine three signals per claim: (1) grounded-extension outcome, (2) fact-check support/contradict scores, (3) agents' self-reported confidence
- Simple Bayesian combination (log-odds pooling or a small logistic model) → raw P(claim true)
- **Calibration (the actual "learning" component):** fit isotonic regression or Platt scaling on a held-out FEVER split, mapping raw P → calibrated P
- Evaluate with Expected Calibration Error (ECE) against FEVER ground truth — this is the headline metric that makes the demo defensible

### f. Transcript & Explanation Layer
- Every verdict ships with: full debate transcript, the argument graph (which arguments survived), fact-check flags, and the calibration math — nothing is a black box

### g. API Layer (FastAPI)
See §9.

### h. Frontend / Dashboard (React + Tailwind)
- Claim input, live/replay transcript view, argument graph visualization (React Flow or vis.js), final verdict with calibrated probability
- This is the piece Lovable is genuinely good at — feed it §9's contract and let it build the UI shell fast

## 6. Data
- **Primary: FEVER** (Fact Extraction and VERification) — labeled claims (SUPPORTS/REFUTES/NOT ENOUGH INFO) with Wikipedia evidence sentences. Public, well-documented — lets you show real ground-truth accuracy and calibration numbers, not vibes.
- **Alternative: LIAR** — shorter political statements, 6-way truthfulness labels, less plumbing if FEVER's evidence corpus feels too heavy for your timeline
- MVP eval set: ~50-100 claims, stratified across labels — not the full dataset

## 7. Tech Stack
- Backend: Python 3.11+, FastAPI, Pydantic
- Argument graph: networkx + a custom grounded-extension algorithm
- Retrieval: rank_bm25 (or Whoosh for a proper index)
- Calibration: scikit-learn (isotonic/Platt), reliability diagrams via matplotlib
- LLM: Grok API, OpenAI-compatible client (§13)
- Frontend: React 18, Tailwind, React Flow or vis.js
- Deploy (optional, for demo): Vercel (frontend) + Render (backend)

## 8. Data Models (sketch)

```python
class Argument(BaseModel):
    id: str
    agent: Literal["advocate", "skeptic"]
    round: int
    text: str
    attacks: list[str]        # ids of arguments this one attacks
    self_confidence: float    # 0-1, raw/uncalibrated

class FactCheckResult(BaseModel):
    argument_id: str
    evidence_sentences: list[str]
    support_score: float      # -1 (contradicts) to 1 (supports)

class Verdict(BaseModel):
    claim: str
    raw_probability: float
    calibrated_probability: float
    grounded_extension: dict[str, list[str]]   # side -> surviving argument ids
    explanation: str
```

## 9. API Contracts

```
POST /debate/start
  body: { "claim": string, "rounds": int = 3 }
  returns: { "debate_id": string }

GET /debate/{debate_id}/transcript
  returns: { "arguments": Argument[], "status": "in_progress" | "complete" }

GET /debate/{debate_id}/verdict
  returns: Verdict

GET /debate/{debate_id}/graph
  returns: { "nodes": [...], "edges": [...] }   # for the frontend graph viz
```

## 10. Milestones (assumes solo, ~3 weeks — rescope if the assumption in §3 is wrong)

- **Week 1:** Debate orchestrator + Advocate/Skeptic agents wired to Grok; argument graph structure + grounded-extension algorithm, tested on synthetic claims
- **Week 2:** FEVER integration (evidence corpus + BM25 retrieval), fact-check/chaining module, Bayesian judge (raw, uncalibrated), FastAPI endpoints
- **Week 3:** Calibration (isotonic/Platt), evaluation run on the eval set, ECE + baseline comparison, frontend dashboard (via Lovable), transcript/graph viz, demo polish

## 11. Evaluation Plan
- **Baseline:** single Grok call — "is this claim true?" with a confidence score
- **System:** full debate → calibrated verdict
- **Metrics:** accuracy vs FEVER labels, ECE (calibration), reliability diagram for both, plus a qualitative read of a handful of transcripts
- **The sentence that sells this to your prof:** "the calibrated debate system has X% lower ECE than a single-model baseline on N held-out claims" — concrete and falsifiable, not just a demo

## 12. Risks & Mitigations
| Risk | Mitigation |
|---|---|
| LLM cost/rate limits mid-eval run | Pick a cost-efficient Grok tier for agent calls (§13); batch eval runs; cache responses |
| Debate is non-deterministic, eval noisy | Fix low temperature for eval runs; average over 2-3 seeds if time allows |
| Fact-check module scope creep (easiest part to over-engineer) | Hard cap: BM25 + simple triple matching, no fine-tuned NLI model unless Week 3 has slack |
| Grounded-extension bugs (silent, hard to debug) | Unit test on 3-4 hand-constructed toy argument graphs with known extensions before wiring to live debates |

## 13. LLM Provider: Grok Integration Notes
- xAI's API is OpenAI-SDK-compatible — point the standard `openai` Python client at `base_url="https://api.x.ai/v1"` with your xAI key, no separate SDK required:
```python
from openai import OpenAI
client = OpenAI(api_key=XAI_API_KEY, base_url="https://api.x.ai/v1")
response = client.chat.completions.create(
    model="grok-4.6",  # confirm current model IDs at console.x.ai — see note below
    messages=[{"role": "user", "content": "..."}],
)
```
- **Model choice:** xAI's lineup has been shifting fast in 2026 — several older model IDs (grok-4, grok-4.1, grok-3) have already been retired and redirect to newer ones. Check `console.x.ai` for the current cheapest/fastest tier before locking a model name into your code; as of Aug 2026, grok-4.3 was the general-purpose value option and grok-4.6 the top-quality one, but confirm before you build since this changes month to month.
- For this project: use the cheapest available tier for the Advocate/Skeptic agents (they run many calls per debate), and reserve a stronger model for the fact-check/judge step only if budget allows — that's the piece that most needs sharper reasoning.
- xAI has periodically run free-API-credit programs — worth checking `console.x.ai` directly before budgeting, since terms shift often.
- Log every raw API response to disk during development — you'll want it for the eval/calibration step and for debugging non-deterministic debate behavior.

## 14. Tooling Workflow — Antigravity / Codex / Lovable / Google AI Studio

1. **Antigravity or Codex — primary backend build.** Feed this PRD in directly; either is fine for generating the repo skeleton (orchestrator, argument graph, calibration, FastAPI layer) since both have real file-system/repo access and can iterate against your actual codebase. Pick one, don't split the backend across both — that just creates merge headaches.
2. **Lovable — frontend shell.** Once §9's API contract is stable, feed Lovable that plus §5h's component list. Strong at fast, polished UI from a spec; weak at the actual AI logic, so keep it off the backend.
3. **Google AI Studio — worth reconsidering.** Google shipped GitHub bi-directional sync to AI Studio's Build mode in mid-to-late August 2026 (previously it was export-only, hence the copy-paste friction you remember). Now you can import the repo Antigravity/Codex built, iterate visually with Gemini's UI-generation strengths, and push straight back to the same repo. Good fit for: fast visual iteration on the argument-graph viz, or as a prompt-behavior sandbox before wiring prompts into your real agent code. Not a great fit for the core Python backend logic — it's optimized for React/Next.js/web-stack projects, and the argument-semantics/calibration math wants a real IDE with a debugger, not a chat-driven builder.

**Suggested order:** Antigravity/Codex for backend skeleton → stabilize the API contract → Lovable for frontend shell → optionally pull into AI Studio via GitHub for visual polish on the graph viz → back to Antigravity/Codex for final integration + eval script.

---

# Appendix A — Amendments (2026-09-20)

The sections above are the original specification and are left unchanged as a
record. Where the implementation now deviates, this appendix is authoritative.
Rationale and evidence:
`docs/superpowers/specs/2026-09-20-argus-evidence-grounded-redesign.md`.

## A.1 Why these amendments exist

The first complete FEVER run (n=50, 2026-09-15) lost to the single-LLM baseline
on accuracy (0.620 vs 0.860) and ECE (0.289 vs 0.136). A paired McNemar test
added later gives **p = 0.0018**, so that loss was real rather than small-sample
noise.

The cause was not tuning. Across 57 of 58 cached debates the grounded extension
was **skeptic 2, advocate 0** — identical every time, because a strictly
alternating one-argument-per-turn debate always produces the same attack chain,
whose grounded extension depends only on its length. The structural signal was a
constant −2 on the logit and carried no information. Separately, §5d's symbolic
fact-checker had never been built; the module asked the same model that generated
the arguments whether they were true. **M3 was decorative and M4 was absent.**

## A.2 §5a Debate protocol — multi-argument turns

A turn may put forward up to **3** arguments (hard cap 12 per debate), each
attacking **any number** of the opposing side's earlier arguments rather than
implicitly the previous one. Self-attacks, forward references and same-side
attacks are rejected.

*Rationale:* free targeting is what allows the attack graph to be anything other
than a path. LLM call count is unchanged, so there is no quota cost.

*Known limit, stated rather than claimed away:* this makes non-degenerate graphs
reachable, not guaranteed. Whoever speaks last is still never attacked and so
always survives. A.4's evidence weighting removes that bias's effect on the
verdict, but not its presence in the graph.

## A.3 §5c/§5d coupling — evidence-gated attack edges

The original design treats the argumentation engine and the fact-checker as
independent inputs to the judge. They are now chained: an asserted attack becomes
an edge in the argumentation framework **only if the attacking argument is
supported by retrieved evidence** (threshold `tau`, default 0.0 as a floor).

Rejected attacks are recorded as `asserted_unsupported` and shown in the trace.

*Rationale:* this is what makes M3 load-bearing. Without it the graph records who
said what, and its extension is decided by turn order rather than by whether
anything said was true.

## A.4 §5e Judge — evidence-weighted structural term

The structural signal was `len(advocate survivors) - len(skeptic survivors)`. It
is now those survivors weighted by their evidence support:

    structural = ( sum support(advocate survivors) - sum support(skeptic survivors) )
                 / (number of survivors)

bounded in [-1, 1].

*Rationale:* the old term was unbounded while the other two signals sat in
[-1, 1], so one extra survivor swung the logit by a full e-fold; and a survivor
that survived only by speaking last received full credit. An argument with no
evidence behind it now contributes zero.

*Note the denominator.* The design document originally divided by total support
*magnitude*. A failing test showed that makes the term purely relative — a lone
survivor backed by support 0.01 would score a full ±1.0, reproducing the exact
"maximal signal from nothing" failure being fixed. Survivor count is used
instead.

**Ablation evidence** (`scripts/rescore.py --ablations`, n=10): reverting only
this term to the unweighted count drops accuracy to 0.500, AUROC to 0.240 and
mean P(true) to 0.083 — reproducing the original defect on demand.

## A.5 §5e — the three signals are no longer independent

§5e assumes three independent signals. The structural and fact-check terms now
both read evidence, so they are correlated. They remain distinct (one is "what
survived, weighted by evidence", the other "evidence balance across all
arguments, including those that died"), all three are retained because M5 asks
for three, and the weight sweep is reported as a sensitivity analysis.

**Open issue (unresolved, tracked in `docs/PLAN.md`).** The fact-check term
measures whether an argument's assertion is *true*, not whether it *supports the
claim*. Observed in a real debate: the Advocate argued "the release year is 1980
rather than 2007, making the claim false" — conceding. That statement is true,
scored +1.00, and the fact-check term credited it to the Advocate, pushing P
toward true on a false claim. To be resolved by the `structural only` and
`no structural term` ablations rather than by guesswork.

## A.6 §5d — the LLM parses, the rules judge

§5d is now implemented as specified (BM25 retrieval + triples + forward
chaining), with the LLM's role narrowed to **triple extraction only**. It is
never asked to rate or judge. Forward chaining derives inverse and symmetric
predicates to a fixpoint before matching, so facts not literally present in the
evidence can still be used.

Retrieval runs over a pooled corpus of 3,493 FEVER gold-evidence sentences drawn
from 6,506 claims — far more than are scored — so a claim's evidence sits among
realistic distractors. Measured **recall@5 = 0.836** on the held-out 50.

**Honest limitations, reported as results rather than hidden:**

- This is retrieval over a pooled gold-evidence corpus, **not** open-domain
  retrieval over Wikipedia.
- Strict triple matching has poor recall on natural language. The module
  **abstains** (`no_symbolic_match`) rather than guessing, and **symbolic
  coverage** — the fraction of arguments the rules could decide — is reported as
  a first-class metric.
- The functional-predicate list is curated by hand. Inferring functionality from
  data is a research problem of its own, and a wrong entry manufactures false
  contradictions, which is this module's worst failure mode.

## A.7 Evaluation additions

- Metrics extended with AUROC, Brier, a threshold sweep and **McNemar's exact
  paired test**. At n=50 an unpaired CI is roughly ±0.13 and establishes nothing;
  both systems score the same claims, so the paired test is the meaningful one.
- The evaluation cache stores the **full debate artifact** — arguments, edges,
  retrieved evidence, extracted triples, rules fired, and both the symbolic and
  the legacy LLM fact-check scores. Everything downstream of the LLM re-scores
  offline in seconds via `scripts/rescore.py`, which has no network path.
- A six-configuration **ablation table** isolates each component's contribution.
- The seed-42 n=50 set is held out permanently; the calibrator is fitted on a
  disjoint draw, with zero claim-text overlap asserted in code and in a test.

## A.8 Deferred

- **M6 debate-strategy planner.** Out of scope, unchanged.
