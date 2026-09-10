# PROJECT STATE — Multi-Agent Debate System for Verified Claims
*(working name: Verdikt)*

**This is a living document.** It exists so that anyone or any AI picking this project up
mid-build has full context without re-deriving decisions already made. Update it as the
project progresses — don't let it drift out of sync with reality.

**Last updated:** First valid evaluation run + branch merge (2026-09-10) — balanced n=50 results in §4; frontend redesign and backend eval work now live together on branch `backend-eval` (pushed to origin). Earlier the same day: measurement fixes — balanced n=50 FEVER sample, stratified `--limit`, config-keyed + corruption-safe eval cache; the n=8 numbers are now marked invalid (§4). 2026-09-09: evaluation harness built. Earlier the same day: FEVER sample integrated (§4, §8). Prior: Review-1 wiring session (2026-08-30) — all components wired end-to-end,
orchestrator bug fixed, LLM fact-checker, in-memory persistence, cached demo debates, docs
refreshed. Provider: Google Gemini `gemini-3.5-flash-lite` (moved off `gemini-3.6-flash`
after hitting its 20 req/day free cap). Retry policy tightened; frontend now shows an honest
"debate failed" banner instead of masking failures as mock data. Live debate verified
end-to-end. Earlier automated analysis preserved as `status_report_2026-08-29.md`.

**Repo location:** `C:\AI-Project`
**Full technical spec:** `debate_system_prd.md` at the project root.
**Review-1 demo script:** `DEMO.md`.

---

## 1. Project Overview

**Context:** Course project for BITE308L (AI theory) + BITE308P (AI Lab). Professor wants a
clear problem statement and dislikes "basic algo optimization" projects — this one spans most
of the syllabus (search, KR, reasoning, uncertainty, learning) as one coherent system. Also
intended as a resume-worthy artifact.

**One-liner:** Two LLM agents (Advocate, Skeptic) debate a factual claim across structured
rounds; a formal argumentation engine, a fact-checker, and a calibrated Bayesian judge
combine to produce a truth-probability verdict with a fully auditable trace.

**Builder:** Solo.

**Syllabus mapping** (full detail in PRD §1): Search (adversarial) → argument-graph eval;
KR → Dung's AF; Reasoning → fact-check pass; Uncertainty → Bayesian aggregation +
calibration; Learning → calibration model. Planning is intentionally thin.

---

## 2. Key Decisions & Rationale (don't re-litigate without reason)

### LLM Provider — Google Gemini (current), Cerebras (fallback)
Journey: xAI Grok (billing wall) → Groq (email-verification block) → Cerebras (free-tier
quota hit HTTP 402 on 2026-08-30) → **Google Gemini (AI Studio)**.
- **Current: Gemini.** Key from aistudio.google.com/apikey. Model **`gemini-3.5-flash-lite`**.
  Base URL `https://generativelanguage.googleapis.com/v1beta/openai/` (OpenAI-SDK compatible).
  Live 2-round debate ≈ 5 calls, verified end-to-end 2026-08-30.
- **Model-id churn / quota trap (learned the hard way):** the *newest* flash models have a
  tiny free **daily** quota — `gemini-3.6-flash` = 20 requests/day (`quotaId:
  GenerateRequestsPerDayPerProjectPerModel-FreeTier`), exhausted after ~4 debates. Use a
  `*-flash-lite` model. Also `gemini-2.0-flash` and `gemini-2.5-flash-lite` return 404
  ("no longer available", pointing at a newer id) — check `GET /v1beta/models` for what's
  live. Quota is **per model**, so switching model = fresh bucket.
- Provider is now fully env-configurable: `LLM_API_KEY` / `LLM_MODEL` / `LLM_BASE_URL`
  (see `app/core/config.py`). Swapping back to Cerebras is a 3-line `.env` change.
- Context cap: keep debates short. **Default debate is 2 rounds, not 3.**
- **Cached demo debates** (`data/demo_debates.json`) still need no API — demo fallback.

