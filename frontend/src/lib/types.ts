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

export interface Verdict {
  claim: string;
  raw_probability: number;
  calibrated_probability: number;
  grounded_extension: {
    advocate: string[];
    skeptic: string[];
  };
  explanation: string;
}
