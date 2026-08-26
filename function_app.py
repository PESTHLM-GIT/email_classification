"""Azure Functions-app (Python v2-modellen).

Endpoints:
- POST/GET /api/notifications      - tar emot Microsoft Graph webhook-notiser om nya mejl.
- POST /api/subscribe              - slår PÅ automatisk klassificering (skapar webhook-prenumerationen).
- POST /api/unsubscribe            - slår AV automatisk klassificering (tar bort alla prenumerationer).
- POST /api/classify-recent        - manuell/backfill-klassificering av senaste mejlen.
- POST /api/classifications/correct - rättar en enskild klassificering manuellt.
- GET  /api/stats                  - statistik (antal, kostnad, kategorier) för dashboarden.
- GET  /api/dashboard              - enkel HTML-sida: status, statistik, på/av-knapp.
- (timer) renew_subscriptions      - förnyar aktiva prenumerationer var 6:e timme.
"""

import json
import logging
import os
import time

import azure.functions as func
from azure.core.exceptions import ResourceNotFoundError

from src import storage
from src.auth import require_login
from src.classifier import classify
from src.config import (
    AZURE_FREE_EXECUTIONS_PER_MONTH,
    AZURE_FREE_GB_SECONDS_PER_MONTH,
    CATEGORIES,
    GRAPH_WEBHOOK_CLIENT_STATE,
    MAILBOX_USER_ID,
)
from src.dashboard import render_dashboard
from src.graph_client import GraphClient
from src.models import EmailMessage

app = func.FunctionApp()
logger = logging.getLogger(__name__)


def _process_message(graph: GraphClient, mailbox: str, message_id: str) -> EmailMessage:
    raw_message = graph.get_message(mailbox, message_id)
    email = EmailMessage.from_graph_message(raw_message, mailbox)
    result = classify(email)
    storage.save_classification(email, result)
    logger.info(
        "Klassificerade %s som %s (%s, confidence=%.2f)",
        message_id,
        result.category,
        result.method,
        result.confidence,
    )
    return email


@app.route(route="notifications", methods=["GET", "POST"], auth_level=func.AuthLevel.ANONYMOUS)
def notifications(req: func.HttpRequest) -> func.HttpResponse:
    # Microsoft Graph validerar endpointen genom att skicka en validationToken
    # som måste ekas tillbaka som text/plain inom 10 sekunder.
    validation_token = req.params.get("validationToken")
    if validation_token:
        return func.HttpResponse(validation_token, status_code=200, mimetype="text/plain")

    start = time.perf_counter()
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

    storage.record_invocation("notifications", time.perf_counter() - start)

    # Graph kräver bara ett 2xx-svar, ingen body behövs.
    return func.HttpResponse(status_code=202)


@app.route(route="subscribe", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def subscribe(req: func.HttpRequest) -> func.HttpResponse:
    denied = require_login(req)
    if denied:
        return denied

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


@app.route(route="unsubscribe", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def unsubscribe(req: func.HttpRequest) -> func.HttpResponse:
    """Stänger av den automatiska klassificeringen: tar bort alla kända
    Graph-prenumerationer så inga fler webhook-notiser (och därmed inga fler
    Claude-anrop) kommer in. Rör aldrig själva brevlådan."""
    denied = require_login(req)
    if denied:
        return denied

    graph = GraphClient()
    subscriptions = storage.list_subscriptions()

    removed = []
    for sub in subscriptions:
        subscription_id = sub["RowKey"]
        graph.delete_subscription(subscription_id)
        storage.delete_subscription(subscription_id)
        removed.append(subscription_id)

    return func.HttpResponse(
        json.dumps({"removed": removed}, ensure_ascii=False), status_code=200, mimetype="application/json"
    )


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


@app.route(route="classify-recent", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def classify_recent(req: func.HttpRequest) -> func.HttpResponse:
    """Manuell/backfill-klassificering, användbar innan webhooken är uppsatt."""
    denied = require_login(req)
    if denied:
        return denied

    mailbox = req.params.get("mailbox", MAILBOX_USER_ID)
    if not mailbox:
        return func.HttpResponse(
            "Ingen mailbox angiven (query-param 'mailbox' eller env-variabeln MAILBOX_USER_ID)",
            status_code=400,
        )
    top = int(req.params.get("top", "20"))
    since = req.params.get("since")
    until = req.params.get("until")

    start = time.perf_counter()
    graph = GraphClient()
    messages = graph.list_recent_messages(mailbox, top=top, since=since, until=until)

    results = []
    for raw_message in messages:
        email = EmailMessage.from_graph_message(raw_message, mailbox)
        result = classify(email)
        storage.save_classification(email, result)
        results.append(
            {"id": email.id, "subject": email.subject, "category": result.category, "method": result.method}
        )
    storage.record_invocation("classify_recent", time.perf_counter() - start)

    return func.HttpResponse(
        json.dumps(
            {"classified": len(results), "results": results, "mailbox": mailbox, "since": since, "until": until},
            ensure_ascii=False,
        ),
        status_code=200,
        mimetype="application/json",
    )


@app.route(route="classifications/correct", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def correct_classification(req: func.HttpRequest) -> func.HttpResponse:
    """Rättar en enskild klassificering manuellt (dashboardens dropdown i
    den utfällda radvyn). Behåller den ursprungliga bedömningen och vem som
    rättade den, istället för att bara skriva över den tyst."""
    denied = require_login(req)
    if denied:
        return denied

    message_id = req.params.get("id")
    mailbox = req.params.get("mailbox", MAILBOX_USER_ID)
    new_category = req.params.get("category")

    if not message_id or not new_category:
        return func.HttpResponse("Query-parametrarna 'id' och 'category' krävs", status_code=400)
    if new_category not in CATEGORIES:
        return func.HttpResponse(f"Ogiltig kategori. Måste vara en av: {', '.join(CATEGORIES)}", status_code=400)

    corrected_by = req.headers.get("X-MS-CLIENT-PRINCIPAL-NAME", "okänd")
    try:
        storage.update_category(mailbox, message_id, new_category, corrected_by)
    except ResourceNotFoundError:
        return func.HttpResponse("Hittade ingen klassificering med det id:t", status_code=404)

    return func.HttpResponse(status_code=204)


@app.route(route="stats", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def stats(req: func.HttpRequest) -> func.HttpResponse:
    denied = require_login(req)
    if denied:
        return denied

    data = storage.get_stats()
    data["subscriptionActive"] = len(storage.list_subscriptions()) > 0
    data["loggedInAs"] = req.headers.get("X-MS-CLIENT-PRINCIPAL-NAME", "")

    usage = storage.get_usage()
    usage["freeExecutionsPerMonth"] = AZURE_FREE_EXECUTIONS_PER_MONTH
    usage["freeGbSecondsPerMonth"] = AZURE_FREE_GB_SECONDS_PER_MONTH
    data["azureUsage"] = usage

    return func.HttpResponse(json.dumps(data, ensure_ascii=False), status_code=200, mimetype="application/json")


@app.route(route="dashboard", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def dashboard(req: func.HttpRequest) -> func.HttpResponse:
    denied = require_login(req, redirect_if_missing=True)
    if denied:
        return denied
    return func.HttpResponse(render_dashboard(CATEGORIES), status_code=200, mimetype="text/html")
