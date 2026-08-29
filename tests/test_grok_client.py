import pytest
from unittest.mock import patch, MagicMock
from openai import RateLimitError, OpenAIError
import httpx

def test_settings_empty_raises(monkeypatch):
    import sys
    from importlib import reload
    import app.core.config as config
    
    # We must patch the environment so that when `Settings()` is instantiated
    # it picks up empty values
    monkeypatch.setattr(config.settings, "llm_api_key", "")
    monkeypatch.setattr(config.settings, "llm_model", "")
    
    with pytest.raises(ValueError, match="LLM_API_KEY and LLM_MODEL must be set"):
        # The ValueError is raised in grok_client when it's imported
        if "app.services.grok_client" in sys.modules:
            del sys.modules["app.services.grok_client"]
        import app.services.grok_client


@pytest.fixture
def mock_settings(monkeypatch):
    import app.core.config as config
    monkeypatch.setattr(config.settings, "llm_api_key", "fake-key")
    monkeypatch.setattr(config.settings, "llm_model", "fake-model")

@patch("app.services.grok_client.client")
def test_call_grok_returns_content(mock_client, mock_settings):
    from app.services.grok_client import call_grok
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="Mocked response"))]
    mock_client.chat.completions.create.return_value = mock_response
    
    result = call_grok("User prompt", "System prompt")
    assert result == "Mocked response"

@patch("app.services.grok_client.client")
def test_call_grok_correct_args(mock_client, mock_settings):
    from app.services.grok_client import call_grok
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="ok"))]
    mock_client.chat.completions.create.return_value = mock_response
    
    call_grok("User prompt", "System prompt")
    
    mock_client.chat.completions.create.assert_called_once_with(
        model="fake-model",
        messages=[
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "User prompt"}
        ]
    )

@patch("app.services.grok_client.client")
def test_call_grok_raises_other_errors(mock_client, mock_settings):
    from app.services.grok_client import call_grok
    
    mock_client.chat.completions.create.side_effect = OpenAIError("Some other error")
    
    with pytest.raises(OpenAIError, match="Some other error"):
        call_grok("User prompt", "System prompt")

@patch("app.services.grok_client.time.sleep")
@patch("app.services.grok_client.client")
def test_call_grok_retries_on_429(mock_client, mock_sleep, mock_settings):
    from app.services.grok_client import call_grok
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="Success after 429"))]
    
    fake_request = httpx.Request("POST", "https://api.cerebras.ai/v1/chat/completions")
    fake_response = httpx.Response(429, request=fake_request)
    rate_limit_error = RateLimitError("Rate limited", response=fake_response, body=None)
    
    mock_client.chat.completions.create.side_effect = [
        rate_limit_error,
        mock_response
    ]
    
    result = call_grok("User prompt", "System prompt")
    
    assert result == "Success after 429"
    assert mock_client.chat.completions.create.call_count == 2
    mock_sleep.assert_called_once_with(12)
