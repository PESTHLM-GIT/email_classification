from dataclasses import dataclass
from typing import Any, Dict


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
        return cls(
            id=message["id"],
            subject=message.get("subject", "") or "",
            sender_name=sender.get("name", "") or "",
            sender_address=(sender.get("address", "") or "").lower(),
            body_preview=message.get("bodyPreview", "") or "",
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
