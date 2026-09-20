"""Demo corpus export. Offline: the deployed demo must not need an LLM call."""
import json

import pytest

from app.services.debate_store import DebateRecord
from scripts import export_demos as ed
from tests.test_rescore import ROWS


def test_exported_records_validate_as_debate_records():
    """They are loaded straight into debate_store at startup, so a shape error
    here shows up as an empty demo corpus on a deployed instance."""
    taken = set()
    for row in ROWS:
        DebateRecord(**ed.to_record(row, taken))


def test_export_never_calls_the_llm(monkeypatch):
    import app.services.grok_client as gc

    monkeypatch.setattr(gc, "call_grok", lambda *a, **k: pytest.fail("LLM called"))
    taken = set()
    assert ed.to_record(ROWS[0], taken)["status"] == "complete"


def test_slugs_are_readable_and_unique():
    taken = set()
    a = ed.slug("The Chrysler Building is tall!", taken)
    b = ed.slug("The Chrysler Building is tall?", taken)
    assert a == "demo-the-chrysler-building-is-tall"
    assert b == "demo-the-chrysler-building-is-tall-2"   # collision gets suffixed


def test_slug_handles_a_claim_with_nothing_slugifiable():
    assert ed.slug("!!!", set()) == "demo-claim"


def test_graph_is_built_over_gated_arguments():
    """The rendered edges must be the ones the verdict was computed from -
    showing an attack the judge ignored would make the trace a lie."""
    taken = set()
    rec = ed.to_record(ROWS[0], taken)
    dropped = {tuple(e) for e in rec["verdict"]["dropped_edges"]}
    edges = {(e["source"], e["target"]) for e in rec["graph"]["edges"]}
    assert not (edges & dropped)


def test_answer_key_is_not_exported():
    """The demo shows what the system concluded, not the ground-truth label."""
    rec = ed.to_record(ROWS[0], set())
    assert "label" not in rec
    assert "label" not in json.dumps(rec["verdict"])
