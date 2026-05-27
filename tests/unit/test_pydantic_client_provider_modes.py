from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import NativeOutput

from src.llm import pydantic_client as mod
from src.llm.pydantic_client import _model_settings


@dataclass
class _FakeResult:
    output: object


class _FakeAgent:
    captured_output_type: object | None = None

    def __init__(self, _model: str, *, output_type: object, **_kwargs: object) -> None:
        _FakeAgent.captured_output_type = output_type

    async def run(self, _prompt: object, *, model_settings: object) -> _FakeResult:  # noqa: ARG002
        return _FakeResult(output={"ok": True})


async def test_complete_uses_native_output_for_google(monkeypatch) -> None:
    monkeypatch.setattr(mod, "Agent", _FakeAgent)
    client = mod.PydanticAIClient()
    await client.complete(
        "x",
        model="google:gemini-2.5-flash",
        temperature=0.1,
        json_schema={"type": "object"},
    )
    assert isinstance(_FakeAgent.captured_output_type, NativeOutput)


def test_model_settings_disables_thinking_for_deepseek_structured() -> None:
    settings = _model_settings(
        temperature=0.1,
        timeout=60.0,
        model="deepseek:deepseek-v4-flash",
        structured=True,
    )
    assert settings.get("extra_body") == {"thinking": {"type": "disabled"}}


def test_model_settings_keeps_thinking_for_deepseek_plain_text() -> None:
    settings = _model_settings(
        temperature=0.1,
        timeout=60.0,
        model="deepseek:deepseek-v4-flash",
        structured=False,
    )
    assert settings.get("extra_body") is None


async def test_complete_uses_structured_dict_for_non_google(monkeypatch) -> None:
    monkeypatch.setattr(mod, "Agent", _FakeAgent)
    client = mod.PydanticAIClient()
    await client.complete(
        "x",
        model="deepseek:deepseek-v4-flash",
        temperature=0.1,
        json_schema={"type": "object"},
    )
    assert _FakeAgent.captured_output_type is not None
    assert not isinstance(_FakeAgent.captured_output_type, NativeOutput)
