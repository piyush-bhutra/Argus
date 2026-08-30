# Argus — Multi-Agent Debate System for Verified Claims

*(working name: Verdikt)*

Two LLM agents (Advocate, Skeptic) debate a factual claim across structured rounds. A formal
argumentation engine (Dung's AF grounded extension), an LLM fact-check pass, and a Bayesian
judge combine to produce a truth-probability verdict with a fully auditable trace — instead
of asking one model to just answer.

Course project for **BITE308L (AI theory) + BITE308P (AI Lab)**. See `debate_system_prd.md`
for the full spec, `PROJECT_STATE.md` for current status, and `DEMO.md` for the review script.

## What works today (end-to-end)

`claim → debate orchestrator (LLM) → argument attack graph → grounded extension →
LLM fact-check → Bayesian judge → verdict`, all rendered in the React dashboard.

| Module (syllabus) | Component | File |
|---|---|---|
| M1 Agents | Advocate / Skeptic / Judge with a percept–action loop | `app/services/orchestrator.py` |
| M2 Search (adversarial) | Argument-graph attack/defense evaluation | `app/services/semantics_engine.py` |
| M3 Knowledge Representation | Dung's Abstract Argumentation Framework | `app/services/semantics_engine.py` |
| M4 Reasoning | Fact-check pass over each argument's core assertion | `app/services/fact_checker.py` |
| M5 Uncertainty | Bayesian aggregation of structural + fact-check + confidence signals | `app/services/judge.py` |
| M7 Learning | Isotonic calibration (math built; trained on real labels in Review 2) | `app/services/judge.py` |
| API | FastAPI endpoints + in-memory debate store | `app/api/routes.py`, `app/services/debate_store.py` |
| Pipeline glue | Wires all components together | `app/services/pipeline.py` |
| Frontend | Transcript, attack-graph viz, verdict panel | `frontend/` |

**Deferred to Review 2:** FEVER dataset, BM25 retrieval + symbolic triple KB, calibrator
training, ECE / baseline evaluation, reliability diagrams.

## Setup

### Backend (FastAPI, Python 3.11)

```bash
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env      # then edit .env with a real key
```

`.env` (any OpenAI-SDK-compatible provider — currently Google Gemini):

```
LLM_API_KEY=<your Gemini key>       # aistudio.google.com/apikey
LLM_MODEL=gemini-3.5-flash-lite     # newest flash models have a ~20 req/day free cap; use a *-lite
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
LOG_DIR=./logs
```

Cerebras (`gpt-oss-120b`, base URL `https://api.cerebras.ai/v1`) also works — see
`.env.example`.

Run:

```bash
uvicorn app.main:app --reload
```

API docs at `http://127.0.0.1:8000/docs`.

### Frontend (React + TanStack Start)

```bash
cd frontend
npm install
npm run dev
```

Connects to `http://localhost:8000` by default. If the backend is unreachable it falls back
to bundled mock data and shows a "demo data · backend offline" chip.

## Cached demo debates

A live 2-round debate is ~5 LLM calls and takes ~50 s. Three debates are also pre-computed
and committed to `data/demo_debates.json`, loaded at startup so these ids resolve instantly
with no API calls (useful if the provider is rate-limited or down):

- `demo-sea-level` — sea level rise has accelerated *(advocate wins)*
- `demo-rust-memory` — Rust eliminates all memory-safety bugs *(skeptic wins)*
- `demo-llm-verify` — LLMs can verify facts without retrieval *(skeptic wins)*

Open them from the landing page, or `GET /debate/demo-sea-level/verdict`.

Regenerate them:

```bash
python -m scripts.build_offline_demos   # deterministic, no LLM
python -m scripts.seed_demos            # from real live debates (needs API budget)
```

## Tests

```bash
python -m pytest -v
```

30 tests, 0 skipped — semantics, judge/calibration, LLM client, orchestrator, fact
checker, pipeline, and an end-to-end API smoke test (LLM mocked).
