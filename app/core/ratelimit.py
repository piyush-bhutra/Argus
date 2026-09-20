"""Per-client rate limiting for the debate endpoint.

Why this exists: `POST /debate/start` is unauthenticated and each call spends
roughly six LLM requests against the operator's API key. Without a limit the
endpoint is an open LLM proxy — anyone who finds the URL can drain a free-tier
quota in a loop, or use the key to generate arbitrary text through the claim
field. That is the highest-impact issue in a public deployment of this app.

Deliberately dependency-free and in-process: a fixed-window counter in a dict.
The app already keeps debate state in process memory, so a shared store would be
the only distributed component in the system.

    # ponytail: per-process fixed window. On multiple instances each gets its
    # own budget, and a window boundary allows a short 2x burst. Move to Redis
    # with a sliding window only if the app is ever scaled out.
"""
import threading
import time
from collections import deque
from typing import Deque, Dict

from app.core.config import settings

# Upper bound on distinct callers tracked at once. Beyond this the limiter
# sweeps rather than growing; see allow().
_MAX_TRACKED_KEYS = 10_000


class RateLimiter:
    """Fixed-window request counter keyed by client identity."""

    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: Dict[str, Deque[float]] = {}
        # BackgroundTasks and the request path can touch this from different
        # threads; a plain dict mutation race would drop or double-count hits.
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        """True if this caller may proceed; records the hit when it does."""
        if self.max_requests <= 0:      # 0 disables the endpoint entirely
            return False

        now = time.monotonic() if now is None else now
        cutoff = now - self.window_seconds

        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= self.max_requests:
                return False

            hits.append(now)

            # Bounded memory: an attacker rotating source addresses would
            # otherwise grow this dict without limit, turning the rate limiter
            # itself into the denial-of-service vector.
            #
            # Entries expire lazily per key, so "deque is empty" is almost never
            # true here — a key with one stale hit still holds it until that
            # same key is seen again. Sweep on the LAST hit instead: anything
            # whose newest hit is outside the window would be discarded on its
            # next access anyway.
            if len(self._hits) > _MAX_TRACKED_KEYS:
                for k in [k for k, v in self._hits.items() if not v or v[-1] <= cutoff]:
                    self._hits.pop(k, None)
                # Still oversized means a genuine flood of live callers rather
                # than stale entries; drop the oldest to stay bounded. They get
                # a fresh budget, which is the right way to fail here — a
                # rate limiter must not become the memory exhaustion it prevents.
                while len(self._hits) > _MAX_TRACKED_KEYS:
                    self._hits.pop(next(iter(self._hits)), None)

            return True

    def retry_after(self, key: str, now: float | None = None) -> int:
        """Whole seconds until this caller's oldest hit leaves the window."""
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits.get(key)
            if not hits:
                return 0
            return max(1, int(hits[0] + self.window_seconds - now) + 1)


def client_key(request) -> str:
    """Best-effort caller identity.

    Behind a proxy the socket address is the proxy's, so the leftmost
    X-Forwarded-For entry is used when the operator has declared that the app
    sits behind a trusted proxy. That header is client-controlled and trivially
    spoofed, so it is honoured ONLY when TRUST_PROXY_HEADERS is set — otherwise
    anyone could bypass the limit by varying a header.
    """
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


debate_limiter = RateLimiter(
    max_requests=settings.debate_rate_limit,
    window_seconds=settings.debate_rate_window_seconds,
)
