from __future__ import annotations

from unittest.mock import patch

from src.llm.provider import LLMProvider, clear_price_fallback_cache


def test_estimate_cost_usd_deepseek_via_genai_prices() -> None:
    cost = LLMProvider.estimate_cost_usd(
        "deepseek:deepseek-v4-flash",
        tokens_in=1_000_000,
        tokens_out=1_000_000,
    )
    assert cost > 0.0


def test_estimate_cost_usd_uses_yaml_fallback_when_genai_prices_missing() -> None:
    clear_price_fallback_cache()
    with patch("src.llm.provider.calc_price", side_effect=LookupError("unknown")):
        cost = LLMProvider.estimate_cost_usd(
            "deepseek:deepseek-v4-flash",
            tokens_in=1_000_000,
            tokens_out=1_000_000,
        )
    # settings.yaml: input 0.14 + output 0.28 per MTok
    assert cost == 0.42


def test_estimate_cost_usd_fireworks_pro_fallback_uses_serverless_rates() -> None:
    clear_price_fallback_cache()
    with patch("src.llm.provider.calc_price", side_effect=LookupError("unknown")):
        cost = LLMProvider.estimate_cost_usd(
            "fireworks:accounts/fireworks/models/deepseek-v4-pro",
            tokens_in=1_000_000,
            tokens_out=1_000_000,
        )
    # settings.yaml Fireworks serverless: input 1.74 + output 3.48 per MTok
    assert cost == 5.22
