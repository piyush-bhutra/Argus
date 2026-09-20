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
    # Provenance: what decided this score, so a verdict can be audited rather
    # than taken on trust. method "none" means the rules could not decide and the
    # argument abstained — counted in the reported symbolic-coverage metric.
    method: Literal["symbolic", "none"] = "none"
    rules_fired: List[str] = []
    evidence_ids: List[str] = []
    # The argument's extracted triples, "subject | predicate | object".
    # Cached so a low coverage rate can be diagnosed from the artifact
    # instead of costing another LLM call to reproduce.
    triples: List[str] = []

class Verdict(BaseModel):
    claim: str
    raw_probability: float
    calibrated_probability: float
    grounded_extension: Dict[str, List[str]]   # side -> surviving argument ids
    explanation: str
    # Attacks the agents asserted but could not back with evidence, so they never
    # entered the argumentation framework. Surfaced rather than dropped silently:
    # "attacked but had nothing behind it" is part of the audit trail.
    dropped_edges: List[List[str]] = []
    # Fraction of arguments the symbolic rules could actually decide. Reported
    # honestly; the rest abstained rather than being guessed at.
    symbolic_coverage: Optional[float] = None

class StartDebateRequest(BaseModel):
    claim: str
    rounds: int = 3

class StartDebateResponse(BaseModel):
    debate_id: str

class TranscriptResponse(BaseModel):
    arguments: List[Argument]
    status: Literal["in_progress", "complete"]
    rounds: int = 2

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
