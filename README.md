# Argus: Formal Argumentation and Bayesian Logical Evaluation (FABLE)

A multi-agent debate system for verified claims. This repository contains both the FastAPI backend and the React (TanStack Start) frontend.

## Project Structure

The project is separated into backend and frontend as per the PRD requirements:

- `app/`: FastAPI backend implementation of the debate system, APIs, and models.
- `frontend/`: React dashboard (Vite + TanStack Start + Tailwind) for visualization.
- `tests/`: Testing scaffolding for the backend.

## Setup Instructions

### Backend (FastAPI)

1. Navigate to the root directory and install dependencies:
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

### Frontend (React Dashboard)

The frontend connects to the FastAPI backend running at `http://localhost:8000` by default.

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies (Node.js and npm required):
   ```bash
   npm install
   ```
3. Run the development server:
   ```bash
   npm run dev
   ```

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
| `frontend/` | §5h Frontend | React dashboard for transcript, graph viz, verdict. |
| `tests/` | §12 Mitigations | Scaffolding for unit tests on semantics & calibration. |

