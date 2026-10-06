"""DeepSeek is the only live LLM; no other provider is a fallback."""

from __future__ import annotations

from app import llm


def test_deepseek_is_the_only_provider(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test")
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    info = llm.provider_info()
    assert info is not None
    assert info["name"] == "deepseek"
    assert info["source"] == "deepseek"
    assert info["model"] == "deepseek-v4-flash"
    assert llm.is_enabled()
    assert llm.llm_source() == "deepseek"


def test_vision_off_by_default(monkeypatch) -> None:
    """deepseek-v4-flash is text-only — an image_url part 400s, so vision stays
    off unless explicitly pointed at a vision-capable endpoint."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test")
    monkeypatch.delenv("DEEPSEEK_VISION", raising=False)
    assert llm.vision_enabled() is False
    assert llm.vision_json("s", "u", "/nonexistent.jpg") is None

    monkeypatch.setenv("DEEPSEEK_VISION", "1")
    assert llm.vision_enabled() is True

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert llm.vision_enabled() is False


def test_xai_key_is_ignored(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    assert llm.provider_info() is None
    assert llm.is_enabled() is False
    assert llm.llm_source() == "deterministic"


def test_disabled_without_deepseek_key(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    assert llm.provider_info() is None
    assert llm.is_enabled() is False
    assert llm.llm_source() == "deterministic"


def test_chat_completions_posts_to_deepseek(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-test")
    captured: dict = {}

    class _Resp:
        def read(self) -> bytes:
            return b'{"choices":[{"message":{"content":"ok"}}]}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _urlopen(req, timeout=30):
        captured["url"] = req.full_url
        captured["auth"] = req.get_header("Authorization")
        return _Resp()

    monkeypatch.setattr("app.llm.request.urlopen", _urlopen)
    parsed = llm.chat_completions({"messages": [{"role": "user", "content": "hi"}]})
    assert parsed is not None
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["auth"] == "Bearer ds-test"


def test_grok_helpers_are_gone() -> None:
    """Live code must not expose a Grok/xAI-named API."""
    import inspect
    from datetime import datetime, timezone

    from app import agent as agent_mod
    from app import llm as llm_mod
    from app.schemas import TechnicalEvaluation

    src = inspect.getsource(llm_mod)
    assert "api.x.ai" not in src
    assert "XAI_" not in src
    for name in ("grok_chat", "grok_json", "grok_vision_json"):
        assert not hasattr(llm_mod, name)
    assert not hasattr(agent_mod, "dispatch_grok")
    assert callable(agent_mod.dispatch_llm)

    ev = TechnicalEvaluation(
        rfq_no="RFQ-1",
        quote_id="Q-1",
        vendor="Test",
        source="grok",  # type: ignore[arg-type]
        evaluated_at=datetime.now(timezone.utc),
    )
    assert ev.source == "deepseek"
