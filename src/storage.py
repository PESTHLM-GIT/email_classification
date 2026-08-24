"""Sparar klassificeringsresultat och webhook-prenumerationer i Azure Table
Storage - samma lagringskonto som Function App redan kräver, så ingen extra
Azure-resurs behöver provisioneras för att få ut resultatet som en tabell.
"""

import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from azure.data.tables import TableServiceClient

from .models import ClassificationResult, EmailMessage

CLASSIFICATIONS_TABLE = "Classifications"
SUBSCRIPTIONS_TABLE = "Subscriptions"


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
