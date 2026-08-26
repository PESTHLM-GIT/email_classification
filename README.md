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
  Flex Consumption-plan (räcker gott för denna volym). En Storage Account
  skapas automatiskt – det är den som huserar resultat-tabellen.
  - Function App-namnet i det här projektet är **`emailclassification`**,
    men bas-URL:en är **inte** det förutsägbara `emailclassification.azurewebsites.net`
    - Flex Consumption ger istället en unik, regional URL. Hitta din under
    **Overview → Browse**-knappen eller fältet **Default domain**. I det
    här projektet är den
    `https://emailclassification-cdcwb3a9f6hkaxar.swedencentral-01.azurewebsites.net`.
- Under **Settings → Environment variables** (Application settings), sätt
  samma nycklar som i [`local.settings.json.example`](local.settings.json.example):

  | Namn | Beskrivning |
  |---|---|
  | `ANTHROPIC_API_KEY` | Din Claude API-nyckel |
  | `CLAUDE_MODEL` | T.ex. `claude-sonnet-5` |
  | `GRAPH_TENANT_ID` / `GRAPH_CLIENT_ID` / `GRAPH_CLIENT_SECRET` | Från steg 1 |
  | `MAILBOX_USER_ID` | `petter.edlund@movedigital.se` |
  | `GRAPH_WEBHOOK_CLIENT_STATE` | En slumpad hemlig sträng du hittar på |
  | `FUNCTION_APP_BASE_URL` | `https://emailclassification-cdcwb3a9f6hkaxar.swedencentral-01.azurewebsites.net` |

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

### 4. Aktivera inloggning (Easy Auth)

Dashboarden och API:et (`subscribe`, `unsubscribe`, `classify-recent`,
`stats`) kräver att du är inloggad med ditt `movedigital.se`-konto - ingen
function-nyckel behövs längre för dem. Det sköts av Azure App Service
Authentication ("Easy Auth"), inbyggt i plattformen, ingen egen
inloggningskod. Om er organisation kräver MFA vid inloggning får ni det på
köpet här också.

1. Gå till Function App:en `emailclassification` i Azure Portal.
2. Vänstermenyn → **Settings → Authentication**.
3. Klicka **Add identity provider**.
4. Välj **Microsoft** som identity provider.
5. Under **App registration**, låt **Create new app registration** vara
   ikryssat (Azure skapar och kopplar in den automatiskt - du behöver inte
   göra något manuellt här, till skillnad från Graph-appregistreringen i
   steg 1).
   - **Supported account types**: välj **Current tenant - Single
     organization**. Det gör att bara `movedigital.se`-konton överhuvudtaget
     kan försöka logga in.
6. Under **Restrict access**, välj **Allow unauthenticated requests** (inte
   "Require authentication" - vår egen kod hanterar inloggningskontrollen
   per endpoint, och `/api/notifications` måste förbli helt öppen för
   Microsoft Graph).
7. Klicka **Add**.

