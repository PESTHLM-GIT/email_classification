"""Minimal regelmotor - fångar bara fall med i praktiken noll tvetydighet:
uppenbar skräppost och mejl från kända AI-leverantörers domäner. Allt annat,
inklusive hela gränsdragningen mellan Reklam och AI-relaterat (som kräver
att faktiskt läsa innehållet, inte bara leta nyckelord), avgörs av Claude.

Tidigare försökte regelmotorn även gissa Reklam vs. AI-relaterat på
nyckelord - det blev både svårt att underhålla och sämre än att bara fråga
modellen, som ändå redan får hela mejlinnehållet (se models.py).
"""

from dataclasses import dataclass
from typing import Optional

from .config import CATEGORY_AI, CATEGORY_SPAM
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
        return RuleMatch(CATEGORY_SPAM, confidence, f"{spam_hits} skräpmejl-signalord i ämne/innehåll")

    if any(domain in sender for domain in AI_DOMAINS):
        return RuleMatch(CATEGORY_AI, 0.9, "avsändardomän kopplad till AI")

    return None
