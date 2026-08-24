"""Snabb, billig regelmotor som fångar uppenbara fall innan Claude behöver fråga.

En träff med hög confidence (se RULE_SHORT_CIRCUIT_THRESHOLD i config.py)
används direkt. En träff med lägre confidence skickas vidare som en "hint"
till LLM-klassificeraren, som gör den slutgiltiga bedömningen.
"""

from dataclasses import dataclass
from typing import Optional

from .config import CATEGORY_ADS, CATEGORY_AI, CATEGORY_SPAM
from .models import EmailMessage


@dataclass
class RuleMatch:
    category: str
    confidence: float
    reason: str


SPAM_KEYWORDS = [
    "du har vunnit", "har vunnit ett pris", "gratis pengar", "klicka här för att lösa in",
    "viagra", "casino", "lånelöfte utan uppgifter", "nigeria", "inheritance",
    "claim your prize", "you have won", "wire transfer", "bitcoin giveaway",
    "crypto giveaway", "act now", "urgent action required", "verify your account immediately",
]

AD_KEYWORDS = [
    "rea", "rabatt", "kampanj", "nyhetsbrev", "erbjudande", "% rabatt", "black friday",
    "släpp", "nyhet i sortimentet", "boka nu", "sista chansen", "medlemserbjudande",
    "sale", "discount", "unsubscribe", "newsletter",
]
AD_SENDER_HINTS = ["no-reply", "noreply", "newsletter", "nyhetsbrev", "marketing@", "info@"]

AI_KEYWORDS = [
    "artificial intelligence", "generativ ai", "maskininlärning", "machine learning",
    "chatbot", "large language model", "llm", "gpt", "copilot", " ai ", "ai-modell",
    "neural network", "prompt engineering",
]
AI_DOMAINS = [
    "openai.com", "anthropic.com", "claude.ai", "google.ai", "deepmind.com",
    "huggingface.co", "microsoft.com", "mistral.ai", "cohere.com", "perplexity.ai",
]


def evaluate(email: EmailMessage) -> Optional[RuleMatch]:
    subject = (email.subject or "").lower()
    sender = (email.sender_address or "").lower()
    preview = (email.body_preview or "").lower()
    text = f"{subject} {preview}"

    spam_hits = sum(1 for kw in SPAM_KEYWORDS if kw in text)
    if spam_hits >= 1:
        confidence = min(0.6 + 0.2 * spam_hits, 0.95)
        return RuleMatch(CATEGORY_SPAM, confidence, f"{spam_hits} skräpmejl-signalord i ämne/förhandsvisning")

    ai_domain_hit = any(domain in sender for domain in AI_DOMAINS)
    ai_kw_hits = sum(1 for kw in AI_KEYWORDS if kw in text)
    if ai_domain_hit or ai_kw_hits >= 2:
        confidence = 0.9 if ai_domain_hit else min(0.5 + 0.15 * ai_kw_hits, 0.9)
        reason = "avsändardomän kopplad till AI" if ai_domain_hit else f"{ai_kw_hits} AI-relaterade nyckelord"
        return RuleMatch(CATEGORY_AI, confidence, reason)

    ad_kw_hits = sum(1 for kw in AD_KEYWORDS if kw in text)
    ad_sender_hit = any(hint in sender for hint in AD_SENDER_HINTS)
    if email.has_list_unsubscribe and (ad_kw_hits >= 1 or ad_sender_hit):
        return RuleMatch(CATEGORY_ADS, 0.9, "List-Unsubscribe-header + reklamsignal")
    if ad_kw_hits >= 2 or (ad_sender_hit and ad_kw_hits >= 1):
        confidence = min(0.5 + 0.15 * ad_kw_hits, 0.85)
        return RuleMatch(CATEGORY_ADS, confidence, f"{ad_kw_hits} reklamnyckelord")

    return None