### Naming convention
Config fields are provider-agnostic: `llm_api_key`, `llm_model`, `llm_base_url`. `.env` keys:
`LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`, `LOG_DIR`. The client function is still
`call_grok()` for historical reasons — intentional, don't rename without updating call sites.

### Persistence — in-memory (settled)
`debate_id → DebateRecord` in a process-local dict (`app/services/debate_store.py`). No DB.
State is lost on restart except the pre-seeded demo debates. Correct scope for the demo.

### Fact-checker — Grok-based for Review 1 (settled)
One batched LLM call scores each argument's core assertion in [−1, 1], neutral fallback on
failure. The PRD's BM25 + symbolic-triple KB + forward chaining is **Review-2 work**.

### Environment gotchas (Windows — don't re-debug)
- Use `py -3.11 -m venv venv`; the Windows Store Python alias is a stub (caused a
  `pydantic_core` binary mismatch).
- Always `python -m pytest`, not bare `pytest`. `pytest.ini` sets `pythonpath = .`.
- `.pytest_cache` `WinError 5` warnings are cosmetic (OneDrive sync) — ignore.

---

## 3. Architecture (summary — full detail in PRD §4-§5)

```
Advocate Agent (LLM) ─┐
Skeptic Agent (LLM)  ─┴─→ Debate Orchestrator ─→ Argument Graph (Dung's AF) + Grounded Extension
                                                          ↓
                          Fact-Check (LLM, batched)  ─────┤
                                                          ↓
                                    Bayesian Judge + Calibration
                                                          ↓
                        pipeline.py ─→ FastAPI (+ in-memory store) ─→ React frontend
```

---

## 4. Current Implementation Status

