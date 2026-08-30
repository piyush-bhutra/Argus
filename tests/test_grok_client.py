import pytest
from unittest.mock import patch, MagicMock
from openai import RateLimitError, OpenAIError
import httpx


@pytest.fixture(autouse=True)
def _reset_client():
    """Ensure the lazily-built client cache never leaks between tests."""
    import app.services.grok_client as gc
    gc._client = None
    yield
    gc._client = None


@pytest.fixture
def mock_settings(monkeypatch):
    import app.core.config as config
    monkeypatch.setattr(config.settings, "llm_api_key", "fake-key")
    monkeypatch.setattr(config.settings, "llm_model", "fake-model")


def test_settings_empty_raises(monkeypatch):
    """With no key/model configured, calling call_grok raises ValueError at point of use."""
    import app.core.config as config
    from app.services.grok_client import call_grok

    monkeypatch.setattr(config.settings, "llm_api_key", "")
    monkeypatch.setattr(config.settings, "llm_model", "")

    with pytest.raises(ValueError, match="LLM_API_KEY and LLM_MODEL must be set"):
        call_grok("User prompt", "System prompt")


@patch("app.services.grok_client._get_client")
def test_call_grok_returns_content(mock_get_client, mock_settings):
    from app.services.grok_client import call_grok

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="Mocked response"))]
    mock_get_client.return_value.chat.completions.create.return_value = mock_response

    result = call_grok("User prompt", "System prompt")
    assert result == "Mocked response"


@patch("app.services.grok_client._get_client")
def test_call_grok_correct_args(mock_get_client, mock_settings):
    from app.services.grok_client import call_grok

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]
    mock_client = mock_get_client.return_value
    mock_client.chat.completions.create.return_value = mock_response

    call_grok("User prompt", "System prompt")

    mock_client.chat.completions.create.assert_called_once_with(
        model="fake-model",
        messages=[
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "User prompt"},
        ],
    )


@patch("app.services.grok_client._get_client")
def test_call_grok_raises_other_errors(mock_get_client, mock_settings):
    from app.services.grok_client import call_grok

    mock_get_client.return_value.chat.completions.create.side_effect = OpenAIError(
        "Some other error"
    )

    with pytest.raises(OpenAIError, match="Some other error"):
        call_grok("User prompt", "System prompt")


@patch("app.services.grok_client.time.sleep")
@patch("app.services.grok_client._get_client")
def test_call_grok_retries_on_429(mock_get_client, mock_sleep, mock_settings):
    from app.services.grok_client import call_grok

    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="Success after 429"))]

    fake_request = httpx.Request("POST", "https://api.cerebras.ai/v1/chat/completions")
    fake_response = httpx.Response(429, request=fake_request)
    rate_limit_error = RateLimitError("Rate limited", response=fake_response, body=None)

    mock_get_client.return_value.chat.completions.create.side_effect = [
        rate_limit_error,
        mock_response,
    ]

    result = call_grok("User prompt", "System prompt")

    assert result == "Success after 429"
    assert mock_get_client.return_value.chat.completions.create.call_count == 2
    mock_sleep.assert_called_once_with(8)


@patch("app.services.grok_client.time.sleep")
@patch("app.services.grok_client._get_client")
def test_call_grok_daily_quota_fails_fast(mock_get_client, mock_sleep, mock_settings):
    """A per-day quota error must NOT be retried."""
    from app.services.grok_client import call_grok

    fake_request = httpx.Request("POST", "https://example/v1/chat/completions")
    fake_response = httpx.Response(429, request=fake_request)
    err = RateLimitError(
        "quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier",
        response=fake_response,
        body=None,
    )
    mock_get_client.return_value.chat.completions.create.side_effect = err

    with pytest.raises(RateLimitError):
        call_grok("User prompt", "System prompt")

    assert mock_get_client.return_value.chat.completions.create.call_count == 1
    mock_sleep.assert_not_called()
