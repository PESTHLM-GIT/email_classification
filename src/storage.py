"""Sparar klassificeringsresultat och webhook-prenumerationer i Azure Table
Storage - samma lagringskonto som Function App redan kräver, så ingen extra
Azure-resurs behöver provisioneras för att få ut resultatet som en tabell.
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from azure.core.exceptions import ResourceNotFoundError
from azure.data.tables import TableServiceClient

from .config import FUNCTION_APP_MEMORY_GB
from .models import ClassificationResult, EmailMessage

CLASSIFICATIONS_TABLE = "Classifications"
SUBSCRIPTIONS_TABLE = "Subscriptions"
USAGE_TABLE = "Usage"


def _table_service() -> TableServiceClient:
    conn_str = os.environ["AzureWebJobsStorage"]
    return TableServiceClient.from_connection_string(conn_str)


def _get_or_create_table(service: TableServiceClient, name: str):
    service.create_table_if_not_exists(name)
    return service.get_table_client(name)


def save_classification(email: EmailMessage, result: ClassificationResult) -> None:
    table = _get_or_create_table(_table_service(), CLASSIFICATIONS_TABLE)
    entity = {
        "PartitionKey": email.mailbox,
        "RowKey": email.id,
        "subject": email.subject,
        "senderName": email.sender_name,
        "senderAddress": email.sender_address,
        "receivedAt": email.received_at,
        "category": result.category,
        "confidence": result.confidence,
        "method": result.method,
        "reasoning": result.reasoning,
        "inputTokens": result.input_tokens,
        "outputTokens": result.output_tokens,
        "costUsd": result.cost_usd,
        "classifiedAt": datetime.now(timezone.utc).isoformat(),
    }
    table.upsert_entity(entity)


def save_subscription(subscription_id: str, mailbox: str, resource: str, expiration: str) -> None:
    table = _get_or_create_table(_table_service(), SUBSCRIPTIONS_TABLE)
    table.upsert_entity(
        {
            "PartitionKey": "subscription",
            "RowKey": subscription_id,
            "mailbox": mailbox,
            "resource": resource,
            "expirationDateTime": expiration,
        }
    )


def list_subscriptions() -> List[Dict[str, Any]]:
    table = _get_or_create_table(_table_service(), SUBSCRIPTIONS_TABLE)
    return list(table.query_entities("PartitionKey eq 'subscription'"))


def delete_subscription(subscription_id: str) -> None:
    table = _get_or_create_table(_table_service(), SUBSCRIPTIONS_TABLE)
    table.delete_entity(partition_key="subscription", row_key=subscription_id)


def get_stats(recent_limit: int = 20) -> Dict[str, Any]:
    """Aggregerar allt i Classifications-tabellen för dashboarden: totaler,
    fördelning per kategori/metod, Claude-kostnad och senaste körningarna."""
    table = _get_or_create_table(_table_service(), CLASSIFICATIONS_TABLE)
    entities = list(table.list_entities())

    by_category: Dict[str, int] = {}
    by_method: Dict[str, int] = {}
    total_cost_usd = 0.0
    total_input_tokens = 0
    total_output_tokens = 0

    for entity in entities:
        category = entity.get("category", "Okänd")
        method = entity.get("method", "okänd")
        by_category[category] = by_category.get(category, 0) + 1
        by_method[method] = by_method.get(method, 0) + 1
        total_cost_usd += float(entity.get("costUsd", 0) or 0)
        total_input_tokens += int(entity.get("inputTokens", 0) or 0)
        total_output_tokens += int(entity.get("outputTokens", 0) or 0)

    # Fallande på mottagningstid, som inkorgen - inte på när vi klassificerade
    # det, vilket kan hamna i en annan ordning (t.ex. vid backfill).
    recent = sorted(entities, key=lambda e: e.get("receivedAt", ""), reverse=True)[:recent_limit]

    return {
        "total": len(entities),
        "byCategory": by_category,
        "byMethod": by_method,
        "totalCostUsd": total_cost_usd,
        "totalInputTokens": total_input_tokens,
        "totalOutputTokens": total_output_tokens,
        "recent": [
            {
                "id": e.get("RowKey", ""),
                "subject": e.get("subject", ""),
                "senderName": e.get("senderName", ""),
                "senderAddress": e.get("senderAddress", ""),
                "receivedAt": e.get("receivedAt", ""),
                "category": e.get("category", ""),
                "method": e.get("method", ""),
                "confidence": e.get("confidence", 0),
                "reasoning": e.get("reasoning", ""),
                "inputTokens": e.get("inputTokens", 0),
                "outputTokens": e.get("outputTokens", 0),
                "costUsd": e.get("costUsd", 0),
                "classifiedAt": e.get("classifiedAt", ""),
            }
            for e in recent
        ],
    }


def record_invocation(function_name: str, duration_seconds: float) -> None:
    """Räknar upp den ungefärliga Azure-förbrukningen (anrop + GB-sekunder)
    så dashboarden kan visa hur nära ni är den fria kvoten. Läs-ändra-skriv
    utan atomicitet - gott nog för denna volym, inte menat som exakt fakturering."""
    table = _get_or_create_table(_table_service(), USAGE_TABLE)
    try:
        entity = table.get_entity(partition_key="usage", row_key="totals")
    except ResourceNotFoundError:
        entity = {"PartitionKey": "usage", "RowKey": "totals", "invocationCount": 0, "gbSeconds": 0.0}

    entity["invocationCount"] = int(entity.get("invocationCount", 0) or 0) + 1
    entity["gbSeconds"] = float(entity.get("gbSeconds", 0.0) or 0.0) + duration_seconds * FUNCTION_APP_MEMORY_GB
    table.upsert_entity(entity)


def get_usage() -> Dict[str, Any]:
    table = _get_or_create_table(_table_service(), USAGE_TABLE)
    try:
        entity = table.get_entity(partition_key="usage", row_key="totals")
    except ResourceNotFoundError:
        return {"invocationCount": 0, "gbSeconds": 0.0}
    return {
        "invocationCount": int(entity.get("invocationCount", 0) or 0),
        "gbSeconds": float(entity.get("gbSeconds", 0.0) or 0.0),
    }
