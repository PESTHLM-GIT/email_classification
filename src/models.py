from dataclasses import dataclass
from typing import Any, Dict

# Hur mycket av mejlets faktiska innehåll (inte bara Graphs korta
# auto-genererade bodyPreview på ~255 tecken) som skickas vidare till
# regelmotorn/Claude. Innehåll som klipps bort ses aldrig av klassificeraren -
# högre värde ger bättre täckning men fler tokens (=högre kostnad) per mejl.
BODY_MAX_CHARS = 3000


@dataclass
class EmailMessage:
    id: str
    subject: str
    sender_name: str
    sender_address: str
    body_preview: str
    received_at: str
    mailbox: str
    has_list_unsubscribe: bool = False

    @classmethod
    def from_graph_message(cls, message: Dict[str, Any], mailbox: str) -> "EmailMessage":
        sender = (message.get("from") or {}).get("emailAddress", {}) or {}
        headers = {
            h["name"].lower(): h.get("value", "")
            for h in (message.get("internetMessageHeaders") or [])
        }
        body_content = ((message.get("body") or {}).get("content") or "").strip()
        return cls(
            id=message["id"],
            subject=message.get("subject", "") or "",
            sender_name=sender.get("name", "") or "",
            sender_address=(sender.get("address", "") or "").lower(),
            body_preview=body_content[:BODY_MAX_CHARS],
            received_at=message.get("receivedDateTime", "") or "",
            mailbox=mailbox,
            has_list_unsubscribe="list-unsubscribe" in headers,
        )


@dataclass
class ClassificationResult:
    message_id: str
    category: str
    confidence: float
    method: str  # "rule" eller "llm"
    reasoning: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