| Component | File | Status | Test coverage |
|---|---|---|---|
| Data models, API contracts | `app/models/schemas.py` | ✅ Done; graph node now carries `agent`/`round` to match the frontend | Exercised via API + pipeline tests |
| **Argument Semantics Engine** (Dung's AF, grounded extension) | `app/services/semantics_engine.py` | ✅ Done, verified | 3 tests: reinstatement, cycle, simple defeat |
| **Bayesian Judge + Calibration** | `app/services/judge.py` | ✅ Done, verified | 5 tests (judge + calibration round-trip; previously-skipped test now real) |
| **LLM Client** (env-configurable; Gemini) | `app/services/grok_client.py` | ✅ Done; lazy init, configurable `llm_base_url`, live-verified on Gemini | 5 tests |
| **Debate Orchestrator** | `app/services/orchestrator.py` | ✅ Done; **early-termination bug fixed** (§5) | 5 tests incl. regression for the fixed bug |
| **Fact-Checking** | `app/services/fact_checker.py` | ✅ Grok-based, batched, neutral fallback | 4 tests |
| **Pipeline glue** | `app/services/pipeline.py` | ✅ New — runs debate → semantics → fact-check → judge → Verdict + graph | 5 tests |
| **Debate store** (persistence) | `app/services/debate_store.py` | ✅ New — in-memory + demo loader | via API + pipeline tests |
| **API routes — real data** | `app/api/routes.py` | ✅ **Wired to the real pipeline** (background task + polling); no more hardcoded JSON | End-to-end smoke test (`test_app.py`) |
| CORS middleware | `app/main.py` | ✅ Present (`allow_origins=["*"]`) + lifespan demo seed | N/A |
| **Cached demo debates** | `data/demo_debates.json`, `scripts/build_offline_demos.py`, `scripts/seed_demos.py` | ✅ 3 debates, committed, loaded at startup | Verified through the API |
| Frontend | `frontend/` | ✅ **Redesigned 2026-09-10** in the notebook/paper style: the debate view is one scrolling page with a sticky claim bar and scroll-spy rail (no tabs); the graph uses deterministic round columns, grows live, marks survivors/defeated on verdict, and supports replay; unused shadcn scaffolding and ~40 unused deps removed. Data layer (`api.ts`, `types.ts`, React Query polling) unchanged. Wired to live backend; 2-round default; cached-demo links. **Live streaming:** arguments appear turn-by-turn as the debate runs (orchestrator `on_argument` callback → store → 1.5s poll), with per-turn "<Agent> is forming a rebuttal…" / "Scoring the argument graph…" cues. Distinguishes **backend-offline** (mock + chip) from **debate-failed** (explicit banner, no fake data); typechecks clean | N/A (manual) |
| LLM retry policy | `app/services/grok_client.py` | ✅ SDK internal retries disabled; our loop = 2 short retries; **daily-quota 429s fail fast** instead of blocking ~2 min | 6 tests |
| **FEVER dataset** | `scripts/prepare_fever.py`, `data/fever_sample.json` | ✅ **n=50, exactly 25 SUPPORTED / 25 REFUTED** (seed 42; `--n` for more). Claims de-duplicated, ambiguous ones dropped; if a class runs short both are capped to match, never padded; counts printed on generation. Offline only; **not wired into the live pipeline** | 6 balance tests (`tests/test_prepare_fever.py`) + on-disk shape & balance checks (`tests/test_fever_sample.py`, skip if not generated) |
| **Evaluation harness** (accuracy, ECE, single-LLM baseline, reliability diagrams) | `scripts/evaluate.py`, `scripts/reliability_diagram.py` | ✅ Built — calls the existing services, never the live API; cache keyed per claim **and** per half, each half stamped with its config (see §8 item 4); atomic writes; corrupt file moved aside, corrupt rows re-scored; `--limit` draws a **class-balanced** subset; `--seed` / `--rounds` / `--bins` / `--delay` / `--llm-timeout`; writes `data/eval_results.json` (cache), `data/eval_summary.json` (per-run record incl. the exact scored claims), `data/reliability_*.png` | 5 metric tests (`tests/test_eval_metrics.py`) + 7 cache/resume tests (`tests/test_eval_resume.py`, LLM fully mocked) |
| Trained calibrator | `data/calibrator.pkl` | ⬜ Review 2 — pipeline loads it if present, else calibrated = raw | N/A |

**Test suite: 52 passed, 0 skipped** (`python -m pytest`).

### First valid evaluation run (2026-09-10) — balanced n=50

`python -m scripts.evaluate` on the full 25/25 sample; seed 42, 2 rounds, 10 ECE bins,
`gemini-3.5-flash-lite`, no calibrator (so Argus calibrated = raw).

| System | n scored | Accuracy @0.5 | ECE | mean P(true) |
|---|---|---|---|---|
| **Argus** (debate → grounded extension → fact-check → judge) | 49 (24T / 25F) | **0.633** | **0.283** | 0.233 |
| **Baseline** (one direct LLM call) | 46 (22T / 24F) | **0.848** | **0.150** | 0.502 |

- **The single-LLM baseline beats Argus on both accuracy and calibration.** This is the honest
  "before" number that the fact-checker and calibrator work has to move.
- **The skeptic bias the n=8 run hinted at is confirmed on a balanced set:** Argus's mean
  P(true) is 0.233 on data that is 50% true; the baseline's is 0.502. Argus under-calls true
  claims systematically — the leading suspect is still the judge's structural term (surviving
  arguments favour whoever attacks last, and the Skeptic always speaks last in 2 rounds). A
  monotone bias like this is exactly what the isotonic calibrator should absorb.
- **4 claims have a missing half** (transient per-minute 429s — the run did not abort): Argus is
  missing 1, the baseline 4. Rerunning `python -m scripts.evaluate` fills only those halves from
  the cache (~10 LLM calls) and rewrites the summary.
- **Caveats:** n≈50 is small — each accuracy has a 95% CI of roughly ±0.13 and 10 ECE bins hold
  ~5 claims each, so ECE is noisy. The accuracy gap (0.215) is large relative to that, but no
  paired significance test has been run yet.
