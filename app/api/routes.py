from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.models.schemas import (
    GraphResponse,
    StartDebateRequest,
    StartDebateResponse,
    TranscriptResponse,
    Verdict,
)
from app.services import debate_store
from app.services.pipeline import run_pipeline

router = APIRouter()


@router.post("/debate/start", response_model=StartDebateResponse)
def start_debate(request: StartDebateRequest, background_tasks: BackgroundTasks):
    """Start a new debate. The pipeline runs in the background; poll the
    transcript endpoint for progress."""
    claim = request.claim.strip()
    if not claim:
        raise HTTPException(status_code=422, detail="claim must not be empty")

    rounds = max(1, min(request.rounds, 5))
    debate_id = debate_store.create(claim, rounds)
    background_tasks.add_task(run_pipeline, debate_id)
    return StartDebateResponse(debate_id=debate_id)


@router.get("/debate/{debate_id}/transcript", response_model=TranscriptResponse)
def get_transcript(debate_id: str):
    record = debate_store.get(debate_id)
    if record is None:
        raise HTTPException(status_code=404, detail="unknown debate_id")
    if record.status == "error":
        raise HTTPException(
            status_code=500, detail=record.error or "debate pipeline failed"
        )
    status = "complete" if record.status == "complete" else "in_progress"
    return TranscriptResponse(arguments=record.transcript, status=status)


@router.get("/debate/{debate_id}/verdict", response_model=Verdict)
def get_verdict(debate_id: str):
    record = debate_store.get(debate_id)
    if record is None:
        raise HTTPException(status_code=404, detail="unknown debate_id")
    if record.status == "error":
        raise HTTPException(status_code=500, detail=record.error or "pipeline failed")
    if record.verdict is None:
        raise HTTPException(status_code=409, detail="verdict not ready yet")
    return record.verdict


@router.get("/debate/{debate_id}/graph", response_model=GraphResponse)
def get_graph(debate_id: str):
    record = debate_store.get(debate_id)
    if record is None:
        raise HTTPException(status_code=404, detail="unknown debate_id")
    if record.graph is not None:
        return record.graph
    # Graph is derivable from a partial transcript too, so build it on the fly.
    from app.services.pipeline import build_graph

    return build_graph(record.transcript)
