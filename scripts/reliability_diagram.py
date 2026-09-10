"""
Reliability diagrams for the last evaluation run (written by scripts.evaluate).

    python -m scripts.reliability_diagram

Writes data/reliability_argus.png and data/reliability_baseline.png. A perfectly
calibrated system sits on the diagonal: of the claims it called 0.7, 70% are true.

Reads the per-claim scores recorded in data/eval_summary.json - exactly the set
the reported metrics came from - not data/eval_results.json, which is a cache
that can hold scores from other configs. Binning is imported from
scripts.evaluate and defaults to the run's own bin count, so the plot and the
reported ECE can never disagree.
"""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # no display on a headless/dev box
import matplotlib.pyplot as plt  # noqa: E402

from scripts.evaluate import SUMMARY, accuracy, bin_stats, ece  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def plot(rows, key, title, out_path, bins):
    pairs = [(r[key], r["label"]) for r in rows if r.get(key) is not None]
    if not pairs:
        print(f"skipped {title}: no scored claims for {key}")
        return
    probs = [p for p, _ in pairs]
    labels = [lb for _, lb in pairs]
    stats = bin_stats(probs, labels, bins)
    width = 1.0 / bins

    fig, (ax, ax_hist) = plt.subplots(
        2, 1, figsize=(5.5, 6.5), height_ratios=[3, 1], sharex=True
    )

    ax.plot([0, 1], [0, 1], "k--", lw=1, label="perfect calibration")
    ax.bar(
        [b["lo"] + width / 2 for b in stats],
        [b["accuracy"] if b["count"] else 0 for b in stats],
        width=width * 0.9,
        color="#4C72B0",
        edgecolor="white",
        label="observed fraction true",
    )
    ax.set_ylim(0, 1)
    ax.set_ylabel("fraction of claims actually true")
    ax.set_title(
        f"{title}\nn={len(probs)}  accuracy={accuracy(probs, labels):.3f}  "
        f"ECE={ece(probs, labels, bins):.3f}"
    )
    ax.legend(loc="upper left", fontsize=8)

    ax_hist.bar(
        [b["lo"] + width / 2 for b in stats],
        [b["count"] for b in stats],
        width=width * 0.9,
        color="#999999",
        edgecolor="white",
    )
    ax_hist.set_xlim(0, 1)
    ax_hist.set_xlabel("predicted P(claim true)")
    ax_hist.set_ylabel("claims")

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"wrote {out_path}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--bins", type=int, help="bins (default: the eval run's own --bins)")
    p.add_argument("--summary", type=Path, default=SUMMARY)
    args = p.parse_args()

    if not args.summary.exists():
        raise SystemExit(f"{args.summary} not found - run: python -m scripts.evaluate")

    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    if "claims" not in summary:
        raise SystemExit(f"{args.summary} predates per-claim recording - rerun: python -m scripts.evaluate")
    rows = summary["claims"]
    args.bins = args.bins or summary["config"]["bins"]
    plot(rows, "argus_probability", "Argus (debate + grounded extension + judge)",
         ROOT / "data" / "reliability_argus.png", args.bins)
    plot(rows, "baseline_probability", "Baseline (single LLM call)",
         ROOT / "data" / "reliability_baseline.png", args.bins)


if __name__ == "__main__":
    main()
