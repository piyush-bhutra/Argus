# Review 1 — Demo Script & Talking Points

## Problem statement

Single-model fact verification is **opaque and poorly calibrated** — LLMs are frequently
confidently wrong on false claims, and a single answer gives you no way to see *why*.

This project asks: does **structured adversarial debate + formal argumentation semantics +
calibrated aggregation** produce a better-calibrated, fully explainable truth judgment than
one LLM call?

Two LLM agents argue opposite sides of a claim across rounds. Their arguments form an
**attack graph**; a formal semantics engine computes which arguments survive scrutiny; a
fact-check pass and a Bayesian judge combine that structural signal with evidence and the
agents' own confidence into a single **P(claim is true)** — with the full transcript, graph,
and math exposed.

## Why this project (for the "not basic algo optimization" framing)

It spans most of the syllabus as **one coherent system**, not an isolated algorithm:

| Module | In this system |
|---|---|
| M1 Agents | Advocate / Skeptic / Judge, each a distinct agent with a percept–action loop |
| M2 Search (adversarial) | Argument-graph evaluation is minimax-style attack/defense depth |
| M3 Knowledge Representation | Dung's Abstract Argumentation Framework (arguments = nodes, attacks = edges) |
| M4 Reasoning | Fact-check pass testing each argument's core factual assertion |
| M5 Uncertainty | Bayesian pooling of structural + fact-check + confidence signals |
| M7 Learning | Isotonic calibration model (math implemented; trained on FEVER labels in Review 2) |

## What's built and working now

- **Debate orchestrator** — runs N rounds of Advocate vs Skeptic against the LLM
  (Google Gemini), parses structured argument objects, handles malformed output, early
  concession. *4 unit tests.*
- **Argument semantics engine** — Dung's AF grounded extension via the standard fixpoint
  IN/OUT/UNDEC labeling. Real, gradable CS, not an LLM wrapper. *3 unit tests over
  reinstatement, cycles, simple defeat.*
- **Bayesian judge + calibration** — sigmoid over (surviving-argument margin) +
  (fact-check margin) + (confidence margin); isotonic regression for calibration.
  *5 unit tests.*
- **Fact-checker** — one batched LLM call scoring each argument's assertion in [−1, 1],
  neutral fallback on failure. *4 unit tests.*
- **Pipeline + FastAPI** — all four endpoints wired to real data, in-memory debate store,
  background execution with polling. *End-to-end API smoke test + 5 pipeline tests.*
- **React dashboard** — claim input, live transcript, force-directed attack graph with
  surviving arguments highlighted, verdict gauge + explanation.
- **30 tests, 0 skipped.**

## What's next (Review 2)

FEVER dataset integration · BM25 retrieval + symbolic triple KB + forward chaining ·
train the calibrator on real labels · evaluation: accuracy + ECE vs a single-LLM baseline,
reliability diagrams · the headline sentence: *"the calibrated debate system has X% lower
ECE than a single-model baseline on N held-out claims."*

## Live demo — 5 steps

1. **Start the backend:** `uvicorn app.main:app --reload` (loads 3 cached demo debates).
2. **Start the frontend:** `cd frontend && npm run dev`, open the local URL.
3. **Show a debate.** Either:
   - *Cached (instant):* click a "cached debate" link on the landing page, or
   - *Live:* type a claim, Start Debate, watch the header go `live · polling → complete`
     (~50 s for 2 rounds).
   > If the LLM provider is down or rate-limited, use the cached debates — they need no API.
4. **Walk the transcript tab** — each round, who attacked whom, self-reported confidence.
5. **Walk the graph tab** — circles = advocate, squares = skeptic, arrows = attacks,
   dashed ring = survived the grounded extension. Then the **verdict tab** — raw vs
   calibrated probability, which arguments survived per side, and the generated explanation.

## Questions to be ready for

- **Grounded extension by hand:** start all UNDEC; an argument goes IN when *every* attacker
  is OUT (so unattacked args are IN); it goes OUT when *any* attacker is IN; iterate to a
  fixpoint; anything still UNDEC sits in an unresolved cycle. Walk `demo-sea-level`:
  arg_5 (unattacked) → IN, so arg_4 → OUT, so arg_3 → IN, so arg_2 → OUT, so arg_1 → IN.
- **The judge math:** `P = sigmoid(1.0·Δsurvivors + 1.0·Δfactcheck + 0.5·Δconfidence)`,
  where each Δ is advocate-minus-skeptic. Zero signal → sigmoid(0) = 0.5.
- **Calibration:** isotonic regression fits a monotonic step function from raw scores to
  observed truth frequencies on held-out data — corrects systematic over/under-confidence
  without assuming a parametric shape. Not yet trained (no labels wired) → calibrated = raw.
- **Why debate helps:** the structural signal (which arguments survive) is independent of
  how confident either model *sounds*, so it catches confidently-wrong claims a single call
  would pass through.
