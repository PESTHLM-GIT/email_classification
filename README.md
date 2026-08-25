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
Graph webhook (change notification). Motorn är **skrivskyddad mot Outlook** –
den läser mejl men ändrar, flyttar eller taggar aldrig något i brevlådan.
Enda output är en rad i en resultat-tabell. När ett nytt mejl kommer in:

1. **Regelmotor** (`src/rules.py`) tittar först på avsändardomän, nyckelord
   och `List-Unsubscribe`-header. Uppenbara fall (t.ex. ett nyhetsbrev med
   avregistreringslänk) avgörs direkt utan att fråga någon LLM.
2. Osäkra/nyanserade fall skickas till **Claude** (`src/llm_classifier.py`)
   som gör den slutgiltiga bedömningen – regelmotorns preliminära gissning
   skickas med som en hint.
3. Resultatet skrivs som en rad i en **Azure Table Storage**-tabell
   (`Classifications`) – din resultat-tabell. Table Storage ligger i samma
   lagringskonto som Function App redan kräver, så ingen extra Azure-resurs
   behöver skapas för det.

```
Nytt mejl -> Graph webhook -> /api/notifications -> regler -> (ev. Claude) -> spara rad i tabellen
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
  **Application permissions** → lägg till `Mail.Read` (motorn skriver
  aldrig till brevlådan, så `Mail.ReadWrite` behövs inte).
- Klicka **Grant admin consent** (kräver admin-behörighet i tenanten).

Har du redan lagt till `Mail.ReadWrite` av misstag: gå till samma
**API permissions**-sida, klicka på de tre prickarna bredvid `Mail.ReadWrite`
→ **Remove permission**, enligt principen om minsta möjliga behörighet.

App-only-behörighet ger som standard åtkomst till alla brevlådor i
tenanten. Vill du begränsa appen till bara din brevlåda (och senare den
delade brevlådan), gå igenom
[ApplicationAccessPolicy](https://learn.microsoft.com/graph/auth-limit-mailbox-access)
via Exchange Online PowerShell.

### 2. Function App

- Skapa en **Function App** i Azure Portal: Runtime stack **Python 3.11**,
  Consumption-plan (räcker gott för denna volym). En Storage Account skapas
  automatiskt – det är den som huserar resultat-tabellen.
  - Function App-namnet i det här projektet är **`emailclassification`**,
    dvs. bas-URL:en är `https://emailclassification.azurewebsites.net`.
- Under **Settings → Environment variables** (Application settings), sätt
  samma nycklar som i [`local.settings.json.example`](local.settings.json.example):

  | Namn | Beskrivning |
  |---|---|
  | `ANTHROPIC_API_KEY` | Din Claude API-nyckel |
  | `CLAUDE_MODEL` | T.ex. `claude-sonnet-5` |
  | `GRAPH_TENANT_ID` / `GRAPH_CLIENT_ID` / `GRAPH_CLIENT_SECRET` | Från steg 1 |
  | `MAILBOX_USER_ID` | `petter.edlund@movedigital.se` |
  | `GRAPH_WEBHOOK_CLIENT_STATE` | En slumpad hemlig sträng du hittar på |
  | `FUNCTION_APP_BASE_URL` | `https://emailclassification.azurewebsites.net` |

  Överväg Key Vault-referenser för hemligheterna i produktion.

### 3. Deploy via GitHub Actions

Deployen sköts av `.github/workflows/main_emailclassification.yml`, som
Azures **Deployment Center** genererade automatiskt och pushade till `main`
när Function App:en kopplades mot detta repo. Den använder OIDC/federated
credentials (secrets `AZUREAPPSERVICE_CLIENTID_...`, `..._TENANTID_...`,
`..._SUBSCRIPTIONID_...`, redan tillagda i repots secrets av Azure) – inget
manuellt publish-profile-steg behövs.

Varje push till `main` bygger och deployar automatiskt. Vill du deploya om
utan att pusha, kör workflowen manuellt via **Actions → Build and deploy
Python project to Azure Function App - emailclassification → Run workflow**.

### 4. Slå på/av automatisk klassificering

Den automatiska klassificeringen (nya mejl klassificeras direkt när de
kommer in) är **avstängd som standard**. Enklast sätt att testa den (eller
stänga av den igen) är via samma **Code + Test → Test/Run**-panel i Azure
Portal som används för `classify_recent` (se avsnittet om att verifiera att
allt fungerar) - välj bara funktionen `subscribe` eller `unsubscribe`
istället, inga query-parametrar behövs.

- **Slå på**: kör funktionen **`subscribe`**. Det skapar en
  Graph-prenumeration och sparar den i `Subscriptions`-tabellen. Efter det
  klassificeras nya mejl automatiskt, vilket innebär att Claude-credits
  förbrukas löpande. Timer-funktionen (`renew_subscriptions`) håller
  prenumerationen vid liv automatiskt var 6:e timme tills du stänger av den.
- **Slå av**: kör funktionen **`unsubscribe`**. Den tar bort alla aktiva
  prenumerationer, både hos Microsoft Graph och i `Subscriptions`-tabellen -
  inga fler mejl klassificeras automatiskt förrän du kör `subscribe` igen.
  Manuell körning av `classify_recent` fungerar oavsett på/av-läge.

(Vill du hellre göra det via HTTP-anrop, t.ex. med curl: samma två
endpoints finns på `POST /api/subscribe?code=<function-key>` respektive
`POST /api/unsubscribe?code=<function-key>`, med function-nyckeln du hittar
under **App keys**.)

### 5. Backfill / manuell klassificering

Innan webhooken hunnit trigga på nya mejl, eller för att klassificera
befintliga mejl i inkorgen:

```
POST https://emailclassification.azurewebsites.net/api/classify-recent?code=<function-key>&top=50
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

## Vägen vidare: orderigenkänning i en delad brevlåda

Detta projekt är en proof-of-concept för ett större slutmål: en delad
brevlåda dit ordrar kommer in, där en AI läser innehållet, avgör om det
verkligen är en order, och trycker in resultatet i ett ordersystem via API.
Grundflödet (läs mejl → klassificera → skriv resultat) är detsamma, men två
delar behöver byggas ut när vi tar steget dit:

- **Klassificeringsschema**: byt kategori-taggningen i `llm_classifier.py`
  mot ett verktyg som avgör "är det här en order?" (ja/nej + confidence) och
  extraherar strukturerade fält (ordernummer, kund, artiklar, leveransadress
  m.m.) istället för en enkel kategori.
- **Utgående steg mot ordersystemet**: ett nytt anrop som tar den
  strukturerade ordern och POST:ar den till ordersystemets API, utöver (eller
  istället för) att bara spara raden i Table Storage.

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

- Alla HTTP-endpoints utom `/api/notifications` kräver en function key
  (`auth_level=FUNCTION`).
- `/api/notifications` är medvetet öppen utan nyckel-krav
  (`auth_level=ANONYMOUS`) – Microsoft Graph kan inte skicka med en
  function-nyckel i sina anrop, så den skulle annars aldrig komma förbi
  valideringen när prenumerationen skapas. Skyddet sitter istället i att
  endpointen avvisar alla notiser vars `clientState` inte matchar den hemliga
  `GRAPH_WEBHOOK_CLIENT_STATE`-strängen, så förfalskade anrop ignoreras ändå.
- Motorn har bara `Mail.Read`-behörighet mot Graph – den kan inte ändra,
  flytta eller ta bort något i brevlådan, bara läsa och skriva resultatet
  till tabellen.
