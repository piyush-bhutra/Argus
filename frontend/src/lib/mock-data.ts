import type { DebateGraph, Transcript, Verdict } from "./types";

export const MOCK_DEBATE_ID = "demo-debate";

export const MOCK_CLAIM =
  "Large language models can reliably verify factual claims without external retrieval.";

export const mockTranscript: Transcript = {
  status: "complete",
  arguments: [
    {
      id: "a1",
      agent: "advocate",
      round: 1,
      text: "Frontier models encode a broad slice of encyclopedic knowledge during pretraining, and closed-book QA benchmarks such as Natural Questions show accuracy competitive with retrieval-augmented pipelines on head entities.",
      attacks: [],
      self_confidence: 0.78,
    },
    {
      id: "s1",
      agent: "skeptic",
      round: 1,
      text: "Closed-book accuracy collapses on tail entities and on any fact postdating the training cutoff. A verifier that silently fails on the long tail is not 'reliable' in the sense the claim requires.",
      attacks: ["a1"],
      self_confidence: 0.86,
    },
    {
      id: "a2",
      agent: "advocate",
      round: 2,
      text: "Reliability can be recovered through calibration rather than retrieval: when a model abstains below a confidence threshold, selective accuracy on the answered subset exceeds 95% in several published evaluations.",
      attacks: ["s1"],
      self_confidence: 0.64,
    },
    {
      id: "s2",
      agent: "skeptic",
      round: 2,
      text: "Selective accuracy is measured after abstention, so it hides coverage loss. Reported abstention rates on tail claims reach 40%, which reframes the system as a partial verifier, not a reliable one.",
      attacks: ["a2"],
      self_confidence: 0.81,
    },
    {
      id: "a3",
      agent: "advocate",
      round: 3,
      text: "Even a partial verifier is decision-useful, and self-consistency sampling recovers a meaningful share of the abstained cases without touching an external index.",
      attacks: ["s2"],
      self_confidence: 0.52,
    },
    {
      id: "s3",
      agent: "skeptic",
      round: 3,
      text: "Self-consistency amplifies confidently-wrong priors: agreement across samples correlates with fluency, not truth, so it cannot separate a memorized fact from a plausible fabrication.",
      attacks: ["a3"],
      self_confidence: 0.88,
    },
  ],
};

export const mockGraph: DebateGraph = {
  nodes: mockTranscript.arguments.map((a) => ({
    id: a.id,
    agent: a.agent,
    round: a.round,
    label: a.id.toUpperCase(),
  })),
  edges: mockTranscript.arguments.flatMap((a) =>
    a.attacks.map((target) => ({ source: a.id, target })),
  ),
};

export const mockVerdict: Verdict = {
  claim: MOCK_CLAIM,
  raw_probability: 0.41,
  calibrated_probability: 0.27,
  grounded_extension: {
    advocate: [],
    skeptic: ["s3", "s1"],
  },
  explanation:
    "The grounded extension retains only the skeptic's unattacked arguments. The advocate's line of defence (a2, a3) is defeated at every round, and the surviving objections target the two load-bearing assumptions of the claim: coverage on tail facts and the truth-correlation of self-consistency. The raw model score of 0.41 is adjusted downward to 0.27 after calibration, reflecting the model's historical over-confidence on claims whose grounded extension is dominated by a single agent.",
};
