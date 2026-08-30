"""
PRD §13 - LLM API wrapper (OpenAI-SDK-compatible; currently Google Gemini).

The client is created lazily on the first call so that importing this module
(and everything downstream: orchestrator, routes, the FastAPI app) never fails
just because a key is missing. Validation happens at the point of use.
"""
import time
from openai import OpenAI, RateLimitError, OpenAIError
from app.core.config import settings
from app.core.logger import logger

# Our own retry policy is below; don't let the SDK add a second, hidden layer.
_SDK_MAX_RETRIES = 0
_REQUEST_TIMEOUT = 60.0

# Transient (per-minute) 429s: retry a couple of times, briefly.
_MAX_RETRIES = 2
_RETRY_DELAY = 8

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """Validate config and build (once) the OpenAI-compatible client."""
    global _client
    if not settings.llm_api_key or not settings.llm_model:
        raise ValueError(
            "LLM_API_KEY and LLM_MODEL must be set in the environment or .env file."
        )
    if _client is None:
        _client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            max_retries=_SDK_MAX_RETRIES,
            timeout=_REQUEST_TIMEOUT,
        )
    return _client


def _is_daily_quota_exhausted(err: Exception) -> bool:
    """A per-day free-tier quota won't recover in seconds — don't retry it."""
    text = str(err)
    return (
        "PerDayPerProject" in text
        or "GenerateRequestsPerDay" in text
        or "per day" in text.lower()
    )


def call_grok(prompt: str, role_system_prompt: str) -> str:
    """
    Call the chat-completions API using the OpenAI SDK.
    Retries briefly on transient rate limits; fails fast on daily-quota exhaustion.
    """
    client = _get_client()

    messages = [
        {"role": "system", "content": role_system_prompt},
        {"role": "user", "content": prompt},
    ]

    logger.info(f"Outgoing prompt (System): {role_system_prompt}")
    logger.info(f"Outgoing prompt (User): {prompt}")

    delay = _RETRY_DELAY

    for attempt in range(_MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
            )
            content = response.choices[0].message.content
            logger.info(f"Returned response: {content}")
            return content
        except RateLimitError as e:
            if _is_daily_quota_exhausted(e):
                logger.error(
                    "Daily free-tier quota exhausted for this model — not retrying. "
                    "Switch LLM_MODEL / provider, or wait for the quota to reset."
                )
                raise
            if attempt < _MAX_RETRIES:
                logger.warning(f"Rate limited (429). Retrying in {delay}s...")
                time.sleep(delay)
                delay *= 2
            else:
                logger.error(
                    f"Rate limit persisted after {_MAX_RETRIES} retries: "
                    f"{type(e).__name__} - {e}"
                )
                raise
        except OpenAIError as e:
            logger.error(f"API Error encountered: {type(e).__name__} - {e}")
            raise
