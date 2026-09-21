from pydantic import BaseModel, Field
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
    # Per-argument evidence, extracted triples and the rules that fired. Shipped
    # with the verdict because the auditable trace is the claim the whole system
    # rests on, and a score a reader cannot follow back to a source sentence is
    # an assertion rather than evidence.
    fact_checks: List[FactCheckResult] = []
    # The three signals the judge combined, each in [-1, 1], positive favouring
    # the claim. Reported rather than just summed: shown only a final
    # probability, a reader cannot tell whether it came from the argument graph,
    # from the evidence, or from how confident the agents merely sounded.
    signals: Dict[str, float] = {}
    # The weights those signals were combined with, so the arithmetic on screen
    # can be checked against the number.
    signal_weights: Dict[str, float] = {}

# A claim is one sentence to verify, not a document. The cap matters because the
# claim is embedded in EVERY prompt of the debate — roughly six LLM calls — so an
# unbounded claim is a token-cost amplifier aimed at the operator's quota. A
# 1 MB claim was accepted before this limit existed.
MAX_CLAIM_LENGTH = 1000


class StartDebateRequest(BaseModel):
    claim: str = Field(min_length=1, max_length=MAX_CLAIM_LENGTH)
    # Bounded here as well as in the route: the route's clamp is what actually
    # runs today, but a second entry point must not be able to skip it.
    rounds: int = Field(default=3, ge=1, le=5)

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
