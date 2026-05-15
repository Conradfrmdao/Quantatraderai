from __future__ import annotations

from types import SimpleNamespace


def test_bedrock_provider_uses_anthropic_bedrock_client(monkeypatch):
    import src.agent.providers.bedrock_provider as bp
    from src.agent.providers.bedrock_provider import BedrockProvider

    captured_client_kwargs: dict = {}
    captured_create_kwargs: dict = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured_create_kwargs.update(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="hold safely")],
                usage=SimpleNamespace(input_tokens=11, output_tokens=3),
                stop_reason="end_turn",
            )

    class FakeClient:
        def __init__(self, **kwargs):
            captured_client_kwargs.update(kwargs)
            self.messages = FakeMessages()

    monkeypatch.setitem(bp.CONFIG, "aws_region", "us-east-1")
    monkeypatch.setitem(bp.CONFIG, "aws_access_key_id", "AKIA_TEST")
    monkeypatch.setitem(bp.CONFIG, "aws_secret_access_key", "secret-test")
    monkeypatch.setitem(bp.CONFIG, "aws_session_token", "")
    monkeypatch.setitem(bp.CONFIG, "aws_profile", "")
    monkeypatch.setitem(bp.CONFIG, "enable_tool_calling", True)
    monkeypatch.setitem(bp.CONFIG, "thinking_enabled", False)
    monkeypatch.setattr(bp.anthropic, "AnthropicBedrock", FakeClient)
    monkeypatch.setattr(bp.anthropic, "AsyncAnthropicBedrock", FakeClient)

    provider = BedrockProvider(model="us.anthropic.claude-haiku-4-5-20251001-v1:0")
    result = provider.complete(
        system="You are safe.",
        messages=[{"role": "user", "content": "Return JSON"}],
        max_tokens=64,
        tools=[{"name": "fetch_indicator", "input_schema": {"type": "object"}}],
    )

    assert captured_client_kwargs["aws_region"] == "us-east-1"
    assert captured_client_kwargs["aws_access_key"] == "AKIA_TEST"
    assert captured_client_kwargs["aws_secret_key"] == "secret-test"
    assert captured_create_kwargs["model"] == "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    assert captured_create_kwargs["max_tokens"] == 64
    assert captured_create_kwargs["tools"][0]["name"] == "fetch_indicator"
    assert result.content == "hold safely"
    assert result.input_tokens == 11
    assert result.output_tokens == 3
    assert result.stop_reason == "end_turn"


def test_provider_factory_supports_bedrock(monkeypatch):
    import src.agent.providers.bedrock_provider as bp
    from src.agent.providers import factory

    class FakeClient:
        def __init__(self, **kwargs):
            self.messages = SimpleNamespace()

    monkeypatch.setitem(bp.CONFIG, "aws_region", "us-east-1")
    monkeypatch.setattr(bp.anthropic, "AnthropicBedrock", FakeClient)
    monkeypatch.setattr(bp.anthropic, "AsyncAnthropicBedrock", FakeClient)

    provider = factory.get_provider("bedrock", model="us.anthropic.claude-sonnet-4-6")

    assert provider.name == "bedrock"
    assert provider.model == "us.anthropic.claude-sonnet-4-6"
