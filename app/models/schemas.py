from pydantic import BaseModel
from typing import Literal, List, Dict, Optional

class Argument(BaseModel):
    id: str
    agent: Literal["advocate", "skeptic"]
    round: int
    text: str
    attacks: List[str]        # ids of arguments this one attacks
    self_confidence: float    # 0-1, raw/uncalibrated

class FactCheckResult(BaseModel):
    argument_id: str
    evidence_sentences: List[str]
    support_score: float      # -1 (contradicts) to 1 (supports)

class Verdict(BaseModel):
    claim: str
    raw_probability: float
    calibrated_probability: float
    grounded_extension: Dict[str, List[str]]   # side -> surviving argument ids
    explanation: str

class StartDebateRequest(BaseModel):
    claim: str
    rounds: int = 3

class StartDebateResponse(BaseModel):
    debate_id: str

class TranscriptResponse(BaseModel):
    arguments: List[Argument]
    status: Literal["in_progress", "complete"]

class GraphNode(BaseModel):
    id: str
    agent: Literal["advocate", "skeptic"]
    round: int
    label: str


class GraphEdge(BaseModel):
    source: str
    target: str


class GraphResponse(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]
