"""Orkestrerar hybrid-klassificeringen: snabba regler först, Claude för oklara fall."""

from typing import Optional

import anthropic

from . import rules
from .config import RULE_SHORT_CIRCUIT_THRESHOLD
from .llm_classifier import classify_with_llm
from .models import ClassificationResult, EmailMessage


def classify(
    email: EmailMessage, anthropic_client: Optional[anthropic.Anthropic] = None
) -> ClassificationResult:
    match = rules.evaluate(email)

    if match and match.confidence >= RULE_SHORT_CIRCUIT_THRESHOLD:
        return ClassificationResult(
            message_id=email.id,
            category=match.category,
            confidence=match.confidence,
            method="rule",
            reasoning=match.reason,
        )

    hint = f"{match.category} (confidence {match.confidence:.2f}, {match.reason})" if match else None
    return classify_with_llm(email, rule_hint=hint, client=anthropic_client)
