"""Unattended overnight collection of the calibration split (M7).

    python -m scripts.overnight

Runs the calibration scoring run, and when the provider's DAILY quota is
exhausted it sleeps and retries rather than giving up. Everything already
scored is kept, so each retry resumes where the last one stopped — the
evaluation harness caches per claim and the cache is written after every claim.

Safe to kill at any point (Ctrl-C, closing the terminal, a reboot): the next
run picks up from `data/calib_results.json`. Nothing is lost, and no claim is
ever paid for twice.

Only touches the calibration split. The held-out evaluation set and its results
are never written to.
"""
import argparse
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "calib_results.json"

CMD = [
    sys.executable, "-m", "scripts.evaluate",
    "--sample", str(ROOT / "data" / "fever_calib.json"),
    "--results", str(RESULTS),
    "--summary", str(ROOT / "data" / "calib_summary.json"),
    "--no-baseline",            # the baseline half is not needed to fit a calibrator
    "--no-legacy-factcheck",    # ablation-only call; saves one request per claim
    "--delay", "3",
]


def scored_count() -> int:
    """Claims with a usable Argus probability in the calibration cache."""
    if not RESULTS.exists():
        return 0
    import json

    try:
        rows = json.loads(RESULTS.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return 0
    return sum(
        1 for r in rows
        if isinstance(r, dict) and isinstance(r.get("argus_raw_probability"), (int, float))
    )


def stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--target", type=int, default=100,
                   help="stop once this many claims are scored (default 100)")
    p.add_argument("--retry-minutes", type=int, default=45,
                   help="wait between attempts when the daily quota is exhausted")
    p.add_argument("--max-hours", type=float, default=14.0,
                   help="give up after this long (default 14h — one night)")
    args = p.parse_args(argv)

    deadline = datetime.now() + timedelta(hours=args.max_hours)
    start_count = scored_count()
    print(f"[{stamp()}] starting with {start_count}/{args.target} claims scored")
    print(f"[{stamp()}] will stop at {deadline:%Y-%m-%d %H:%M} or on reaching the target")
    print(f"[{stamp()}] safe to kill at any time; progress is cached per claim\n")

    attempt = 0
    while datetime.now() < deadline:
        have = scored_count()
        if have >= args.target:
            print(f"\n[{stamp()}] TARGET REACHED: {have}/{args.target} claims scored")
            break

        attempt += 1
        print(f"[{stamp()}] attempt {attempt} — {have}/{args.target} scored so far")
        # Output goes to this process's stdout, so a redirected log captures the
        # harness's own per-claim lines too.
        subprocess.run(CMD, cwd=ROOT)

        gained = scored_count() - have
        print(f"[{stamp()}] attempt {attempt} finished, +{gained} claim(s) this round")

        if scored_count() >= args.target:
            continue  # loop head prints the completion message

        if gained == 0:
            print(f"[{stamp()}] no progress — quota is likely exhausted for the day")
        print(f"[{stamp()}] sleeping {args.retry_minutes} min before retrying\n")
        time.sleep(args.retry_minutes * 60)

    final = scored_count()
    print(f"\n[{stamp()}] stopped with {final}/{args.target} claims scored "
          f"(+{final - start_count} this session)")

    if final >= 20:
        print("\nEnough points to fit the calibrator (minimum 20). Next:")
        print("  python -m scripts.fit_calibrator")
        print("  python -m scripts.evaluate        # re-score held-out WITH the calibrator")
    else:
        print(f"\nOnly {final} scored; the fitter refuses below 20 points to avoid "
              f"interpolating noise. Run this again after the next quota reset.")


if __name__ == "__main__":
    main()