- Artifacts: `data/eval_summary.json` (metrics + exact config + per-claim scores) and
  `data/reliability_argus.png` / `data/reliability_baseline.png`, regenerated from this run.

### ~~First evaluation run (2026-09-09) — smoke subset, n=8~~ — ⚠️ INVALID, kept for the record

> **Do not cite these numbers.** The `--limit 8` draw was a plain `random.sample` over the
> balanced file and came out 6 REFUTED / 2 SUPPORTED, so an "always false" system scores well
> for free — which is exactly what Argus nearly is. The sampling was fixed on 2026-09-10
> (stratified `--limit`, n=50 balanced sample). The skeptic-bias *hypothesis* below still
> stands and is what the next real run should test; the accuracy/ECE figures do not.
> The summary and PNGs from this run have since been overwritten by the valid n=50 run above.

`python -m scripts.evaluate --limit 8 --delay 2 --llm-timeout 240`, seed 42, 2 rounds,
10 ECE bins, `gemini-3.5-flash-lite`, no calibrator (so Argus calibrated = raw).

| System | n | Accuracy @0.5 | ECE | mean P(true) |
|---|---|---|---|---|
| **Argus** (debate → grounded extension → fact-check → judge) | 8 | **0.750** | **0.175** | 0.094 |
| **Baseline** (one direct LLM call) | 8 | **1.000** | **0.013** | 0.237 |

**The baseline currently beats Argus.** This is the honest starting number, not a bug in the
harness — read it as the "before" measurement:

- **Argus has a strong skeptic bias.** Mean predicted P(true) is 0.094; it assigns ≤0.15 to
  seven of eight claims. Both of its errors are *true* claims scored as false (0.42 and 0.15);
  it got every false claim right. Suspect the judge's structural term — surviving-argument
  counts favour whoever attacks last, and the Skeptic always speaks last in a 2-round debate.
- **This subset is not balanced.** Seed 42 drew 6 REFUTED / 2 SUPPORTED out of the then
  150-claim sample, so accuracy figures here are dominated by the false claims and the
  baseline's 1.000 is very likely optimistic. n=8 is directional only.
- Both fixes queued below (real fact-checker, trained calibrator) target exactly this. The
  calibrator in particular should absorb a monotone bias like this one.

**Reproduce:** `data/eval_results.json` (per claim) and `data/eval_summary.json` (metrics +
the exact config used) are written by the harness; `data/reliability_argus.png` and
`data/reliability_baseline.png` by `python -m scripts.reliability_diagram`.

---

## 5. Known Bugs / Open Issues

### Bug 1 — Orchestrator early-termination logic — ✅ FIXED (2026-08-30)
**File:** `app/services/orchestrator.py`
**Was:** if the Advocate conceded on its first turn in round 1 (before the Skeptic spoke),
the debate ended and the Skeptic was skipped entirely.
**Fix:** the termination check now never fires in round 1 before the opponent has had a turn
(`opponent_spoke` guard); from round 2 on it fires only on mutual concession in the same
round. Regression test:
`tests/test_orchestrator.py::test_advocate_concedes_turn_one_skeptic_still_speaks`.

### Open issues
- **LLM access — RESOLVED (2026-08-30):** switched to Google Gemini (`gemini-3.6-flash`),
  live debates verified end-to-end. Cerebras key still in `.env` (commented) as a fallback.
- **Planning (M6) coverage** — debate-strategy planner still only floated, not committed.
- **Calibrator not trained** — FEVER labels now exist (`data/fever_sample.json`) and the eval
  harness produces the raw probabilities to fit on; fitting and pickling is still outstanding.
- **Argus loses to the single-LLM baseline on the balanced n=50 run** (§4): accuracy 0.633 vs
  0.848, ECE 0.283 vs 0.150. Skeptic bias confirmed (mean P(true) 0.233 on a 50/50 set). Next:
  train the calibrator (on a split *separate* from the eval claims) and fix the judge's bias.
  The earlier n=8 run is invalid (class-imbalanced draw) and is kept only for the record.
