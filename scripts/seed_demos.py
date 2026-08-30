"""
Pre-generate cached demo debates so the Review-1 demo never waits on the
Cerebras 5 req/min free-tier limit.

Run once locally with a valid LLM_API_KEY / LLM_MODEL in .env:

    python -m scripts.seed_demos

Writes data/demo_debates.json (committed to the repo). app.main loads it at
startup via debate_store.load_demos(); the ids below then resolve instantly with
status "complete".
"""
import json
import time
from pathlib import Path

from app.services.debate_store import DebateRecord
from app.services.pipeline import assemble_verdict, build_graph
from app.services.orchestrator import run_debate

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "demo_debates.json"

DEMOS = [
    ("demo-sea-level", "Global sea level rise has accelerated over the past three decades."),
    ("demo-rust-memory", "Rust eliminates all classes of memory-safety bugs in production systems."),
    ("demo-llm-verify", "Large language models can reliably verify factual claims without external retrieval."),
]

ROUNDS = 2


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    records = []

    for debate_id, claim in DEMOS:
        print(f"[{debate_id}] running debate: {claim}")
        transcript = run_debate(claim, ROUNDS)
        verdict = assemble_verdict(claim, transcript, calibrator=None)
        graph = build_graph(transcript)

        record = DebateRecord(
            debate_id=debate_id,
            claim=claim,
            rounds=ROUNDS,
            status="complete",
            transcript=transcript,
            verdict=verdict,
            graph=graph,
        )
        records.append(json.loads(record.model_dump_json()))
        print(
            f"    -> {len(transcript)} arguments, "
            f"P(true)={verdict.calibrated_probability:.2f}"
        )
        time.sleep(15)  # stay under 5 req/min between debates

    OUT.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"\nWrote {len(records)} demo debate(s) to {OUT}")


if __name__ == "__main__":
    main()
