"""Turn cached eval artifacts into the demo corpus the deployed app serves.

    python -m scripts.export_demos                 # all cached debates
    python -m scripts.export_demos --limit 30      # a balanced subset

Why this exists: a live demo on a free LLM tier returns 429 in front of whoever
is watching. The evaluation run already produces fully traced real debates —
transcripts, attack graphs, retrieved evidence, provenance, verdicts — so the
deployed app browses those instead of depending on an API call. Live debate stays
available as an explicit opt-in.

Never calls the LLM. Re-runs the offline stages only, exactly as
scripts/rescore.py does, so the verdicts shown match the current judge.
"""
import argparse
import json
import re
from pathlib import Path

from app.models.schemas import Argument, GraphResponse, Verdict
from app.services.gating import DEFAULT_TAU, gate_attacks
from app.services.judge import (
    apply_calibration,
    compute_raw_probability,
    compute_signals,
)
from app.services.pipeline import SIGNAL_WEIGHTS, _load_calibrator, build_graph
from app.services.semantics_engine import compute_grounded_extension
from scripts.rescore import _fact_results, load_artifacts

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "demo_debates.json"


def slug(claim: str, taken: set) -> str:
    """Stable, readable, URL-safe id. Demo ids end up in links, so a hash would
    make every shared link opaque."""
    base = re.sub(r"[^a-z0-9]+", "-", claim.lower()).strip("-")[:48].rstrip("-")
    base = f"demo-{base or 'claim'}"
    candidate, n = base, 2
    while candidate in taken:
        candidate, n = f"{base}-{n}", n + 1
    taken.add(candidate)
    return candidate


def to_record(row: dict, taken: set, tau: float = DEFAULT_TAU, calibrator=None) -> dict:
    arguments = [Argument(**a) for a in row["arguments"]]
    facts = _fact_results(row, "symbolic")

    gated, dropped = gate_attacks(arguments, facts, tau=tau)
    grounded = compute_grounded_extension(gated)
    raw = compute_raw_probability(grounded, facts, arguments)
    # Apply the trained calibrator, so a browsed demo shows the same number the
    # live pipeline would produce for that debate. Leaving it at raw made the
    # demo corpus silently disagree with the running system.
    calibrated = apply_calibration(calibrator, raw) if calibrator is not None else raw

    verdict = Verdict(
        claim=row["claim"],
        raw_probability=raw,
        calibrated_probability=calibrated,
        grounded_extension=grounded,
        explanation=(
            f"P(claim true) = {calibrated:.2f}"
            + (f" (raw {raw:.2f}, isotonic-calibrated)" if calibrator is not None else "")
            + ". "
            f"{len(grounded['advocate'])} advocate and {len(grounded['skeptic'])} skeptic "
            f"argument(s) survive the grounded extension; {len(dropped)} asserted attack(s) "
            f"were excluded for lack of supporting evidence."
        ),
        dropped_edges=[[s, t] for s, t in dropped],
        symbolic_coverage=row.get("symbolic_coverage"),
        fact_checks=facts,
        signals=compute_signals(grounded, facts, arguments),
        signal_weights=SIGNAL_WEIGHTS,
    )

    # The graph is built over the GATED arguments so the rendered edges are the
    # ones the verdict was actually computed from.
    graph: GraphResponse = build_graph(gated)

    return {
        "debate_id": slug(row["claim"], taken),
        "claim": row["claim"],
        "rounds": 2,
        "status": "complete",
        "transcript": [a.model_dump() for a in arguments],
        "verdict": verdict.model_dump(),
        "graph": graph.model_dump(),
        # Not part of DebateRecord: extra fields would fail validation at load.
        # The label stays out deliberately - the demo shows what the system
        # concluded, not the answer key.
    }


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--limit", type=int, help="export at most N debates")
    p.add_argument("--tau", type=float, default=DEFAULT_TAU)
    p.add_argument("--out", type=Path, default=OUT)
    p.add_argument("--keep-existing", action="store_true",
                   help="keep the hand-written demo debates already in the file")
    args = p.parse_args(argv)

    rows = load_artifacts()
    if args.limit:
        rows = rows[:args.limit]

    taken, records, kept_claims = set(), [], set()
    if args.keep_existing and args.out.exists():
        existing = json.loads(args.out.read_text(encoding="utf-8"))
        for r in existing:
            taken.add(r["debate_id"])
            kept_claims.add(r["claim"])
            records.append(r)

    # Deduplicated by CLAIM, not by id. Keying on id alone meant a second
    # --keep-existing run re-exported every debate under a "-2" suffix and
    # doubled the corpus.
    fresh = [row for row in rows if row["claim"] not in kept_claims]
    skipped = len(rows) - len(fresh)
    if skipped:
        print(f"skipping {skipped} debate(s) already present in {args.out.name}")

    calibrator = _load_calibrator()
    if calibrator is None:
        print("no data/calibrator.pkl - exporting raw probabilities")
    for row in fresh:
        records.append(to_record(row, taken, args.tau, calibrator))

    args.out.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"wrote {len(records)} demo debate(s) -> {args.out}")
    for r in records[len(records) - len(fresh):]:
        v = r["verdict"]
        print(f"  {r['debate_id']:52} P={v['calibrated_probability']:.2f} "
              f"(raw {v['raw_probability']:.2f}) coverage={v['symbolic_coverage']}")


if __name__ == "__main__":
    main()
