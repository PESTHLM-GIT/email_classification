"""Tunn, skrivskyddad wrapper runt Microsoft Graph för att läsa mejl och
hantera webhook-prenumerationer (change notifications). Motorn ändrar
aldrig något i brevlådan - endast Mail.Read-behörighet krävs.

Autentisering sker app-only (client credentials) så att samma kod fungerar
oförändrat mot både en personlig brevlåda och en delad brevlåda senare -
det är bara `mailbox`-parametern (UPN eller objekt-id) som ändras.
"""

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import msal
import requests

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
MESSAGE_SELECT = "id,subject,from,bodyPreview,receivedDateTime,categories,internetMessageHeaders"

# Microsoft Graph tillåter max ~4230 minuter (strax under 3 dygn) för
# mail-resursen. Timer-funktionen förnyar prenumerationen med god marginal
# innan dess.
DEFAULT_SUBSCRIPTION_MINUTES = 4230


class GraphClient:
    def __init__(self) -> None:
        self.tenant_id = os.environ["GRAPH_TENANT_ID"]
        self.client_id = os.environ["GRAPH_CLIENT_ID"]
        self.client_secret = os.environ["GRAPH_CLIENT_SECRET"]
        self._app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            client_credential=self.client_secret,
        )
        self._token = None
        self._token_expires_at = 0.0

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        result = self._app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in result:
            raise RuntimeError(f"Kunde inte hämta Graph-token: {result.get('error_description')}")
        self._token = result["access_token"]
        self._token_expires_at = time.time() + result.get("expires_in", 3600)
        return self._token

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._get_token()}", "Content-Type": "application/json"}

    def get_message(self, mailbox: str, message_id: str) -> Dict[str, Any]:
        url = f"{GRAPH_BASE}/users/{mailbox}/messages/{message_id}"
        resp = requests.get(url, headers=self._headers(), params={"$select": MESSAGE_SELECT}, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def list_recent_messages(self, mailbox: str, top: int = 20) -> List[Dict[str, Any]]:
        url = f"{GRAPH_BASE}/users/{mailbox}/mailFolders('Inbox')/messages"
        params = {"$top": top, "$select": MESSAGE_SELECT, "$orderby": "receivedDateTime desc"}
        resp = requests.get(url, headers=self._headers(), params=params, timeout=30)
        resp.raise_for_status()
        return resp.json().get("value", [])

    def create_subscription(
        self,
        mailbox: str,
        notification_url: str,
        client_state: str,
        expiration_minutes: int = DEFAULT_SUBSCRIPTION_MINUTES,
    ) -> Dict[str, Any]:
        expiration = (datetime.now(timezone.utc) + timedelta(minutes=expiration_minutes)).isoformat()
        body = {
            "changeType": "created",
            "notificationUrl": notification_url,
            "resource": f"/users/{mailbox}/mailFolders('Inbox')/messages",
            "expirationDateTime": expiration,
            "clientState": client_state,
        }
        resp = requests.post(f"{GRAPH_BASE}/subscriptions", headers=self._headers(), json=body, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def renew_subscription(
        self, subscription_id: str, expiration_minutes: int = DEFAULT_SUBSCRIPTION_MINUTES
    ) -> Dict[str, Any]:
        expiration = (datetime.now(timezone.utc) + timedelta(minutes=expiration_minutes)).isoformat()
        resp = requests.patch(
            f"{GRAPH_BASE}/subscriptions/{subscription_id}",
            headers=self._headers(),
            json={"expirationDateTime": expiration},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
