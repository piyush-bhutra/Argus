"""scripts/rescore.py must re-score cached artifacts WITHOUT touching the LLM.

That guarantee is the reason the artifact cache exists: if rescoring can call
the provider, every judge experiment costs quota again.
"""
import json

import pytest

import scripts.rescore as rs


def _row(claim, label, adv_support, skp_support, llm_adv=0.0, llm_skp=0.0):
    return {
        "claim": claim,
        "label": label,
        "baseline_probability": 0.9 if label else 0.1,
        "symbolic_coverage": 1.0,
        "arguments": [
            {"id": "arg_1", "agent": "advocate", "round": 1, "text": "a",
             "attacks": [], "self_confidence": 0.8},
            {"id": "arg_2", "agent": "skeptic", "round": 1, "text": "s",
             "attacks": ["arg_1"], "self_confidence": 0.8},
        ],
        "fact_checks": [
            {"argument_id": "arg_1", "support_score": adv_support, "method": "symbolic",
             "rules_fired": ["entailment"], "evidence_ids": ["e1"], "evidence_sentences": ["x"]},
            {"argument_id": "arg_2", "support_score": skp_support, "method": "symbolic",
             "rules_fired": ["entailment"], "evidence_ids": ["e2"], "evidence_sentences": ["y"]},
        ],
        "fact_checks_llm": [
            {"argument_id": "arg_1", "support_score": llm_adv},
            {"argument_id": "arg_2", "support_score": llm_skp},
        ],
    }


ROWS = [_row("true claim", True, 1.0, -1.0), _row("false claim", False, -1.0, 1.0)]


# --- the guarantee ----------------------------------------------------------

def test_rescoring_never_calls_the_llm(monkeypatch):
    """The whole point of the artifact cache. Any path to the provider makes
    judge experiments cost quota again."""
    import app.services.grok_client as gc

    def boom(*a, **k):
        raise AssertionError("rescore must never call the LLM")

    monkeypatch.setattr(gc, "call_grok", boom)
    scored = [rs.score_row(r, 0.0, (1.0, 1.0, 0.5), "weighted", "symbolic") for r in ROWS]
    assert len(scored) == 2


def test_rescore_module_does_not_import_the_llm_client():
    """A transitive import is how a network path sneaks back in."""
    import inspect

    src = inspect.getsource(rs)
    assert "grok_client" not in src
    assert "call_grok" not in src


# --- scoring ----------------------------------------------------------------

def test_supported_advocate_yields_high_probability():
    s = rs.score_row(ROWS[0], 0.0, (1.0, 1.0, 0.5), "weighted", "symbolic")
    assert s["probability"] > 0.5
    assert s["label"] is True


def test_contradicted_advocate_yields_low_probability():
    s = rs.score_row(ROWS[1], 0.0, (1.0, 1.0, 0.5), "weighted", "symbolic")
    assert s["probability"] < 0.5


def test_gating_changes_the_grounded_extension():
    """arg_2 is contradicted, so its attack is gated out and arg_1 survives."""
    gated = rs.score_row(ROWS[0], 0.0, (1.0, 1.0, 0.5), "weighted", "symbolic")
    ungated = rs.score_row(ROWS[0], -1.0, (1.0, 1.0, 0.5), "weighted", "symbolic")
    assert gated["grounded_extension"]["advocate"] == ["arg_1"]
    assert ungated["grounded_extension"]["advocate"] == []


def test_gating_changes_the_probability():
    # Supports of exactly +1/-1 are a trap here: gated gives (1.0+1.0)/2 and
    # ungated gives (0+1.0)/1, both 1.0, so the probability coincides and the
    # test would pass while measuring nothing. Asymmetric supports separate them.
    row = _row("c", True, adv_support=1.0, skp_support=-0.5)
    gated = rs.score_row(row, 0.0, (1.0, 0.0, 0.0), "weighted", "symbolic")
    ungated = rs.score_row(row, -1.0, (1.0, 0.0, 0.0), "weighted", "symbolic")
    assert gated["structural"] == pytest.approx(0.75)
    assert ungated["structural"] == pytest.approx(0.5)
    assert gated["probability"] > ungated["probability"]


def test_count_mode_reproduces_the_unweighted_structural_term():
    s = rs.score_row(ROWS[0], -1.0, (1.0, 0.0, 0.0), "count", "symbolic")
    # ungated: only the skeptic survives -> count structural = 0 - 1 = -1
    assert s["structural"] == -1.0


def test_llm_fact_source_reads_the_other_cached_scores():
    row = _row("c", True, adv_support=1.0, skp_support=-1.0, llm_adv=-1.0, llm_skp=1.0)
    sym = rs.score_row(row, 0.0, (1.0, 1.0, 0.5), "weighted", "symbolic")
    llm = rs.score_row(row, 0.0, (1.0, 1.0, 0.5), "weighted", "llm")
    assert sym["probability"] > 0.5 > llm["probability"]


def test_weights_are_applied():
    hi = rs.score_row(ROWS[0], 0.0, (4.0, 0.0, 0.0), "weighted", "symbolic")
    lo = rs.score_row(ROWS[0], 0.0, (0.5, 0.0, 0.0), "weighted", "symbolic")
    assert hi["probability"] > lo["probability"]


def test_zero_weights_give_one_half():
    s = rs.score_row(ROWS[0], 0.0, (0.0, 0.0, 0.0), "weighted", "symbolic")
    assert s["probability"] == pytest.approx(0.5)


# --- loading and summarising ------------------------------------------------

def test_load_artifacts_skips_score_only_rows(tmp_path):
    f = tmp_path / "eval_results.json"
    f.write_text(json.dumps([
        {"claim": "old", "label": True, "argus_raw_probability": 0.3},   # v1, no artifact
        ROWS[0],
    ]), encoding="utf-8")
    assert [r["claim"] for r in rs.load_artifacts(f)] == ["true claim"]


def test_load_artifacts_is_explicit_when_the_file_is_missing(tmp_path):
    with pytest.raises(SystemExit):
        rs.load_artifacts(tmp_path / "nope.json")


def test_summary_reports_structural_health():
    scored = [rs.score_row(r, 0.0, (1.0, 1.0, 0.5), "weighted", "symbolic") for r in ROWS]
    out = rs.summarise(scored, ROWS, {})
    # The metric that says whether the degeneracy is gone: a constant structural
    # signal would collapse to one distinct value.
    assert out["structure"]["distinct_structural_values"] == 2
    assert out["structure"]["mean_symbolic_coverage"] == 1.0


def test_summary_includes_paired_mcnemar_against_the_baseline():
    scored = [rs.score_row(r, 0.0, (1.0, 1.0, 0.5), "weighted", "symbolic") for r in ROWS]
    out = rs.summarise(scored, ROWS, {})
    assert out["mcnemar_argus_vs_baseline"]["n_discordant"] == 0
    assert out["baseline"]["n"] == 2
