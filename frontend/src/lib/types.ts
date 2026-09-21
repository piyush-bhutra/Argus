export type AgentRole = "advocate" | "skeptic";

export interface Argument {
  id: string;
  agent: AgentRole;
  round: number;
  text: string;
  attacks: string[];
  self_confidence: number;
}

export interface Transcript {
  arguments: Argument[];
  status: "in_progress" | "complete";
  rounds: number;
}

export interface GraphNode {
  id: string;
  agent: AgentRole;
  round: number;
  label?: string;
}

export interface GraphEdge {
  source: string;
  target: string;
}

export interface DebateGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

/** What the symbolic rules concluded about one argument, and why. */
export interface FactCheck {
  argument_id: string;
  /** -1 contradicted by evidence, 0 undecided, +1 supported. */
  support_score: number;
  /** "symbolic" = the rules decided it; "none" = they abstained. */
  method: "symbolic" | "none";
  /** Which rules fired, e.g. "entailment", "functional_contradiction". */
  rules_fired: string[];
  evidence_ids: string[];
  evidence_sentences: string[];
  /** Extracted facts, "subject | predicate | object". */
  triples: string[];
}

export interface Verdict {
  claim: string;
  raw_probability: number;
  calibrated_probability: number;
  grounded_extension: {
    advocate: string[];
    skeptic: string[];
  };
  explanation: string;
  /**
   * Attacks an agent asserted but could not back with evidence, so they never
   * entered the argumentation framework. Shown rather than hidden — "attacked
   * but had nothing behind it" is part of the audit trail.
   */
  dropped_edges?: [string, string][];
  /** Fraction of arguments the symbolic rules could decide. The rest abstained. */
  symbolic_coverage?: number | null;
  /**
   * The three signals the judge combined, each in [-1, 1], positive favouring
   * the claim. Rendered as the graded "subjects" of the report card — shown only
   * a final probability, a reader cannot tell whether it came from the argument
   * graph, the evidence, or how confident the agents merely sounded.
   */
  signals?: { structural: number; factcheck: number; confidence: number };
  /** Weights those signals were combined with, so the arithmetic can be checked. */
  signal_weights?: { structural: number; factcheck: number; confidence: number };
  fact_checks?: FactCheck[];
}
