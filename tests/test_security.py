"""Security boundaries on the public API.

`POST /debate/start` is unauthenticated and each accepted call spends roughly
six LLM requests against the operator's key. These tests pin the controls that
stop it being an open proxy onto someone else's quota.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.ratelimit import RateLimiter
from app.main import app
from app.models.schemas import MAX_CLAIM_LENGTH, StartDebateRequest
from app.services import debate_store


@pytest.fixture
def client():
    """Client with the pipeline stubbed — no test may reach the provider."""
    with patch("app.api.routes.run_pipeline"):
        with TestClient(app) as c:
            yield c


@pytest.fixture(autouse=True)
def _reset_limiter():
    from app.core.ratelimit import debate_limiter

    debate_limiter._hits.clear()
    yield
    debate_limiter._hits.clear()


# --- input bounds -----------------------------------------------------------

def test_oversized_claim_is_rejected():
    """The claim is embedded in every prompt of the debate, so an unbounded one
    is a token-cost amplifier aimed at the operator's quota. A 1 MB claim was
    accepted before this limit."""
    with pytest.raises(Exception):
        StartDebateRequest(claim="A" * (MAX_CLAIM_LENGTH + 1), rounds=2)


def test_oversized_claim_is_rejected_over_http(client):
    r = client.post("/debate/start", json={"claim": "A" * 1_000_000, "rounds": 2})
    assert r.status_code == 422


def test_empty_claim_is_rejected(client):
    assert client.post("/debate/start", json={"claim": "", "rounds": 2}).status_code == 422


def test_rounds_cannot_exceed_the_cap(client):
    for rounds in (0, -5, 99, 10**9):
        r = client.post("/debate/start", json={"claim": "x", "rounds": rounds})
        assert r.status_code == 422, f"rounds={rounds} was accepted"


def test_a_normal_claim_still_works(client):
    r = client.post("/debate/start", json={"claim": "The sky is blue.", "rounds": 2})
    assert r.status_code == 200 and r.json()["debate_id"]


# --- rate limiting ----------------------------------------------------------

def test_rate_limit_blocks_a_burst(client):
    from app.core.ratelimit import debate_limiter

    allowed = sum(
        client.post("/debate/start", json={"claim": "x", "rounds": 1}).status_code == 200
        for _ in range(debate_limiter.max_requests + 5)
    )
    assert allowed == debate_limiter.max_requests


def test_rate_limited_response_tells_the_caller_when_to_retry(client):
    from app.core.ratelimit import debate_limiter

    for _ in range(debate_limiter.max_requests):
        client.post("/debate/start", json={"claim": "x", "rounds": 1})
    r = client.post("/debate/start", json={"claim": "x", "rounds": 1})
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) > 0


def test_limiter_window_expires():
    rl = RateLimiter(max_requests=2, window_seconds=10)
    assert rl.allow("ip", now=0) and rl.allow("ip", now=1)
    assert not rl.allow("ip", now=2)
    assert rl.allow("ip", now=100)          # window has passed


def test_limiter_is_per_client():
    rl = RateLimiter(max_requests=1, window_seconds=10)
    assert rl.allow("a", now=0)
    assert not rl.allow("a", now=1)
    assert rl.allow("b", now=1)             # a different caller is unaffected


def test_limiter_memory_is_bounded():
    """An attacker rotating source addresses must not be able to grow the
    limiter's own dict without limit — that would make the control the DoS."""
    rl = RateLimiter(max_requests=1, window_seconds=0.0001)
    for i in range(12_000):
        rl.allow(f"ip-{i}", now=i)
    assert len(rl._hits) <= 10_001


def test_forwarded_header_is_ignored_unless_proxy_is_trusted(client, monkeypatch):
    """X-Forwarded-For is client-supplied. Honouring it by default would let
    anyone bypass the rate limit by varying one header."""
    from app.core.config import settings
    from app.core.ratelimit import debate_limiter

    monkeypatch.setattr(settings, "trust_proxy_headers", False)
    codes = [
        client.post("/debate/start", json={"claim": "x", "rounds": 1},
                    headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code
        for i in range(debate_limiter.max_requests + 3)
    ]
    assert 429 in codes, "spoofed forwarding header bypassed the rate limit"


# --- information disclosure -------------------------------------------------

def test_pipeline_errors_do_not_leak_internals():
    """The fallback used to echo str(e)[:300] to the caller, exposing provider
    endpoints, model names and internal paths."""
    from app.services.pipeline import _friendly_error

    leaky = RuntimeError(
        "Connection failed to https://generativelanguage.googleapis.com/v1beta/"
        "openai/chat/completions model=gemini-3.5-flash-lite at /app/services/x.py"
    )
    msg = _friendly_error(leaky)
    for secret in ("googleapis.com", "gemini-3.5", "/app/services", "http"):
        assert secret not in msg, f"error message leaked {secret!r}"


def test_quota_error_still_gives_a_useful_message():
    from app.services.pipeline import _friendly_error

    msg = _friendly_error(RuntimeError("429 RESOURCE_EXHAUSTED"))
    assert "quota" in msg.lower()


def test_missing_key_error_does_not_reveal_configuration():
    from app.services.pipeline import _friendly_error

    msg = _friendly_error(ValueError("LLM_API_KEY and LLM_MODEL must be set"))
    assert "LLM_API_KEY" not in msg


def test_unknown_debate_id_is_a_flat_404(client):
    r = client.get("/debate/../../etc/passwd/verdict")
    assert r.status_code == 404


# --- memory bounds ----------------------------------------------------------

def test_debate_store_evicts_and_protects_demos():
    """Unbounded growth was a memory-exhaustion path; the seeded demo corpus
    must survive it, or traffic would quietly empty the deployed demo."""
    debate_store.load_demos()
    protected = set(debate_store._protected)
    for i in range(debate_store.MAX_USER_DEBATES + 200):
        debate_store.create(f"claim {i}", 1)

    assert debate_store.count() <= debate_store.MAX_USER_DEBATES + len(protected)
    assert all(debate_store.get(pid) is not None for pid in protected)


# --- headers ----------------------------------------------------------------

def test_security_headers_present(client):
    h = client.get("/health").headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in h["content-security-policy"]


def test_health_does_not_leak_the_api_key(client):
    body = client.get("/health").text
    assert "llm_configured" in body
    from app.core.config import settings

    if settings.llm_api_key:
        assert settings.llm_api_key not in body
