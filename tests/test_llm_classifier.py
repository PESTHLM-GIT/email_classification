from types import SimpleNamespace
from unittest.mock import MagicMock

from src.config import CATEGORY_PERSONAL
from src.llm_classifier import classify_with_llm

from .test_rules import make_email


def _fake_response(category=CATEGORY_PERSONAL, confidence=0.9, input_tokens=500, output_tokens=50):
    tool_use_block = SimpleNamespace(
        type="tool_use",
        input={"category": category, "confidence": confidence, "reasoning": "Test"},
    )
    return SimpleNamespace(
        content=[tool_use_block],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def test_computes_cost_from_token_usage():
    email = make_email(subject="Hej, hur går det?", body_preview="Vi borde ses snart!")
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_response(input_tokens=1000, output_tokens=100)

    result = classify_with_llm(email, client=fake_client)

    assert result.input_tokens == 1000
    assert result.output_tokens == 100
    # claude-sonnet-5 pricing: $2/$10 per 1M tokens -> (1000*2 + 100*10) / 1_000_000
    assert result.cost_usd == (1000 * 2.00 + 100 * 10.00) / 1_000_000
