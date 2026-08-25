import os

CATEGORY_PERSONAL = "Privat"
CATEGORY_ADS = "Reklam"
CATEGORY_AI = "AI-relaterat"
CATEGORY_SPAM = "Skräpmejl"

CATEGORIES = [CATEGORY_PERSONAL, CATEGORY_ADS, CATEGORY_AI, CATEGORY_SPAM]

# Claude-modell som används för LLM-klassificering av oklara fall.
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")

# Regelträff med confidence >= detta värde används direkt utan att fråga LLM:en.
RULE_SHORT_CIRCUIT_THRESHOLD = float(os.environ.get("RULE_SHORT_CIRCUIT_THRESHOLD", "0.85"))

# UPN/objekt-id för brevlådan som ska klassificeras. Byt till en delad brevlådas
# adress senare för att peka om motorn utan kodändring.
MAILBOX_USER_ID = os.environ.get("MAILBOX_USER_ID", "")

# Delad hemlighet som Microsoft Graph skickar tillbaka i varje webhook-notis
# (clientState) så vi kan avvisa förfalskade anrop mot /api/notifications.
GRAPH_WEBHOOK_CLIENT_STATE = os.environ.get("GRAPH_WEBHOOK_CLIENT_STATE", "")

# Enda e-postadressen som får logga in på dashboard/stats/subscribe/unsubscribe
# /classify-recent efter Entra ID-inloggning (Easy Auth). Skiftlägesokänslig
# jämförelse. /api/notifications är undantaget - Microsoft Graph loggar aldrig in.
ALLOWED_USER_EMAIL = os.environ.get("ALLOWED_USER_EMAIL", "petter.edlund@movedigital.se")

# USD per 1 miljon tokens, används enbart för att uppskatta kostnaden som
# visas i dashboarden - motsvarar Anthropics officiella listpriser.
CLAUDE_PRICING_PER_MILLION_TOKENS = {
    "claude-sonnet-5": {"input": 2.00, "output": 10.00},
    "claude-opus-5": {"input": 5.00, "output": 25.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
}

# Function App:ens konfigurerade minne (GB), används för att uppskatta
# GB-sekunder-förbrukning i dashboarden. Måste stämma med instansminnet i
# Azure Portal (Function App -> Overview -> Instance Memory).
FUNCTION_APP_MEMORY_GB = float(os.environ.get("FUNCTION_APP_MEMORY_GB", "0.5"))

# Azure Functions Flex Consumption: gratis kvot per månad och prenumeration
# (källa: azure.microsoft.com/pricing/details/functions, on-demand-läge).
AZURE_FREE_EXECUTIONS_PER_MONTH = 250_000
AZURE_FREE_GB_SECONDS_PER_MONTH = 100_000
