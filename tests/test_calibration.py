"""M7 Learning — calibration step: raw probability in, calibrated probability out."""
from app.services.judge import apply_calibration, fit_calibrator


def test_calibration_maps_raw_to_calibrated():
    # A raw scorer that is systematically over-confident on the low end.
    raw = [0.2, 0.3, 0.55, 0.6, 0.8, 0.9]
    labels = [False, False, False, True, True, True]

    calibrator = fit_calibrator(raw, labels)

    calibrated = [apply_calibration(calibrator, r) for r in raw]

    # stays in [0, 1]
    assert all(0.0 <= c <= 1.0 for c in calibrated)
    # monotonic non-decreasing (isotonic guarantee)
    assert calibrated == sorted(calibrated)
    # separates the two classes: worst positive scores above best negative
    assert min(calibrated[3:]) >= max(calibrated[:3])
    # calibration actually moved at least one value
    assert any(abs(c - r) > 1e-9 for c, r in zip(calibrated, raw))


def test_calibration_clips_out_of_range_inputs():
    calibrator = fit_calibrator([0.3, 0.7], [False, True])
    assert 0.0 <= apply_calibration(calibrator, 0.0) <= 1.0
    assert 0.0 <= apply_calibration(calibrator, 1.0) <= 1.0
