"""Sensitivity analysis over the judge's knobs. NEVER calls the LLM.

    python -m scripts.sweep

Presented as a SENSITIVITY ANALYSIS, not as tuning. The operating point is
chosen on principle - all three signals normalised to [-1,1], equal weight, tau
at the abstention floor - and this sweep exists to show the conclusion does not
balance on that choice. Picking the argmax here would be fitting on the
evaluation set and would invalidate every reported number.

Runs entirely off cached artifacts, so the whole surface costs nothing.
"""
import argparse
import json
from pathlib import Path

import scripts.rescore as rs
from scripts.metrics import accuracy, auroc, brier, ece

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sweep_summary.json"


def evaluate(rows, tau, weights, fact_source="symbolic"):
    scored = [rs.score_row(r, tau, weights, "weighted", fact_source) for r in rows]
    probs = [s["probability"] for s in scored]
    labels = [s["label"] for s in scored]
    return {
        "accuracy": accuracy(probs, labels),
        "ece": ece(probs, labels),
        "auroc": auroc(probs, labels),
        "brier": brier(probs, labels),
    }


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fact-source", choices=("symbolic", "llm"), default="symbolic")
    p.add_argument("--out", type=Path, default=OUT)
    args = p.parse_args(argv)

    rows = rs.load_artifacts()
    print(f"{len(rows)} cached debates, fact source: {args.fact_source}\n")

    report = {"n": len(rows), "fact_source": args.fact_source}

    # --- structural weight ---------------------------------------------------
    print("structural weight (factcheck 1.0, confidence 0.5, tau 0.0)")
    print(f"  {'w':>5} {'acc':>6} {'ECE':>7} {'AUROC':>7} {'Brier':>7}")
    report["structural_weight"] = []
    for w in (0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0):
        m = evaluate(rows, 0.0, (w, 1.0, 0.5), args.fact_source)
        report["structural_weight"].append({"weight": w, **m})
        print(f"  {w:>5} {m['accuracy']:.3f} {m['ece']:>7.3f} "
              f"{m['auroc']:>7.3f} {m['brier']:>7.3f}")

    # --- fact-check weight ---------------------------------------------------
    print("\nfact-check weight (structural 1.0, confidence 0.5, tau 0.0)")
    print(f"  {'w':>5} {'acc':>6} {'ECE':>7} {'AUROC':>7} {'Brier':>7}")
    report["factcheck_weight"] = []
    for w in (0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0):
        m = evaluate(rows, 0.0, (1.0, w, 0.5), args.fact_source)
        report["factcheck_weight"].append({"weight": w, **m})
        print(f"  {w:>5} {m['accuracy']:.3f} {m['ece']:>7.3f} "
              f"{m['auroc']:>7.3f} {m['brier']:>7.3f}")

    # --- confidence weight ---------------------------------------------------
    print("\nconfidence weight (structural 1.0, factcheck 1.0, tau 0.0)")
    print(f"  {'w':>5} {'acc':>6} {'ECE':>7} {'AUROC':>7} {'Brier':>7}")
    report["confidence_weight"] = []
    for w in (0.0, 0.25, 0.5, 1.0):
        m = evaluate(rows, 0.0, (1.0, 1.0, w), args.fact_source)
        report["confidence_weight"].append({"weight": w, **m})
        print(f"  {w:>5} {m['accuracy']:.3f} {m['ece']:>7.3f} "
              f"{m['auroc']:>7.3f} {m['brier']:>7.3f}")

    # --- gating threshold ----------------------------------------------------
    print("\ngating threshold tau (weights 1.0/1.0/0.5); -1.0 admits every edge")
    print(f"  {'tau':>5} {'acc':>6} {'ECE':>7} {'AUROC':>7} {'Brier':>7}")
    report["tau"] = []
    for tau in (-1.0, -0.5, -0.25, 0.0, 0.25, 0.5, 1.0):
        m = evaluate(rows, tau, (1.0, 1.0, 0.5), args.fact_source)
        report["tau"].append({"tau": tau, **m})
        print(f"  {tau:>5} {m['accuracy']:.3f} {m['ece']:>7.3f} "
              f"{m['auroc']:>7.3f} {m['brier']:>7.3f}")

    # The spread is what matters, not the best cell: a conclusion that only holds
    # at one setting is a tuned artefact, not a result.
    aurocs = [r["auroc"] for r in report["structural_weight"] if r["auroc"] is not None]
    print(f"\nAUROC across the structural-weight sweep: "
          f"min {min(aurocs):.3f}, max {max(aurocs):.3f}, spread {max(aurocs) - min(aurocs):.3f}")
    print("Reported as sensitivity, NOT used to select the operating point.")

    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
