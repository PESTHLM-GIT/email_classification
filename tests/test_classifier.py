from unittest.mock import patch

from src.classifier import classify
from src.config import CATEGORY_ADS, CATEGORY_PERSONAL
from src.models import ClassificationResult

from .test_rules import make_email


def test_short_circuits_on_high_confidence_rule():
    email = make_email(
        subject="REA - 50% rabatt hela helgen",
        sender_address="nyhetsbrev@butik.se",
        has_list_unsubscribe=True,
    )

    with patch("src.classifier.classify_with_llm") as mock_llm:
        result = classify(email)

    mock_llm.assert_not_called()
    assert result.category == CATEGORY_ADS
    assert result.method == "rule"


def test_falls_back_to_llm_for_ambiguous_email():
    email = make_email(subject="Hej, hur går det?", body_preview="Vi borde ses snart!")
    fake_result = ClassificationResult(
        message_id=email.id,
        category=CATEGORY_PERSONAL,
        confidence=0.92,
        method="llm",
        reasoning="Personlig ton, riktat till en specifik mottagare",
    )

    with patch("src.classifier.classify_with_llm", return_value=fake_result) as mock_llm:
        result = classify(email)

    mock_llm.assert_called_once()
    assert result.category == CATEGORY_PERSONAL
    assert result.method == "llm"


def test_low_confidence_rule_hint_is_passed_to_llm():
    # En enda skräpmejl-signal ger confidence 0.8, dvs under short-circuit-
    # tröskeln (0.85) - ska alltså skickas vidare till Claude som en hint.
    email = make_email(subject="Prova vårt casino ikväll", body_preview="Nya spel varje vecka")
    fake_result = ClassificationResult(
        message_id=email.id, category=CATEGORY_ADS, confidence=0.7, method="llm", reasoning="Marknadsföring"
    )

    with patch("src.classifier.classify_with_llm", return_value=fake_result) as mock_llm:
        classify(email)

    _, kwargs = mock_llm.call_args
    assert kwargs.get("rule_hint") is not None