Det räcker för själva inloggningen. Vem som helst på `movedigital.se`
*kan* då logga in, men bara den e-postadress som står i miljövariabeln
`ALLOWED_USER_EMAIL` (satt till `petter.edlund@movedigital.se` som
default) släpps igenom av appens egen kod - alla andra får ett tydligt
403-felmeddelande. Vill du lägga till fler tillåtna personer senare, se
[Justera klassificeringen](#justera-klassificeringen)-avsnittets motsvarighet
för åtkomst: ändra `src/auth.py` till att jämföra mot en lista istället för
en enda adress.

### 5. Slå på/av automatisk klassificering

Den automatiska klassificeringen (nya mejl klassificeras direkt när de
kommer in) är **avstängd som standard**. Styr den via
[dashboarden](#dashboard) - en på/av-knapp i webbläsaren, efter att du
loggat in enligt steg 4.

- **Slå på**: knappen i dashboarden (eller `POST /api/subscribe` från en
  inloggad session). Det skapar en Graph-prenumeration och sparar den i
  `Subscriptions`-tabellen. Efter det klassificeras nya mejl automatiskt,
  vilket innebär att Claude-credits förbrukas löpande. Timer-funktionen
  (`renew_subscriptions`) håller prenumerationen vid liv automatiskt var 6:e
  timme tills du stänger av den.
- **Slå av**: samma knapp igen (eller `POST /api/unsubscribe`). Den tar
  bort alla aktiva prenumerationer, både hos Microsoft Graph och i
  `Subscriptions`-tabellen - inga fler mejl klassificeras automatiskt
  förrän du slår på igen. Manuell klassificering (nästa steg) fungerar
  oavsett på/av-läge.

**Obs:** Azure Portals **Code + Test → Test/Run**-panel går inte via en
inloggad webbläsarsession, så den fungerar inte längre för dessa skyddade
funktioner efter att Easy Auth är aktiverat - använd dashboarden istället.
`/api/notifications` (som Graph anropar) påverkas inte av det här alls.

### 6. Backfill / manuell klassificering

Innan webhooken hunnit trigga på nya mejl, eller för att klassificera
befintliga mejl i inkorgen: sektionen **"Klassificera manuellt"** i
dashboarden, med två lägen:

- **Senaste antal mejl** - klassificerar de N senaste (mottagningsordning).
  Motsvarar `POST /api/classify-recent?top=50`.
- **Mellan två tidpunkter** - klassificerar alla mejl mottagna i ett
  datumintervall, upp till 200 mejl. Datum väljs med en vanlig
  datumväljare, klockslag skrivs som text i 24-timmarsformat (TT:MM) - ett
  vanligt textfält istället för webbläsarens inbyggda tidswidget, som annars
  växlar mellan AM/PM och 24h beroende på webbläsarens/OS:ets
  språkinställning snarare än sidans. Allt tolkas som din lokala tid; sidan
  räknar om till UTC åt dig bakom kulisserna (Graph vill ha UTC), men visar
  aldrig UTC i sig - statusraden efter en sökning visar sökintervallet i din
  lokala tid. Motsvarar `POST /api/classify-recent?since=<ISO8601>&until=<ISO8601>`
  (endera kan utelämnas) om du anropar API:et direkt.

## Läsa resultat-tabellen

Varje klassificerat mejl blir en rad i `Classifications`-tabellen i
lagringskontot: avsändare, ämne, kategori, confidence, metod (`rule`/`llm`),
motivering och tidsstämpel. Enklast sätt att titta på den utan installation:

- **Azure Portal** → ditt lagringskonto → **Storage browser** → **Tables** →
  `Classifications`.
- **Excel** kan koppla upp sig direkt mot Table Storage via Power Query
  (Data → Get Data → From Azure → From Azure Table Storage) om du vill
  bygga en rapport/pivot ovanpå.

## Dashboard

En enkel statussida finns på `/api/dashboard` - visar om automatisk
klassificering är på eller av (med en knapp för att slå av/på direkt),
totalt antal klassificerade mejl, Claude-kostnad hittills (uträknad från de
faktiska token-antalen i varje API-svar × Anthropics listpris, inte en
gissning), fördelning per kategori och regelmotor/Claude, en ungefärlig
Azure-förbrukning (mätt körtid, jämförd med Flex Consumptions fria kvot på
250 000 anrop / 100 000 GB-sekunder per månad - **en uppskattning för att ge
en känsla för läget, inte exakt fakturering**; exakta siffror finns i Azure
Portal under **Cost Management**), samt en tabell med de senaste
klassificeringarna - fallande på mottagningstid, som inkorgen. Kolumnen
**Mottaget** visar när mejlet faktiskt kom in, inte klassificeringstid-
punkten (för att undvika förväxling), och tider visas i din webbläsares
lokala tidszon (datat lagras i UTC i tabellen, men konverteras för visning).
Klicka på en rad för att se övrig data som också finns i
`Classifications`-tabellen: avsändare, motivering från Claude, token-antal
och exakt klassificeringstidpunkt - samt en dropdown för att **rätta
kategorin manuellt**. En rättelse skriver tillbaka direkt till raden i
Table Storage (via `POST /api/classifications/correct?id=...&category=...`)
och behåller den ursprungliga bedömningen och vem som rättade den, så
historiken inte går förlorad. Rättade rader får en liten ✎-markering bredvid
kategorin.

Öppna den på:

```
https://emailclassification-cdcwb3a9f6hkaxar.swedencentral-01.azurewebsites.net/api/dashboard
```

Är du inte redan inloggad skickas du automatiskt till Microsofts
inloggningssida (kräver att [Easy Auth är aktiverat](#4-aktivera-inloggning-easy-auth)
och att du loggar in med `petter.edlund@movedigital.se`). Bokmärk gärna
länken - webbläsarens inloggningssession håller dig inloggad mellan besöken
tills sessionen går ut av sig själv.

Dashboarden har **ingen** utloggningsknapp: Azures `/.auth/logout`-endpoint
loggar tyvärr inte bara ut dig från den här appen utan gör en global
utloggning från hela Microsoft 365 i webbläsaren (Outlook, Teams m.m.) -
det är dokumenterat plattformsbeteende, inte något som går att stänga av
via en parameter. Vill du logga ut just den här sidan specifikt: rensa
cookies för webbplatsen i webbläsaren istället för att anropa
`/.auth/logout`.

Sidan uppdaterar sig själv automatiskt var 20:e sekund medan den är öppen
(pausar om fliken inte är synlig) - du behöver inte klicka **Uppdatera**
för att se nya klassificeringar som webhooken gjort under tiden. Riktig
push direkt vid varje webhook-anrop skulle kräva extra Azure-infrastruktur
(t.ex. Azure SignalR/Web PubSub) - bedömdes inte vara värt det för den här
volymen.

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

- **Regler**: `src/rules.py` är medvetet minimal - bara `SPAM_KEYWORDS`
  (uppenbar skräppost) och `AI_DOMAINS` (kända AI-leverantörers domäner).
  Allt annat, inklusive gränsdragningen Reklam/AI-relaterat, avgörs av
  Claude - ett nyckelordsbaserat regelverk för den bedömningen visade sig
  både svårt att underhålla och sämre än att fråga modellen.
- **LLM-prompt/kategoribeskrivningar**: `src/llm_classifier.py`.
- **Tröskel för när en regelträff används direkt utan Claude**:
  `RULE_SHORT_CIRCUIT_THRESHOLD` (miljövariabel, default `0.85`).
- **Hur mycket av mejlet Claude ser**: `BODY_MAX_CHARS` i `src/models.py`
  (default 3000 tecken av det faktiska innehållet, inte bara Graphs korta
  `bodyPreview`). Högre värde = bättre täckning men fler tokens per mejl.

## Köra tester

Testerna mockar både Graph och Claude, så de kräver inga riktiga
credentials och körs automatiskt i GitHub Actions på varje push:

```
pip install -r requirements-dev.txt
pytest -v
```

## Säkerhet

- `/api/dashboard`, `/api/stats`, `/api/subscribe`, `/api/unsubscribe` och
  `/api/classify-recent` kräver inloggning via Azure Easy Auth (Entra ID),
  begränsat till tenanten `movedigital.se`. Utöver det jämför appens egen
  kod (`src/auth.py`) den inloggade användarens e-post mot
  `ALLOWED_USER_EMAIL` innan något körs - fel person får ett tydligt
  403-svar även om de kan logga in på tenanten. Ingen egen kod hanterar
  lösenord, tokens eller sessioner - det sköter Azure-plattformen.
- `/api/notifications` är medvetet öppen utan inloggningskrav
  (`auth_level=ANONYMOUS`, inget `require_login`-anrop) – Microsoft Graph
  kan varken logga in interaktivt eller skicka med en function-nyckel, så
  den skulle annars aldrig komma förbi valideringen när prenumerationen
  skapas. Skyddet sitter istället i att endpointen avvisar alla notiser vars
  `clientState` inte matchar den hemliga `GRAPH_WEBHOOK_CLIENT_STATE`-strängen,
  så förfalskade anrop ignoreras ändå.
- Motorn har bara `Mail.Read`-behörighet mot Graph – den kan inte ändra,
  flytta eller ta bort något i brevlådan, bara läsa och skriva resultatet
  till tabellen.
- Innan Easy Auth är aktiverat (steg 4 i Komma igång) svarar de skyddade
  endpointsen 401 för alla, inklusive dig - appen nekar åtkomst som
  standard (fail closed) istället för att av misstag släppa in vem som
  helst om inloggningen inte är klar.