- **Calibrator not applied yet** — until `data/calibrator.pkl` exists, Argus calibrated = raw
  and the verdict explanation says so.

---

## 6. Environment & Setup Reference

```powershell
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
python -m pytest -v

# backend
uvicorn app.main:app --reload
# frontend
cd frontend; npm install; npm run dev
```

`.env` (not committed):
```
LLM_API_KEY=<gemini key>
LLM_MODEL=gemini-3.6-flash
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LOG_DIR=./logs
```

---

## 7. Tooling Workflow & Conventions

1. One-shot, fully-specified prompts to agentic tools.
2. Explain-then-implement (understanding in chat, tool executes).
3. Independent read-only verification after every component.
4. Explicit file scope boundaries per prompt.
5. Credit/quota awareness (Cursor exhausted; Codex ~50 msg/day; Antigravity primary).

---

## 8. Roadmap — Remaining Work (priority order)

Review-1 items 1–8 from the previous roadmap are **done** (orchestrator bug, CORS, pipeline
wiring, in-memory persistence, routes real data, frontend↔backend, end-to-end runs, cached
demos). Remaining:

1. ~~**Download + integrate FEVER**~~ — ✅ done. `python -m scripts.prepare_fever --n 50 --seed 42`
   pulls from `copenlu/fever_gold_evidence` (the canonical `fever` repo is script-based and
   no longer loadable by `datasets>=4`), drops NOTENOUGHINFO, balances the classes, and writes
   `data/fever_sample.json` as `[{claim, label}]` (`label: true` = SUPPORTED). Reproducible via
   `--seed`; falls back to a small built-in claim set if every public source fails.

2. **Build the real fact-checker** — BM25 retrieval + triple extraction + forward chaining
   against FEVER evidence (PRD §5d).
3. **Train the calibrator** on `data/fever_sample.json` → `data/calibrator.pkl`.
4. ~~**Evaluation**~~ — ✅ harness built (PRD §11):

   ```powershell
   python -m scripts.evaluate --limit 10      # smoke run first; resumes if interrupted
   python -m scripts.evaluate                 # full n=50 balanced sample
   python -m scripts.reliability_diagram      # PNGs into data/
   ```

   Runs each claim through the real pipeline (`run_debate` → `assemble_verdict`) and, for
   the same claim, a single direct LLM call as the baseline; reports accuracy @0.5 and ECE
   for both. Every claim is written to `data/eval_results.json` the moment it is scored, at
   **sub-claim granularity** — if the daily quota dies mid-run, rerunning re-scores only the
   half that is actually missing. **A full n=50 run is ~300 LLM calls (≈6 per claim) and, at the
   provider latency observed on 2026-09-09 (~45 s/call), takes several hours** — start it and
   let it resume across quota resets. `--llm-timeout` raises the request timeout for the
   batch run only; `grok_client`'s live 60 s default is deliberately untouched.

   **Cache key.** An entry is unique on *(claim text, half, that half's config)*:
   Argus = `{rounds, llm_model, llm_base_url}`; baseline = `{llm_model, llm_base_url,
   sha256(baseline prompt)[:16]}`. A half is reused only if its score is a valid probability
   in [0,1] **and** its stamp equals the current config; metrics count only halves stamped with
   the current config. Argus caches the **raw** probability and calibrates at read time, so
   training a calibrator never forces debates to re-run. The label is always taken from the
   sample file, never the cache. **Not in the key: code.** Editing the debate / fact-check /
   judge code does not invalidate cached scores — run with `--refresh` after such changes.
5. **Demo/viva prep** — see `DEMO.md`; be ready to hand-run the grounded-extension fixpoint
   and the calibration math.
6. Optionally add the debate-strategy planner for explicit M6 coverage.

---

## 9. Notes for Any AI Picking This Up

- Read this file AND `debate_system_prd.md` before suggesting changes.
- Follow §7 conventions.
- Check §5 before assuming a file is complete.
- Keep §4 and this document current as work progresses.
