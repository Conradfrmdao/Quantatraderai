from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_groq_provider_uses_http_api_without_sdk_import():
    from src.agent.providers.groq_provider import GroqProvider

    fake_response = MagicMock()
    fake_response.raise_for_status.return_value = None
    fake_response.json.return_value = {
        "choices": [{
            "message": {"content": "hello from groq"},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 7,
        },
    }

    with patch("src.agent.providers.groq_provider.requests.post", return_value=fake_response) as post:
        provider = GroqProvider(model="llama-3.3-70b-versatile")
        result = provider.complete(
            system="You are helpful.",
            messages=[{"role": "user", "content": "Hi"}],
        )

    assert result.content == "hello from groq"
    assert result.input_tokens == 12
    assert result.output_tokens == 7
    assert post.called
