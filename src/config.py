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
