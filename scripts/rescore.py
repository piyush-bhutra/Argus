"""Re-score cached debate artifacts offline. NEVER calls the LLM.

    python -m scripts.rescore                          # current settings
    python -m scripts.rescore --tau -1                 # no evidence gating
    python -m scripts.rescore --structural-mode count  # reproduce the old bug
    python -m scripts.rescore --fact-source llm        # ask-the-model-twice
    python -m scripts.rescore --ablations              # the whole table

Everything downstream of the LLM — the gating threshold, the judge weights, the
fact-check source, the structural mode — re-runs from data/eval_results.json in
seconds. That is the whole point of caching artifacts rather than scores: a
question about the judge costs nothing instead of a multi-hour quota-gated run.

Imports only pure modules. scripts/metrics.py and the services used here have no
network path, and tests/test_rescore.py asserts a call would fail loudly.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from app.models.schemas import Argument, FactCheckResult
from app.services.gating import DEFAULT_TAU, gate_attacks
from app.services.judge import sigmoid, structural_signal
from app.services.semantics_engine import compute_grounded_extension
from scripts.metrics import accuracy, auroc, bin_stats, brier, ece, mcnemar, threshold_sweep

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "eval_results.json"
SUMMARY = ROOT / "data" / "rescore_summary.json"

DEFAULT_WEIGHTS = (1.0, 1.0, 0.5)   # structural, factcheck, confidence


def load_artifacts(path: Path = None) -> list:
    """Cached rows that carry a full v2 artifact. Score-only rows are skipped."""
    path = path or RESULTS
    if not path.exists():
        raise SystemExit(f"{path} not found - run: python -m scripts.evaluate")
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [
        r for r in rows
        if isinstance(r, dict) and isinstance(r.get("arguments"), list) and r["arguments"]
    ]


def _arguments(row: dict) -> list:
    return [Argument(**a) for a in row["arguments"]]


def _fact_results(row: dict, source: str) -> list:
    """Fact-check results from the cache, from either scorer.

    'llm' reads the legacy ask-the-model-twice scores recorded alongside the
    symbolic ones, which is what makes that ablation free.
    """
    field = "fact_checks_llm" if source == "llm" else "fact_checks"
    return [
        FactCheckResult(
            argument_id=f["argument_id"],
            evidence_sentences=f.get("evidence_sentences", []),
            support_score=f["support_score"],
            method=f.get("method", "none"),
            rules_fired=f.get("rules_fired", []),
            evidence_ids=f.get("evidence_ids", []),
        )
        for f in row.get(field, [])
    ]


def score_row(row: dict, tau: float, weights, structural_mode: str, fact_source: str) -> dict:
    """One cached debate -> probability, re-running only the offline stages."""
    arguments = _arguments(row)
    facts = _fact_results(row, fact_source)

    gated, dropped = gate_attacks(arguments, facts, tau=tau)
    grounded = compute_grounded_extension(gated)

    w_struct, w_fact, w_conf = weights
    structural = structural_signal(grounded, facts, mode=structural_mode)

    support = {f.argument_id: f.support_score for f in facts}
    by_side = {"advocate": [], "skeptic": []}
    conf_by_side = {"advocate": [], "skeptic": []}
    for a in arguments:
        if a.id in support:
            by_side[a.agent].append(support[a.id])
        conf_by_side[a.agent].append(a.self_confidence)

    def mean(xs):
        return sum(xs) / len(xs) if xs else 0.0

    factcheck = mean(by_side["advocate"]) - mean(by_side["skeptic"])
    confidence = mean(conf_by_side["advocate"]) - mean(conf_by_side["skeptic"])

    return {
        "claim": row["claim"],
        "label": row["label"],
        "probability": sigmoid(w_struct * structural + w_fact * factcheck + w_conf * confidence),
        "grounded_extension": grounded,
        "n_dropped_edges": len(dropped),
        "n_survivors": len(grounded["advocate"]) + len(grounded["skeptic"]),
        "structural": structural,
        "symbolic_coverage": row.get("symbolic_coverage"),
    }


def summarise(scored: list, rows: list, config: dict, bins: int = 10) -> dict:
    probs = [s["probability"] for s in scored]
    labels = [s["label"] for s in scored]

    baseline = [(r.get("baseline_probability"), r["label"]) for r in rows]
    baseline = [(p, lb) for p, lb in baseline if isinstance(p, (int, float))]

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": config,
        "argus": {
            "n": len(probs),
            "accuracy": accuracy(probs, labels),
            "ece": ece(probs, labels, bins),
            "auroc": auroc(probs, labels),
            "brier": brier(probs, labels),
            "mean_probability": sum(probs) / len(probs) if probs else None,
            "bins": bin_stats(probs, labels, bins),
            "threshold_sweep": threshold_sweep(probs, labels),
        },
        # Structural health: under the old protocol this was skeptic-2 /
        # advocate-0 in 57 of 58 debates, so the signal was a constant. If the
        # spread here is still degenerate, the redesign has not worked.
        "structure": {
            "mean_survivors": (sum(s["n_survivors"] for s in scored) / len(scored)) if scored else None,
            "distinct_structural_values": len({round(s["structural"], 4) for s in scored}),
            "total_dropped_edges": sum(s["n_dropped_edges"] for s in scored),
            "mean_symbolic_coverage": (
                sum(s["symbolic_coverage"] or 0.0 for s in scored) / len(scored)
            ) if scored else None,
        },
        "claims": scored,
    }

    if baseline:
        b_probs = [p for p, _ in baseline]
        b_labels = [lb for _, lb in baseline]
        out["baseline"] = {
            "n": len(b_probs),
            "accuracy": accuracy(b_probs, b_labels),
            "ece": ece(b_probs, b_labels, bins),
            "auroc": auroc(b_probs, b_labels),
            "brier": brier(b_probs, b_labels),
            "mean_probability": sum(b_probs) / len(b_probs),
        }

        paired = [
            (s, r) for s, r in zip(scored, rows)
            if isinstance(r.get("baseline_probability"), (int, float))
        ]
        if paired:
            out["mcnemar_argus_vs_baseline"] = mcnemar(
                [(s["probability"] >= 0.5) == s["label"] for s, _ in paired],
                [(r["baseline_probability"] >= 0.5) == s["label"] for s, r in paired],
            )
    return out


ABLATIONS = [
    ("full system", {}),
    ("no evidence gating", {"tau": -1.0}),
    ("no evidence weighting", {"structural_mode": "count"}),
    ("LLM fact-check", {"fact_source": "llm"}),
    ("structural only", {"weights": (1.0, 0.0, 0.0)}),
    ("no structural term", {"weights": (0.0, 1.0, 0.5)}),
]


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tau", type=float, default=DEFAULT_TAU)
    p.add_argument("--weights", type=str, default=None,
                   help="structural,factcheck,confidence (default 1,1,0.5)")
    p.add_argument("--structural-mode", choices=("weighted", "count"), default="weighted")
    p.add_argument("--fact-source", choices=("symbolic", "llm"), default="symbolic")
    p.add_argument("--bins", type=int, default=10)
    p.add_argument("--ablations", action="store_true", help="run the whole ablation table")
    p.add_argument("--results", type=Path, default=None)
    args = p.parse_args(argv)

    weights = DEFAULT_WEIGHTS
    if args.weights:
        weights = tuple(float(x) for x in args.weights.split(","))

    rows = load_artifacts(args.results)
    if not rows:
        raise SystemExit(
            "No v2 artifacts in the cache. Only rows with a full debate artifact "
            "can be re-scored; run scripts.evaluate first."
        )
    print(f"{len(rows)} cached debates with artifacts\n")

    settings = [("full system", {})] if not args.ablations else ABLATIONS
    if not args.ablations:
        settings = [("current settings", {
            "tau": args.tau, "weights": weights,
            "structural_mode": args.structural_mode, "fact_source": args.fact_source,
        })]

    print(f"{'configuration':24} {'acc':>6} {'ECE':>7} {'AUROC':>7} {'Brier':>7} {'meanP':>7}")
    print("-" * 64)

    last = None
    for name, override in settings:
        cfg = {"tau": args.tau, "weights": weights,
               "structural_mode": args.structural_mode, "fact_source": args.fact_source}
        cfg.update(override)
        scored = [score_row(r, cfg["tau"], cfg["weights"],
                            cfg["structural_mode"], cfg["fact_source"]) for r in rows]
        last = summarise(scored, rows, {**cfg, "weights": list(cfg["weights"]), "name": name},
                         args.bins)
        a = last["argus"]
        auc = f"{a['auroc']:.3f}" if a["auroc"] is not None else "  n/a"
        print(f"{name:24} {a['accuracy']:.3f} {a['ece']:>7.3f} {auc:>7} "
              f"{a['brier']:>7.3f} {a['mean_probability']:>7.3f}")

    if "baseline" in last:
        b = last["baseline"]
        auc = f"{b['auroc']:.3f}" if b["auroc"] is not None else "  n/a"
        print("-" * 64)
        print(f"{'baseline (single call)':24} {b['accuracy']:.3f} {b['ece']:>7.3f} {auc:>7} "
              f"{b['brier']:>7.3f} {b['mean_probability']:>7.3f}")

    s = last["structure"]
    print(f"\nstructure: mean survivors {s['mean_survivors']:.2f}, "
          f"{s['distinct_structural_values']} distinct structural values, "
          f"{s['total_dropped_edges']} gated edges, "
          f"mean symbolic coverage {s['mean_symbolic_coverage']:.2f}")

    SUMMARY.write_text(json.dumps(last, indent=2), encoding="utf-8")
    print(f"\nsummary -> {SUMMARY}")


if __name__ == "__main__":
    main()
