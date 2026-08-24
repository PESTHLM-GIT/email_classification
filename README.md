# E-postklassificeringsmotor

Klassificerar inkommande mejl i din brevlåda automatiskt i fyra kategorier:

- **Privat** – personlig/genuin korrespondens
- **Reklam** – marknadsföring, nyhetsbrev, kampanjer
- **AI-relaterat** – mejl vars huvudämne är AI/maskininlärning
- **Skräpmejl** – oönskad post, phishing

Byggd för att köra mot din personliga Move Digital-brevlåda (`petter.edlund@movedigital.se`)
till att börja med, men designad för att pekas om mot en delad brevlåda senare
utan kodändring (se [Utöka till en delad brevlåda](#utöka-till-en-delad-brevlåda)).

## Arkitektur

En Azure Function (Python) som prenumererar på nya mejl via en Microsoft
Graph webhook (change notification). När ett nytt mejl kommer in:

1. **Regelmotor** (`src/rules.py`) tittar först på avsändardomän, nyckelord
   och `List-Unsubscribe`-header. Uppenbara fall (t.ex. ett nyhetsbrev med
   avregistreringslänk) avgörs direkt utan att fråga någon LLM.
2. Osäkra/nyanserade fall skickas till **Claude** (`src/llm_classifier.py`)
   som gör den slutgiltiga bedömningen – regelmotorns preliminära gissning
   skickas med som en hint.
3. Resultatet sätts som **Outlook-kategori** på mejlet (icke-destruktivt,
   syns direkt i Outlook, lätt att ångra) och skrivs som en rad i en
   **Azure Table Storage**-tabell (`Classifications`) – din resultat-tabell.
   Table Storage ligger i samma lagringskonto som Function App redan kräver,
   så ingen extra Azure-resurs behöver skapas för det.

```
Nytt mejl -> Graph webhook -> /api/notifications -> regler -> (ev. Claude) -> sätt kategori + spara rad
```

Inget behöver installeras lokalt: Azure-resurserna sätts upp i webbläsaren
via Azure Portal, och deploy sker automatiskt via den bifogade GitHub
Actions-workflowen när du pushar till `main`.

## Komma igång

### 1. Azure AD-appregistrering (för Microsoft Graph-åtkomst)

I [Azure Portal](https://portal.azure.com) → **Microsoft Entra ID** → **App
registrations** → **New registration**:

- Skapa en appregistrering, notera **Application (client) ID** och
  **Directory (tenant) ID**.
- **Certificates & secrets** → skapa en **client secret**, spara värdet direkt.
- **API permissions** → **Add a permission** → **Microsoft Graph** →
  **Application permissions** → lägg till `Mail.Read` och `Mail.ReadWrite`.
- Klicka **Grant admin consent** (kräver admin-behörighet i tenanten).

App-only-behörighet ger som standard åtkomst till alla brevlådor i
tenanten. Vill du begränsa appen till bara din brevlåda (och senare den
delade brevlådan), gå igenom
[ApplicationAccessPolicy](https://learn.microsoft.com/graph/auth-limit-mailbox-access)
via Exchange Online PowerShell.

### 2. Function App

- Skapa en **Function App** i Azure Portal: Runtime stack **Python 3.11**,
  Consumption-plan (räcker gott för denna volym). En Storage Account skapas
  automatiskt – det är den som huserar resultat-tabellen.
- Under **Settings → Environment variables** (Application settings), sätt
  samma nycklar som i [`local.settings.json.example`](local.settings.json.example):

  | Namn | Beskrivning |
  |---|---|
  | `ANTHROPIC_API_KEY` | Din Claude API-nyckel |
  | `CLAUDE_MODEL` | T.ex. `claude-sonnet-5` |
  | `GRAPH_TENANT_ID` / `GRAPH_CLIENT_ID` / `GRAPH_CLIENT_SECRET` | Från steg 1 |
  | `MAILBOX_USER_ID` | `petter.edlund@movedigital.se` |
  | `GRAPH_WEBHOOK_CLIENT_STATE` | En slumpad hemlig sträng du hittar på |
  | `FUNCTION_APP_BASE_URL` | `https://<ditt-function-app-namn>.azurewebsites.net` |

  Överväg Key Vault-referenser för hemligheterna i produktion.

### 3. Deploy via GitHub Actions

- Öppna `.github/workflows/deploy.yml` och sätt `AZURE_FUNCTIONAPP_NAME`
  till ditt Function App-namn.
- I Function App i Azure Portal: **Overview → Get publish profile**, ladda
  ner filen.
- I GitHub-repot: **Settings → Secrets and variables → Actions → New
  repository secret**, lägg in innehållet som `AZURE_FUNCTIONAPP_PUBLISH_PROFILE`.
- Merga till `main` (eller kör workflowen manuellt via **Actions → Deploy to
  Azure Functions → Run workflow**) – deploy sker automatiskt, helt via
  webbläsaren.

### 4. Sätt upp webhook-prenumerationen

Anropa (t.ex. med curl, Postman, eller webbläsarens devtools) mot din
deployade funktion, med function-nyckeln som Azure ger dig under **App keys**:

```
POST https://<ditt-function-app-namn>.azurewebsites.net/api/subscribe?code=<function-key>
```

Det skapar Graph-prenumerationen och sparar den i `Subscriptions`-tabellen.
Timer-funktionen (`renew_subscriptions`) körs var 6:e timme och förnyar
alla aktiva prenumerationer automatiskt så du slipper göra om det manuellt.

### 5. Backfill / manuell klassificering

Innan webhooken hunnit trigga på nya mejl, eller för att klassificera
befintliga mejl i inkorgen:

```
POST https://<ditt-function-app-namn>.azurewebsites.net/api/classify-recent?code=<function-key>&top=50
```

## Läsa resultat-tabellen

Varje klassificerat mejl blir en rad i `Classifications`-tabellen i
lagringskontot: avsändare, ämne, kategori, confidence, metod (`rule`/`llm`),
motivering och tidsstämpel. Enklast sätt att titta på den utan installation:

- **Azure Portal** → ditt lagringskonto → **Storage browser** → **Tables** →
  `Classifications`.
- **Excel** kan koppla upp sig direkt mot Table Storage via Power Query
  (Data → Get Data → From Azure → From Azure Table Storage) om du vill
  bygga en rapport/pivot ovanpå.

## Utöka till en delad brevlåda

Byt bara värdet på `MAILBOX_USER_ID` (eller skicka `?mailbox=...` till
`/api/subscribe` och `/api/classify-recent`) till den delade brevlådans
adress – all kod är redan skriven mot `mailbox` som en generisk parameter.
Se bara till att appregistreringen har åtkomst till den brevlådan (se
ApplicationAccessPolicy-noten ovan om du har begränsat behörigheten).

## Justera klassificeringen

- **Regler**: lägg till/ta bort nyckelord och domäner i `src/rules.py`
  (`SPAM_KEYWORDS`, `AD_KEYWORDS`, `AI_KEYWORDS`, `AI_DOMAINS`, m.fl.).
- **LLM-prompt/kategoribeskrivningar**: `src/llm_classifier.py`.
- **Tröskel för när en regelträff används direkt utan Claude**:
  `RULE_SHORT_CIRCUIT_THRESHOLD` (miljövariabel, default `0.85`).

## Köra tester

Testerna mockar både Graph och Claude, så de kräver inga riktiga
credentials och körs automatiskt i GitHub Actions på varje push:

```
pip install -r requirements-dev.txt
pytest -v
```

## Säkerhet

- HTTP-endpoints kräver en function key (`auth_level=FUNCTION`).
- `/api/notifications` avvisar notiser vars `clientState` inte matchar
  `GRAPH_WEBHOOK_CLIENT_STATE`, så förfalskade webhook-anrop ignoreras.
- Outlook-kategorier är icke-destruktiva – inget mejl flyttas eller tas bort.
