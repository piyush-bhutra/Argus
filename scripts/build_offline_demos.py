"""
Build data/demo_debates.json from hand-authored transcripts WITHOUT any LLM calls.

This gives the dashboard a guaranteed-working set of cached debates even if the
Cerebras API is unavailable on demo day. `scripts/seed_demos.py` regenerates the
same file from real live debates when you have API budget.

    python -m scripts.build_offline_demos
"""
import json
from pathlib import Path

from app.models.schemas import Argument, FactCheckResult
from app.services.debate_store import DebateRecord
from app.services.pipeline import assemble_verdict, build_graph

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "demo_debates.json"


def A(id, agent, rnd, text, attacks, conf):
    return Argument(id=id, agent=agent, round=rnd, text=text, attacks=attacks, self_confidence=conf)


DEMOS = [
    {
        "debate_id": "demo-sea-level",
        "claim": "Global sea level rise has accelerated over the past three decades.",
        "transcript": [
            A("arg_1", "advocate", 1,
              "Satellite altimetry since 1993 shows the rate of global mean sea-level rise increasing from about 2.1 mm/yr in the 1990s to over 4 mm/yr in the last decade.",
              [], 0.86),
            A("arg_2", "skeptic", 1,
              "Tide-gauge records span a century and contain multi-decadal swings; a 30-year window can mistake a natural oscillation for a genuine acceleration.",
              ["arg_1"], 0.55),
            A("arg_3", "advocate", 2,
              "The satellite acceleration is corroborated by independent estimates of ice-sheet mass loss from GRACE gravimetry and by ocean-heat-content-driven thermal expansion, which are not subject to tide-gauge sampling issues.",
              ["arg_2"], 0.8),
            A("arg_4", "skeptic", 2,
              "Instrument drift corrections applied to the early satellite record are themselves what produce part of the acceleration signal, so the trend is partly a processing artifact.",
              ["arg_3"], 0.42),
            A("arg_5", "advocate", 2,
              "The drift corrections were validated against independent tide-gauge and GPS-located reference stations, and reanalyses that omit the disputed early period still find a statistically significant acceleration.",
              ["arg_4"], 0.81),
        ],
    },
    {
        "debate_id": "demo-rust-memory",
        "claim": "Rust eliminates all classes of memory-safety bugs in production systems.",
        "transcript": [
            A("arg_1", "advocate", 1,
              "Rust's ownership and borrow checker statically prevent use-after-free, double-free, and data races in safe code, which covers the large majority of memory-safety CVEs seen in C and C++.",
              [], 0.7),
            A("arg_2", "skeptic", 1,
              "The claim says 'all classes'. Rust permits `unsafe` blocks, and real production crates (and the standard library) use them; memory-safety bugs have shipped in that unsafe code.",
              ["arg_1"], 0.9),
            A("arg_3", "advocate", 2,
              "`unsafe` is opt-in and auditable, so in practice the safe subset still eliminates these bugs for almost all application code.",
              ["arg_2"], 0.55),
            A("arg_4", "skeptic", 2,
              "'In practice for almost all code' is a weaker claim than 'eliminates all classes'. Leaks, and safe-code logic errors that corrupt state, also remain possible.",
              ["arg_3"], 0.83),
        ],
    },
    {
        "debate_id": "demo-llm-verify",
        "claim": "Large language models can reliably verify factual claims without external retrieval.",
        "transcript": [
            A("arg_1", "advocate", 1,
              "Frontier models encode a broad slice of encyclopedic knowledge during pretraining and score competitively with retrieval pipelines on closed-book QA for common entities.",
              [], 0.62),
            A("arg_2", "skeptic", 1,
              "Closed-book accuracy collapses on rare entities and on anything after the training cutoff; a verifier that silently fails on the long tail is not 'reliable'.",
              ["arg_1"], 0.85),
            A("arg_3", "advocate", 2,
              "Reliability can be recovered by calibration: if the model abstains below a confidence threshold, accuracy on the answered subset is very high.",
              ["arg_2"], 0.5),
            A("arg_4", "skeptic", 2,
              "Selective accuracy hides coverage loss; reported abstention on tail claims reaches 40%, which makes the system a partial verifier, not a reliable one.",
              ["arg_3"], 0.82),
        ],
    },
]


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for demo in DEMOS:
        transcript = demo["transcript"]
        # Neutral fact-check scores (no LLM) so the graph + judge signal is
        # driven purely by the grounded extension and agent confidence.
        neutral = [
            FactCheckResult(argument_id=a.id, evidence_sentences=[], support_score=0.0)
            for a in transcript
        ]
        verdict = assemble_verdict(
            demo["claim"], transcript, calibrator=None, fact_results=neutral
        )
        record = DebateRecord(
            debate_id=demo["debate_id"],
            claim=demo["claim"],
            rounds=2,
            status="complete",
            transcript=transcript,
            verdict=verdict,
            graph=build_graph(transcript),
        )
        records.append(json.loads(record.model_dump_json()))
        print(f"{demo['debate_id']}: P(true)={verdict.calibrated_probability:.2f} "
              f"grounded={verdict.grounded_extension}")

    OUT.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"\nWrote {len(records)} demo debate(s) to {OUT}")


if __name__ == "__main__":
    main()
