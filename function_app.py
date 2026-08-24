"""Azure Functions-app (Python v2-modellen).

Endpoints:
- POST/GET /api/notifications  - tar emot Microsoft Graph webhook-notiser om nya mejl.
- POST /api/subscribe          - skapar (eller återskapar) webhook-prenumerationen.
- POST /api/classify-recent    - manuell/backfill-klassificering av senaste mejlen.
- (timer) renew_subscriptions  - förnyar aktiva prenumerationer var 6:e timme.
"""

import json
import logging
import os

import azure.functions as func

from src import storage
from src.classifier import classify
from src.config import GRAPH_WEBHOOK_CLIENT_STATE, MAILBOX_USER_ID
from src.graph_client import GraphClient
from src.models import EmailMessage

app = func.FunctionApp()
logger = logging.getLogger(__name__)


def _process_message(graph: GraphClient, mailbox: str, message_id: str) -> EmailMessage:
    raw_message = graph.get_message(mailbox, message_id)
    email = EmailMessage.from_graph_message(raw_message, mailbox)
    result = classify(email)
    graph.set_categories(mailbox, message_id, [result.category])
    storage.save_classification(email, result)
    logger.info(
        "Klassificerade %s som %s (%s, confidence=%.2f)",
        message_id,
        result.category,
        result.method,
        result.confidence,
    )
    return email


@app.route(route="notifications", methods=["GET", "POST"], auth_level=func.AuthLevel.FUNCTION)
def notifications(req: func.HttpRequest) -> func.HttpResponse:
    # Microsoft Graph validerar endpointen genom att skicka en validationToken
    # som måste ekas tillbaka som text/plain inom 10 sekunder.
    validation_token = req.params.get("validationToken")
    if validation_token:
        return func.HttpResponse(validation_token, status_code=200, mimetype="text/plain")

    try:
        payload = req.get_json()
    except ValueError:
        return func.HttpResponse("Ogiltig payload", status_code=400)

    graph = GraphClient()
    for notification in payload.get("value", []):
        if notification.get("clientState") != GRAPH_WEBHOOK_CLIENT_STATE:
            logger.warning("Avvisar notis med felaktigt clientState")
            continue

        message_id = (notification.get("resourceData") or {}).get("id")
        if not message_id:
            continue

        try:
            _process_message(graph, MAILBOX_USER_ID, message_id)
        except Exception:
            logger.exception("Misslyckades att klassificera meddelande %s", message_id)

    # Graph kräver bara ett 2xx-svar, ingen body behövs.
    return func.HttpResponse(status_code=202)


@app.route(route="subscribe", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def subscribe(req: func.HttpRequest) -> func.HttpResponse:
    mailbox = req.params.get("mailbox", MAILBOX_USER_ID)
    if not mailbox:
        return func.HttpResponse(
            "Ingen mailbox angiven (query-param 'mailbox' eller env-variabeln MAILBOX_USER_ID)",
            status_code=400,
        )

    base_url = os.environ["FUNCTION_APP_BASE_URL"].rstrip("/")
    notification_url = f"{base_url}/api/notifications"

    graph = GraphClient()
    subscription = graph.create_subscription(mailbox, notification_url, GRAPH_WEBHOOK_CLIENT_STATE)
    storage.save_subscription(
        subscription["id"], mailbox, subscription["resource"], subscription["expirationDateTime"]
    )

    return func.HttpResponse(json.dumps(subscription), status_code=201, mimetype="application/json")


@app.timer_trigger(schedule="0 0 */6 * * *", arg_name="timer", run_on_startup=False)
def renew_subscriptions(timer: func.TimerRequest) -> None:
    graph = GraphClient()
    subscriptions = storage.list_subscriptions()
    if not subscriptions:
        logger.info("Inga aktiva prenumerationer att förnya.")
        return

    for sub in subscriptions:
        try:
            renewed = graph.renew_subscription(sub["RowKey"])
            storage.save_subscription(sub["RowKey"], sub["mailbox"], sub["resource"], renewed["expirationDateTime"])
            logger.info("Förnyade prenumeration %s till %s", sub["RowKey"], renewed["expirationDateTime"])
        except Exception:
            logger.exception("Kunde inte förnya prenumeration %s", sub["RowKey"])


@app.route(route="classify-recent", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def classify_recent(req: func.HttpRequest) -> func.HttpResponse:
    """Manuell/backfill-klassificering, användbar innan webhooken är uppsatt."""
    mailbox = req.params.get("mailbox", MAILBOX_USER_ID)
    if not mailbox:
        return func.HttpResponse(
            "Ingen mailbox angiven (query-param 'mailbox' eller env-variabeln MAILBOX_USER_ID)",
            status_code=400,
        )
    top = int(req.params.get("top", "20"))

    graph = GraphClient()
    messages = graph.list_recent_messages(mailbox, top=top)

    results = []
    for raw_message in messages:
        email = EmailMessage.from_graph_message(raw_message, mailbox)
        result = classify(email)
        graph.set_categories(mailbox, email.id, [result.category])
        storage.save_classification(email, result)
        results.append(
            {"id": email.id, "subject": email.subject, "category": result.category, "method": result.method}
        )

    return func.HttpResponse(
        json.dumps({"classified": len(results), "results": results}, ensure_ascii=False),
        status_code=200,
        mimetype="application/json",
    )
