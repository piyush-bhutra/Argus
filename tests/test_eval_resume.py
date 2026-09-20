"""
End-to-end checks of the eval harness's cache, through scripts.evaluate.main().

No LLM is called: run_argus / run_baseline (the only two paths to the LLM) are
replaced with counting fakes, and every file lives in a temp dir.
"""
import json

import pytest

import scripts.evaluate as ev
from app.services import grok_client

CLAIMS = [
    {"claim": "Claim A is true.", "label": True},
    {"claim": "Claim B is false.", "label": False},
    {"claim": "Claim C is true.", "label": True},
    {"claim": "Claim D is false.", "label": False},
]


class FakeLLM:
    """Stands in for both halves; records which claims each half was run on."""

    def __init__(self, fail_baseline_on=None):
        self.argus_calls, self.baseline_calls = [], []
        self.fail_baseline_on = fail_baseline_on

    def argus(self, claim, rounds, **kwargs):
        # **kwargs so a new run_argus option does not break every resume test.
        self.argus_calls.append(claim)
        # Must carry every field run_argus returns: the harness copies them by
        # name, and a missing one lands the claim in the error path instead of
        # the cache — which silently looks like "resume did not work".
        return {
            "raw_probability": 0.3,
            "n_arguments": 4,
            "grounded_extension": {"advocate": [], "skeptic": []},
            "dropped_edges": [],
            "symbolic_coverage": 0.5,
            "arguments": [],
            "fact_checks": [],
            "fact_checks_llm": [],
        }

    def baseline(self, claim):
        self.baseline_calls.append(claim)
        if claim == self.fail_baseline_on:
            raise RuntimeError("429 GenerateRequestsPerDayPerProjectPerModel-FreeTier")
        return 0.8


@pytest.fixture
def env(tmp_path, monkeypatch):
    sample = tmp_path / "fever_sample.json"
    sample.write_text(json.dumps(CLAIMS), encoding="utf-8")
    monkeypatch.setattr(ev, "ROOT", tmp_path)
    monkeypatch.setattr(ev, "SAMPLE", sample)
    monkeypatch.setattr(ev, "RESULTS", tmp_path / "eval_results.json")
    monkeypatch.setattr(ev, "SUMMARY", tmp_path / "eval_summary.json")
    monkeypatch.setattr(ev, "_load_calibrator", lambda: None)
    monkeypatch.setattr(ev.settings, "llm_model", "test-model")
    # main() overrides the timeout; registering it here restores it afterwards.
    monkeypatch.setattr(grok_client, "_REQUEST_TIMEOUT", grok_client._REQUEST_TIMEOUT)

    def run(fake, *extra):
        monkeypatch.setattr(ev, "run_argus", fake.argus)
        monkeypatch.setattr(ev, "run_baseline", fake.baseline)
        ev.main(["--delay", "0", *extra])
        return fake

    return tmp_path, run


def _results(tmp_path):
    return {r["claim"]: r for r in json.loads((tmp_path / "eval_results.json").read_text())}


def _summary(tmp_path):
    return json.loads((tmp_path / "eval_summary.json").read_text())


def test_interrupted_run_resumes_without_rescoring(env):
    """Quota dies on claim B's baseline, after B's debate already succeeded.
    The resumed run must not re-debate A or B, and must not re-query A."""
    tmp_path, run = env
    first = run(FakeLLM(fail_baseline_on="Claim B is false."))
    assert first.argus_calls == ["Claim A is true.", "Claim B is false."]
    assert _summary(tmp_path)["aborted"]

    second = run(FakeLLM())
    assert second.argus_calls == ["Claim C is true.", "Claim D is false."]
    assert second.baseline_calls == ["Claim B is false.", "Claim C is true.", "Claim D is false."]

    summary = _summary(tmp_path)
    assert summary["argus"]["n"] == summary["baseline"]["n"] == 4
    assert "aborted" not in summary

    third = run(FakeLLM())  # fully cached: zero LLM calls
    assert third.argus_calls == third.baseline_calls == []


def test_config_change_rescores_only_the_affected_half(env):
    tmp_path, run = env
    run(FakeLLM())

    # --rounds changes the debate, not the baseline prompt.
    fake = run(FakeLLM(), "--rounds", "3")
    assert len(fake.argus_calls) == 4
    assert fake.baseline_calls == []

    # A different model invalidates both halves.
    import scripts.evaluate as ev_mod
    ev_mod.settings.llm_model = "other-model"
    fake = run(FakeLLM(), "--rounds", "3")
    assert len(fake.argus_calls) == 4 and len(fake.baseline_calls) == 4


