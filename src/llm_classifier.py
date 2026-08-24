"""LLM-baserad klassificering via Claude för mejl som regelmotorn är osäker på."""

import os
from typing import Optional

import anthropic

from .config import (
    CATEGORIES,
    CATEGORY_ADS,
    CATEGORY_AI,
    CATEGORY_PERSONAL,
    CATEGORY_SPAM,
    CLAUDE_MODEL,
)
from .models import ClassificationResult, EmailMessage

SYSTEM_PROMPT = f"""Du klassificerar inkommande mejl till en privat/jobb-brevlåda i exakt en av
fyra kategorier:

- "{CATEGORY_PERSONAL}": Personlig eller genuin affärskorrespondens mellan människor
  (kollegor, kunder, vänner, familj). Skrivet till mottagaren specifikt, inte massutskick.
- "{CATEGORY_ADS}": Marknadsföring, nyhetsbrev, kampanjer, erbjudanden och rabatter från
  företag, även om avsändaren är legitim.
- "{CATEGORY_AI}": Mejl vars huvudsakliga ämne är AI/maskininlärning – t.ex. produktnyheter,
  fakturor eller uppdateringar från AI-leverantörer (OpenAI, Anthropic, etc.), nyhetsbrev om
  AI, eller personlig korrespondens som handlar om ett AI-projekt.
- "{CATEGORY_SPAM}": Oönskad skräppost, bedrägeriförsök (phishing), eller mejl utan legitimt
  affärssyfte.

Om ett mejl passar in på flera kategorier, prioritera i denna ordning: {CATEGORY_SPAM} >
{CATEGORY_AI} > {CATEGORY_ADS} > {CATEGORY_PERSONAL} (dvs. ett reklammejl om ett AI-verktyg
klassas som "{CATEGORY_AI}", inte "{CATEGORY_ADS}").

Använd alltid classify_email-verktyget för att svara."""

CLASSIFY_TOOL = {
    "name": "classify_email",
    "description": "Klassificera ett e-postmeddelande i exakt en av de fördefinierade kategorierna.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": CATEGORIES},
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "Hur säker klassificeringen är, 0-1.",
            },
            "reasoning": {
                "type": "string",
                "description": "Kort motivering (max en mening) på svenska.",
            },
        },
        "required": ["category", "confidence", "reasoning"],
    },
}


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def classify_with_llm(
    email: EmailMessage,
    rule_hint: Optional[str] = None,
    client: Optional[anthropic.Anthropic] = None,
) -> ClassificationResult:
    client = client or _client()

    hint_text = (
        f"\n\nRegelmotorns preliminära gissning (kan vara fel, väg in men lita inte blint på den): {rule_hint}"
        if rule_hint
        else ""
    )

    user_content = (
        f"Avsändare: {email.sender_name} <{email.sender_address}>\n"
        f"Ämne: {email.subject}\n"
        f"Utdrag av innehåll:\n{email.body_preview}"
        f"{hint_text}"
    )

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        system=SYSTEM_PROMPT,
        tools=[CLASSIFY_TOOL],
        tool_choice={"type": "tool", "name": "classify_email"},
        messages=[{"role": "user", "content": user_content}],
    )

    tool_use = next(block for block in response.content if block.type == "tool_use")
    result = tool_use.input

    return ClassificationResult(
        message_id=email.id,
        category=result["category"],
        confidence=float(result["confidence"]),
        method="llm",
        reasoning=result["reasoning"],
    )
