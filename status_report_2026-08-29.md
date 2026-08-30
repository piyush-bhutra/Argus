# Argus FABLE Repository Status Report

## 1. PRD-to-Code Mapping

Based on the source code and documentation:

*   **§5a Debate Orchestrator:** **Implemented** (`app/services/orchestrator.py`). Manages debate rounds, agent turns, and JSON response parsing.
*   **§5b Advocate/Skeptic Agents:** **Partially Implemented** (`app/services/orchestrator.py`, `app/services/grok_client.py`). The prompts for the agents are defined in the orchestrator, and it uses a functional LLM client, but there are no distinct agent classes or advanced agentic behaviors beyond basic prompting.
*   **§5c Argument Semantics Engine:** **Implemented** (`app/services/semantics_engine.py`). Computes the grounded extension of an Abstract Argumentation Framework (Dung's AF) using a fixpoint algorithm.
*   **§5d Fact-Checking / KB Chaining:** **Stub Only** (`app/services/fact_checker.py`). The `check_argument` function simply returns a dummy `FactCheckResult` with hardcoded scores and evidence.
*   **§5e Bayesian Judge + Calibration:** **Implemented** (`app/services/judge.py`). Contains logic for isotonic regression calibration (`fit_calibrator`, `apply_calibration`) and sigmoid-based probability computation (`compute_raw_probability`).
*   **§5f Transcript Layer:** **Partially Implemented** (`app/models/schemas.py`). The data models (like `Argument` and lists of arguments) exist, but there is no persistent storage or database implementation.
*   **§5g API Layer:** **Stub Only** (`app/api/routes.py`). All FastAPI endpoints (`/debate/start`, `/debate/{id}/transcript`, `/debate/{id}/verdict`, `/debate/{id}/graph`) return hardcoded JSON responses.
*   **§5h Frontend:** **Partially Implemented** (`frontend/`). A React/TanStack Start dashboard exists and renders visualizations. It makes actual `fetch` calls to the local API backend (`http://localhost:8000`), but since the backend routes are stubs, it currently only renders mock data. It also contains a fallback to purely local mock data if the backend is unreachable.

## 2. Test Coverage Summary

Running `python -m pytest -v` yielded **15 passed, 1 skipped** out of 16 tests.

*   `tests/test_calibration.py` (0 pass, 1 skipped):
    *   `test_calibration_math` verifies the calibration step (raw probability in, calibrated probability out), but is explicitly marked `@pytest.mark.skip`.
*   `tests/test_grok_client.py` (5 pass):
    *   Verifies the Grok API client behavior: raises error if settings are empty, returns content on successful call, passes correct arguments to the API, raises appropriate `OpenAIError` exceptions, and correctly retries on 429 Rate Limit errors.
*   `tests/test_judge.py` (3 pass):
    *   Verifies `compute_raw_probability` works correctly on a worked example and with zero signal.
    *   Verifies that the isotonic regression calibration maintains monotonicity and bounds (0.0 to 1.0).
*   `tests/test_orchestrator.py` (4 pass):
    *   Verifies `run_debate` on a normal debate transcript, handles malformed JSON recovery, correctly treats exhausted retries as a concession, and successfully terminates early when both agents concede.
*   `tests/test_semantics.py` (3 pass):
    *   Verifies grounded-extension labeling on 3 hand-constructed argument graphs: reinstatement, cycle, and simple defeat.

## 3. Architecture As-Built

The actual data flow when `run_debate(claim, rounds)` is called in `orchestrator.py` is as follows:

1.  **Initialization:** An empty `transcript` list is created.
2.  **Round Loop:** The system iterates for `rounds`. Inside each round, it alternates turns between `"advocate"` and `"skeptic"`.
3.  **Prompt Generation:** For each turn, it builds a system prompt (assigning the role) and a user prompt (containing the claim and the transcript so far).
4.  **LLM Call:** It calls `call_grok()`, passing the prompts. It includes a retry loop of up to 3 attempts.
5.  **Parsing:** The LLM's string response is cleaned of markdown formatting and parsed as JSON.
6.  **Argument Extraction:** It checks if the agent chose to `concede`. If not, it extracts the `argument_text`, limits `confidence` to a float between 0.0 and 1.0, and identifies any `attacks_argument_id`. 
7.  **Transcript Update:** A new `Argument` object is appended to the transcript.
8.  **Early Termination Check:** If an agent concedes (or fails 3 parse attempts), the orchestrator checks if the opponent has also conceded, or if the opponent has not made any arguments yet. If either is true, the debate terminates immediately, returning the transcript. 

## 4. Known Limitations / Gaps

*   **Stubs / Mock Data:** 
    *   The API endpoints in `app/api/routes.py` return completely hardcoded placeholder data.
    *   The fact-checker in `app/services/fact_checker.py` returns dummy evidence and hardcoded scores.
*   **Known Bugs:** 
    *   In `orchestrator.py`, if the Advocate concedes or fails to return valid JSON in Round 1 before the Skeptic takes any turn, the orchestrator evaluates `if not opponent_args` (which is true because the Skeptic hasn't argued yet). The debate terminates immediately, and the Skeptic is permanently skipped.
*   **Not Started:**
    *   FEVER dataset integration.
    *   Evaluation pipeline (ECE/baseline comparison).
    *   Frontend-to-real-backend wiring: While the frontend API client (`api.ts`) is configured to hit `http://localhost:8000`, the backend only provides mock data, so true end-to-end wiring is incomplete.

## 5. Solid and Well-Verified Components

*   **Argument Semantics Engine (`app/services/semantics_engine.py`):** The logic for computing Dung's AF grounded extensions (IN, OUT, UNDEC labeling) is fully implemented and backed by verified unit tests covering various graph topologies (cycles, reinstatements, simple defeats).
*   **Bayesian Judge (`app/services/judge.py`):** The core probabilistic evaluation and isotonic regression math is solid. It accurately weights structural signals (surviving arguments), fact-checking signals, and agent confidence, and its bounds and monotonic behavior are well-tested.

## 6. File / Module Inventory

**`app/` (Backend Application)**
*   `main.py`: FastAPI application entry point.
*   `api/routes.py`: API endpoint definitions (Stub Status).
*   `core/config.py`: Environment configuration loading via Pydantic.
*   `core/logger.py`: Application logging configuration.
*   `models/schemas.py`: Pydantic data models for the system.
*   `services/fact_checker.py`: Fact-checking logic (Stub Status).
*   `services/grok_client.py`: Wrapper for the Grok LLM API client.
*   `services/judge.py`: Bayesian probability and calibration math logic.
*   `services/orchestrator.py`: Debate round management and agent prompting.
*   `services/semantics_engine.py`: Grounded extension and graph labeling algorithms.

**`tests/` (Test Suite)**
*   `test_calibration.py`: Tests for the calibration mathematical step (Currently skipped).
*   `test_grok_client.py`: Verifies error handling, retries, and formatting of the API client.
*   `test_judge.py`: Verifies Bayesian probability scores and calibration monotonicity.
*   `test_orchestrator.py`: Verifies debate logic, transcript building, and early termination.
*   `test_semantics.py`: Verifies mathematical correctness of argument graph evaluations.
