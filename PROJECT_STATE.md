# PROJECT STATE — Multi-Agent Debate System for Verified Claims
*(working name: Verdikt)*

**This is a living document.** It exists so that anyone or any AI picking this project up
mid-build has full context without re-deriving decisions already made. Update it as the
project progresses — don't let it drift out of sync with reality.

**Last updated:** Review-1 wiring session (2026-08-30) — all components wired end-to-end,
orchestrator bug fixed, LLM fact-checker, in-memory persistence, cached demo debates, docs
refreshed. Provider switched Cerebras → Google Gemini (`gemini-3.6-flash`), live debate
verified end-to-end through the API. Earlier automated analysis preserved as
`status_report_2026-08-29.md`.

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
- **Current: Gemini.** Key from aistudio.google.com/apikey. Model `gemini-3.6-flash`
  (`gemini-2.0-flash` is retired — the API returns a 404 pointing at the new id).
  Base URL `https://generativelanguage.googleapis.com/v1beta/openai/` (OpenAI-SDK compatible).
  Free tier is generous (~15 req/min) — live 2-round debate ≈ 50 s, verified end-to-end
  through the API on 2026-08-30.
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
| Frontend | `frontend/` | ✅ Wired to live backend; 2-round default; cached-demo links; "backend offline" chip; typechecks clean | N/A (manual) |
| FEVER dataset | `data/` | ⬜ Review 2 | N/A |
| Evaluation pipeline (ECE, baseline, reliability diagrams) | — | ⬜ Review 2 | N/A |
| Trained calibrator | `data/calibrator.pkl` | ⬜ Review 2 — pipeline loads it if present, else calibrated = raw | N/A |

**Test suite: 30 passed, 0 skipped** (`python -m pytest`).

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
- **Calibrator not trained** — needs labels (FEVER), Review 2. Until then calibrated = raw
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

1. **Build the real fact-checker** — BM25 retrieval + triple extraction + forward chaining
   against FEVER evidence (PRD §5d).
2. **Download + integrate FEVER** — HuggingFace `datasets`, filtered to the eval sample.
3. **Train the calibrator** on a held-out FEVER split → `data/calibrator.pkl`.
4. **Evaluation** — baseline (single LLM call) vs full system: accuracy + ECE + reliability
   diagrams (PRD §11).
5. **Demo/viva prep** — see `DEMO.md`; be ready to hand-run the grounded-extension fixpoint
   and the calibration math.
6. Optionally add the debate-strategy planner for explicit M6 coverage.

---

## 9. Notes for Any AI Picking This Up

- Read this file AND `debate_system_prd.md` before suggesting changes.
- Follow §7 conventions.
- Check §5 before assuming a file is complete.
- Keep §4 and this document current as work progresses.