def test_stale_halves_never_counted_in_metrics(env):
    """Scores from another config must not leak into the summary, even when
    the harness can't re-score them (here: --no-baseline)."""
    tmp_path, run = env
    run(FakeLLM())
    ev.settings.llm_model = "other-model"
    run(FakeLLM(), "--no-baseline")
    summary = _summary(tmp_path)
    assert summary["argus"]["n"] == 4
    assert summary["baseline"]["n"] == 0


def test_label_comes_from_sample_not_cache(env):
    tmp_path, run = env
    run(FakeLLM())
    rows = json.loads((tmp_path / "eval_results.json").read_text())
    for r in rows:
        r["label"] = not r["label"]  # poison the cached labels
    (tmp_path / "eval_results.json").write_text(json.dumps(rows))

    fake = run(FakeLLM())
    assert fake.argus_calls == fake.baseline_calls == []  # scores still reused
    results = _results(tmp_path)
    assert all(results[c["claim"]]["label"] == c["label"] for c in CLAIMS)


def test_corrupt_cache_file_is_moved_aside_not_fatal(env):
    """A half-written results file must not crash the run. It is kept (renamed),
    never deleted, and every claim is re-scored."""
    tmp_path, run = env
    torn = '[{"claim": "Claim A is true.", "label": true, "argus_raw_prob'
    (tmp_path / "eval_results.json").write_text(torn)

    fake = run(FakeLLM())
    assert len(fake.argus_calls) == len(fake.baseline_calls) == 4
    backups = list(tmp_path.glob("eval_results.corrupt-*.json"))
    assert len(backups) == 1 and backups[0].read_text() == torn
    assert len(_results(tmp_path)) == 4


def test_corrupt_entries_rescored_individually(env):
    """One bad row must cost one claim's re-score, not the whole cache."""
    tmp_path, run = env
    run(FakeLLM())
    rows = {r["claim"]: r for r in json.loads((tmp_path / "eval_results.json").read_text())}
    rows["Claim A is true."]["argus_raw_probability"] = "banana"   # wrong type
    rows["Claim B is false."]["baseline_probability"] = 1.7        # out of range
    del rows["Claim C is true."]["claim"]                          # no key at all
    (tmp_path / "eval_results.json").write_text(
        json.dumps(list(rows.values()) + ["not even a dict"]))

    fake = run(FakeLLM())
    assert fake.argus_calls == ["Claim A is true.", "Claim C is true."]
    assert fake.baseline_calls == ["Claim B is false.", "Claim C is true."]
    assert _summary(tmp_path)["argus"]["n"] == 4


def test_limit_subset_is_class_balanced(env):
    tmp_path, run = env
    fake = run(FakeLLM(), "--limit", "2")
    config = _summary(tmp_path)["config"]
    assert (config["n_true"], config["n_false"]) == (1, 1)
    assert len(fake.argus_calls) == 2


def test_fake_argus_matches_the_real_artifact_contract():
    """Guard against the fake drifting from run_argus. When it did, every claim
    hit the error path and the resume tests failed for a reason unrelated to
    resuming."""
    produced = set(FakeLLM().argus("c", 2, legacy_factcheck=False)) - {"raw_probability"}
    assert produced == set(ev.ARTIFACT_FIELDS)


def test_relative_sample_path_does_not_crash_the_run(tmp_path, monkeypatch):
    """Regression: --sample took a relative path, and the config block reported
    SAMPLE.relative_to(ROOT), which raises on one. The run died before scoring a
    single claim."""
    sample = tmp_path / "calib.json"
    sample.write_text(json.dumps(CLAIMS), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ev, "RESULTS", tmp_path / "r.json")
    monkeypatch.setattr(ev, "SUMMARY", tmp_path / "s.json")
    monkeypatch.setattr(ev, "_load_calibrator", lambda: None)
    fake = FakeLLM()
    monkeypatch.setattr(ev, "run_argus", fake.argus)
    monkeypatch.setattr(ev, "run_baseline", fake.baseline)

    ev.main(["--delay", "0", "--sample", "calib.json",
             "--results", "r.json", "--summary", "s.json"])
    assert len(fake.argus_calls) == 4


def test_out_of_repo_sample_is_reported_by_full_path(tmp_path):
    assert ev._relative_or_absolute(tmp_path / "x.json") == str(tmp_path / "x.json")
    assert ev._relative_or_absolute(ev.ROOT / "data" / "x.json") in ("data/x.json", r"data\x.json")
