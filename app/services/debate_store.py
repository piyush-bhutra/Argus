"""
In-memory debate persistence.

Scope decision (see PROJECT_STATE §5): for the Review-1 demo, debate state lives
in a process-local dict keyed by ``debate_id``. No database. State is lost on
restart, except for the pre-cached demo debates loaded from
``data/demo_debates.json`` at startup.
"""
import json
import uuid
from pathlib import Path
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.core.logger import logger
from app.models.schemas import Argument, GraphResponse, Verdict

Status = Literal["in_progress", "complete", "error"]

_DEMO_FILE = Path(__file__).resolve().parents[2] / "data" / "demo_debates.json"


class DebateRecord(BaseModel):
    debate_id: str
    claim: str
    rounds: int = 2
    status: Status = "in_progress"
    transcript: List[Argument] = Field(default_factory=list)
    verdict: Optional[Verdict] = None
    graph: Optional[GraphResponse] = None
    error: Optional[str] = None


_store: Dict[str, DebateRecord] = {}


def create(claim: str, rounds: int = 2) -> str:
    debate_id = f"debate-{uuid.uuid4().hex[:12]}"
    _store[debate_id] = DebateRecord(debate_id=debate_id, claim=claim, rounds=rounds)
    return debate_id


def get(debate_id: str) -> Optional[DebateRecord]:
    return _store.get(debate_id)


def set_transcript(debate_id: str, transcript: List[Argument]) -> None:
    record = _store.get(debate_id)
    if record:
        # Copy: the orchestrator mutates its list in place as the debate streams.
        record.transcript = list(transcript)


def set_result(debate_id: str, verdict: Verdict, graph: GraphResponse) -> None:
    record = _store.get(debate_id)
    if record:
        record.verdict = verdict
        record.graph = graph
        record.status = "complete"


def set_error(debate_id: str, message: str) -> None:
    record = _store.get(debate_id)
    if record:
        record.status = "error"
        record.error = message


def load_demos() -> int:
    """Seed pre-cached demo debates so their ids resolve instantly, no LLM calls."""
    if not _DEMO_FILE.exists():
        logger.info("No demo_debates.json found; skipping demo seed.")
        return 0
    try:
        payload = json.loads(_DEMO_FILE.read_text(encoding="utf-8"))
        count = 0
        for item in payload:
            record = DebateRecord(**item)
            _store[record.debate_id] = record
            count += 1
        logger.info(f"Loaded {count} cached demo debate(s) from {_DEMO_FILE}.")
        return count
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Failed to load demo debates: {e}")
        return 0
