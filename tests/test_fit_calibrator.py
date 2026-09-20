"""Calibrator fitting (M7), and above all the leakage guard.

Fitting on a claim that is also in the held-out evaluation set is the one
mistake that would invalidate every reported number, and it fails invisibly -
the metrics simply look better than they are. So it must be impossible, not
merely avoided.
"""
import json
import pickle

import pytest

from scripts import fit_calibrator as fc


def _write(tmp_path, name, rows):
    f = tmp_path / name
    f.write_text(json.dumps(rows), encoding="utf-8")
    return f


def _calib_rows(n=30, start=0):
    """Monotone-ish: higher raw probability, more likely true."""
    return [
        {"claim": f"calibration claim {i}", "label": i % 2 == 0,
         "argus_raw_probability": 0.2 + 0.6 * (i % 2)}
        for i in range(start, start + n)
    ]


def _held_out(n=10):
    return [{"claim": f"held out claim {i}", "label": i % 2 == 0} for i in range(n)]


# --- the leakage guard ------------------------------------------------------

def test_refuses_to_fit_when_a_claim_is_also_in_the_held_out_set(tmp_path):
    leaked = _calib_rows(30)
    leaked[5]["claim"] = "held out claim 3"
    results = _write(tmp_path, "calib.json", leaked)
    held = _write(tmp_path, "held.json", _held_out())

    with pytest.raises(SystemExit, match="REFUSING to fit"):
        fc.main(["--results", str(results), "--held-out", str(held),
                 "--out", str(tmp_path / "cal.pkl")])
    assert not (tmp_path / "cal.pkl").exists(), "must not write a leaked calibrator"


def test_assert_disjoint_is_silent_on_a_clean_split(tmp_path):
    held = _write(tmp_path, "held.json", _held_out())
    fc.assert_disjoint(["calibration claim 1"], held)   # no raise


def test_refuses_when_the_held_out_file_is_missing(tmp_path):
    """Cannot verify the split is clean -> do not proceed. Silently skipping the
    check would be worse than failing."""
    with pytest.raises(SystemExit, match="cannot verify"):
        fc.assert_disjoint(["a"], tmp_path / "nope.json")


# --- refusing to fit noise --------------------------------------------------

def test_refuses_too_few_points(tmp_path):
    results = _write(tmp_path, "calib.json", _calib_rows(5))
    held = _write(tmp_path, "held.json", _held_out())
    with pytest.raises(SystemExit, match="at least"):
        fc.main(["--results", str(results), "--held-out", str(held),
                 "--out", str(tmp_path / "cal.pkl")])


def test_min_points_can_be_lowered_deliberately(tmp_path):
    results = _write(tmp_path, "calib.json", _calib_rows(6))
    held = _write(tmp_path, "held.json", _held_out())
    fc.main(["--results", str(results), "--held-out", str(held),
             "--out", str(tmp_path / "cal.pkl"), "--min-points", "4"])
    assert (tmp_path / "cal.pkl").exists()


# --- fitting ----------------------------------------------------------------

def test_writes_a_usable_calibrator(tmp_path):
    results = _write(tmp_path, "calib.json", _calib_rows(30))
    held = _write(tmp_path, "held.json", _held_out())
    out = tmp_path / "cal.pkl"
    fc.main(["--results", str(results), "--held-out", str(held), "--out", str(out)])

    with out.open("rb") as fh:
        calibrator = pickle.load(fh)
    p = float(calibrator.predict([0.8])[0])
    assert 0.0 <= p <= 1.0


def test_calibration_is_monotone():
    """Isotonic regression must never map a higher raw score to a lower
    calibrated one - that would reorder claims and destroy AUROC."""
    from app.services.judge import fit_calibrator as fit

    raws = [0.1, 0.3, 0.5, 0.7, 0.9] * 6
    labels = [False, False, True, True, True] * 6
    cal = fit(raws, labels)
    out = [float(cal.predict([r])[0]) for r in sorted(set(raws))]
    assert out == sorted(out)


def test_load_pairs_skips_unscored_and_malformed_rows(tmp_path):
    results = _write(tmp_path, "calib.json", [
        {"claim": "good", "label": True, "argus_raw_probability": 0.7},
        {"claim": "no score", "label": True},
        {"claim": "bad type", "label": True, "argus_raw_probability": "banana"},
        {"claim": "no label", "argus_raw_probability": 0.5},
        "not a dict",
    ])
    assert [c for c, _, _ in fc.load_pairs(results)] == ["good"]


def test_explains_how_to_produce_the_results_file(tmp_path):
    with pytest.raises(SystemExit, match="scripts.evaluate"):
        fc.load_pairs(tmp_path / "missing.json")


# --- no network -------------------------------------------------------------

def test_fitting_never_calls_the_llm(tmp_path, monkeypatch):
    import app.services.grok_client as gc

    monkeypatch.setattr(gc, "call_grok", lambda *a, **k: pytest.fail("LLM called"))
    results = _write(tmp_path, "calib.json", _calib_rows(30))
    held = _write(tmp_path, "held.json", _held_out())
    fc.main(["--results", str(results), "--held-out", str(held),
             "--out", str(tmp_path / "cal.pkl")])
