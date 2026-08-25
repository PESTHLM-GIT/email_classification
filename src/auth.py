"""Verifierar att en inloggad Azure Easy Auth-användare matchar den enda
tillåtna e-postadressen (ALLOWED_USER_EMAIL), innan skyddade endpoints
(dashboard, stats, subscribe, unsubscribe, classify-recent) körs.

Inloggningen sköts helt av Azure App Service Authentication (Easy Auth) mot
Microsoft Entra ID - ingen egen kod hanterar lösenord, tokens eller
sessioner. Easy Auth injicerar X-MS-CLIENT-PRINCIPAL-NAME i request-headern
för inloggade användare; den headern kan inte sättas av en extern anropare.

/api/notifications är medvetet undantaget - Microsoft Graph kan inte logga
in interaktivt, det skyddet sitter i clientState-kontrollen istället.
"""

from typing import Optional

import azure.functions as func

from .config import ALLOWED_USER_EMAIL

LOGIN_PATH = "/.auth/login/aad"


def require_login(req: func.HttpRequest, redirect_if_missing: bool = False) -> Optional[func.HttpResponse]:
    """Returnerar ett HttpResponse att skicka tillbaka direkt om åtkomst ska
    nekas, annars None (fortsätt köra funktionen som vanligt)."""
    principal_name = (req.headers.get("X-MS-CLIENT-PRINCIPAL-NAME") or "").strip()

    if not principal_name:
        if redirect_if_missing:
            redirect_uri = req.url.split("?", 1)[0]
            return func.HttpResponse(
                status_code=302,
                headers={"Location": f"{LOGIN_PATH}?post_login_redirect_uri={redirect_uri}"},
            )
        return func.HttpResponse(
            "Inte inloggad. Öppna /api/dashboard i webbläsaren för att logga in.",
            status_code=401,
        )

    if principal_name.lower() != ALLOWED_USER_EMAIL.lower():
        return func.HttpResponse(
            f"Inloggad som {principal_name}, men bara {ALLOWED_USER_EMAIL} har åtkomst.",
            status_code=403,
        )

    return None
