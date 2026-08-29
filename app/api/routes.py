from fastapi import APIRouter
from app.models.schemas import (
    StartDebateRequest, StartDebateResponse, TranscriptResponse, 
    Argument, Verdict, GraphResponse
)

router = APIRouter()

@router.post("/debate/start", response_model=StartDebateResponse)
def start_debate(request: StartDebateRequest):
    """
    Start a new debate for a given claim.
    """
    return StartDebateResponse(debate_id="debate_12345")

@router.get("/debate/{debate_id}/transcript", response_model=TranscriptResponse)
def get_transcript(debate_id: str):
    """
    Get the transcript of a debate.
    """
    return TranscriptResponse(
        arguments=[
            Argument(
                id="arg_1",
                agent="advocate",
                round=1,
                text="The claim is true because of evidence A.",
                attacks=[],
                self_confidence=0.9
            ),
            Argument(
                id="arg_2",
                agent="skeptic",
                round=1,
                text="Evidence A is flawed due to B.",
                attacks=["arg_1"],
                self_confidence=0.85
            )
        ],
        status="complete"
    )

@router.get("/debate/{debate_id}/verdict", response_model=Verdict)
def get_verdict(debate_id: str):
    """
    Get the final verdict for a debate.
    """
    return Verdict(
        claim="The sky is blue.",
        raw_probability=0.75,
        calibrated_probability=0.82,
        grounded_extension={"advocate": ["arg_1"]},
        explanation="The advocate's argument survived the grounded extension and was supported by fact-checking."
    )

@router.get("/debate/{debate_id}/graph", response_model=GraphResponse)
def get_graph(debate_id: str):
    """
    Get the argument graph for a debate.
    """
    return GraphResponse(
        nodes=[
            {"id": "arg_1", "label": "Advocate Arg 1"},
            {"id": "arg_2", "label": "Skeptic Arg 1"}
        ],
        edges=[
            {"source": "arg_2", "target": "arg_1", "label": "attacks"}
        ]
    )
