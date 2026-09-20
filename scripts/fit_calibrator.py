"""Fit the isotonic calibrator (PRD M7). NEVER calls the LLM.

    python -m scripts.fit_calibrator

Reads the calibration run's cache, maps raw P(true) -> calibrated P(true) by
isotonic regression against the FEVER labels, and writes data/calibrator.pkl,
which app/services/pipeline.py loads if present.

This is the one place in the project where a mistake would invalidate every
number in the write-up: fitting on a claim that is also in the held-out
evaluation set leaks the answer. Zero overlap is therefore ASSERTED here and
covered by a test, not left to discipline. The script refuses to write on any
overlap at all.
"""
import argparse
import json
import pickle
from pathlib import Path

from app.services.judge import fit_calibrator
from scripts.metrics import accuracy, auroc, brier, ece

ROOT = Path(__file__).resolve().parents[1]
CALIB_RESULTS = ROOT / "data" / "calib_results.json"
HELD_OUT = ROOT / "data" / "fever_sample.json"
OUT = ROOT / "data" / "calibrator.pkl"

# Isotonic regression is non-parametric: with too few points it interpolates
# noise and produces a step function that looks impressive on the fit set and
# generalises badly. Below this, refuse rather than ship a bad calibrator.
MIN_FIT_POINTS = 20


def load_pairs(results_file: Path) -> list:
    """(claim, raw probability, label) for every scored calibration claim."""
    if not results_file.exists():
        raise SystemExit(
            f"{results_file} not found. Score the calibration split first:\n"
            f"  python -m scripts.evaluate --sample data/fever_calib.json "
            f"--results data/calib_results.json --summary data/calib_summary.json --no-baseline"
        )
    rows = json.loads(results_file.read_text(encoding="utf-8"))
    return [
        (r["claim"], r["argus_raw_probability"], bool(r["label"]))
        for r in rows
        if isinstance(r, dict)
        and isinstance(r.get("argus_raw_probability"), (int, float))
        and r.get("label") is not None
    ]


def assert_disjoint(fit_claims, held_out_file: Path) -> None:
    """Refuse to fit on anything the held-out set also scores.

    Not a warning. A calibrator fitted on evaluation claims makes the reported
    ECE meaningless, and the failure is invisible in the output — the numbers
    just look better than they are.
    """
    if not held_out_file.exists():
        raise SystemExit(f"{held_out_file} not found; cannot verify the split is clean.")
    held = {r["claim"] for r in json.loads(held_out_file.read_text(encoding="utf-8"))}
    overlap = set(fit_claims) & held
    if overlap:
        raise SystemExit(
            f"REFUSING to fit: {len(overlap)} calibration claim(s) also appear in "
            f"{held_out_file.name}. Fitting on evaluation data invalidates every "
            f"reported metric.\nFirst few: {sorted(overlap)[:3]}"
        )


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results", type=Path, default=CALIB_RESULTS)
    p.add_argument("--held-out", type=Path, default=HELD_OUT)
    p.add_argument("--out", type=Path, default=OUT)
    p.add_argument("--min-points", type=int, default=MIN_FIT_POINTS)
    args = p.parse_args(argv)

    pairs = load_pairs(args.results)
    if not pairs:
        raise SystemExit(f"No scored calibration claims in {args.results}.")

    claims = [c for c, _, _ in pairs]
    assert_disjoint(claims, args.held_out)

    if len(pairs) < args.min_points:
        raise SystemExit(
            f"Only {len(pairs)} scored claim(s); isotonic regression needs at least "
            f"{args.min_points} to avoid fitting noise. Let the calibration run "
            f"continue, or lower --min-points deliberately."
        )

    raws = [r for _, r, _ in pairs]
    labels = [lb for _, _, lb in pairs]

    calibrator = fit_calibrator(raws, labels)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("wb") as fh:
        pickle.dump(calibrator, fh)

    fitted = [float(calibrator.predict([r])[0]) for r in raws]
    n_true = sum(labels)

    print(f"fit on {len(pairs)} claim(s) ({n_true}T/{len(labels) - n_true}F), "
          f"disjoint from {args.held_out.name}")
    print()
    print(f"{'':10} {'acc':>6} {'ECE':>7} {'AUROC':>7} {'Brier':>7}")
    for name, probs in (("raw", raws), ("calibrated", fitted)):
        auc = auroc(probs, labels)
        auc = f"{auc:.3f}" if auc is not None else "  n/a"
        print(f"{name:10} {accuracy(probs, labels):.3f} {ece(probs, labels):>7.3f} "
              f"{auc:>7} {brier(probs, labels):>7.3f}")
    print()
    print("NOTE: these are IN-SAMPLE numbers on the fit set and will flatter the")
    print("calibrator. The honest figure is the held-out run, which picks this up")
    print("automatically now that data/calibrator.pkl exists:")
    print("  python -m scripts.evaluate")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
