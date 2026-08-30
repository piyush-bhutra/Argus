"""
PRD §13 - LLM API wrapper (Cerebras via the OpenAI SDK).

The client is created lazily on the first call so that importing this module
(and everything downstream: orchestrator, routes, the FastAPI app) never fails
just because a key is missing. Validation happens at the point of use.
"""
import time
from openai import OpenAI, RateLimitError, OpenAIError
from app.core.config import settings
from app.core.logger import logger

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
        )
    return _client


def call_grok(prompt: str, role_system_prompt: str) -> str:
    """
    Call the Cerebras chat-completions API using the OpenAI SDK.
    Includes rate-limit retry logic and logging.
    """
    client = _get_client()

    messages = [
        {"role": "system", "content": role_system_prompt},
        {"role": "user", "content": prompt},
    ]

    logger.info(f"Outgoing prompt (System): {role_system_prompt}")
    logger.info(f"Outgoing prompt (User): {prompt}")

    max_retries = 3
    retry_delay = 12

    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
            )
            content = response.choices[0].message.content
            logger.info(f"Returned response: {content}")
            return content
        except RateLimitError as e:
            if attempt < max_retries:
                logger.warning(
                    f"Rate limited (429). Retrying in {retry_delay} seconds..."
                )
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                logger.error(
                    f"Rate limit exceeded after {max_retries} retries. "
                    f"Raising error: {type(e).__name__} - {e}"
                )
                raise
        except OpenAIError as e:
            logger.error(f"API Error encountered: {type(e).__name__} - {e}")
            raise
