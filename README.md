# Argus: Formal Argumentation and Bayesian Logical Evaluation (FABLE)

A multi-agent debate system for verified claims. This repo contains the FastAPI backend.

## Setup Instructions

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Set up environment variables:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` to include your `XAI_API_KEY`.
3. Run the development server:
   ```bash
   uvicorn app.main:app --reload
   ```
4. Access the API documentation at `http://127.0.0.1:8000/docs`.

## Module Mapping to PRD

| File/Module | PRD Section | Description |
|---|---|---|
| `app/models/schemas.py` | §8 Data Models | Pydantic models for API and data structures. |
| `app/api/routes.py` | §9 API Contracts | FastAPI endpoint definitions. |
| `app/services/orchestrator.py` | §5a Debate Orchestrator | Manages debate rounds. |
| `app/services/grok_client.py` | §5b, §13 Grok API | LLM client stub for agents. |
| `app/services/semantics_engine.py`| §5c Argument Graph | Dung's AF grounded-extension stub. |
| `app/services/fact_checker.py` | §5d Fact-Checking | KB forward-chaining stub. |
| `app/services/judge.py` | §5e Bayesian Judge | Calibration math stub. |
| `tests/` | §12 Mitigations | Scaffolding for unit tests on semantics & calibration. |
