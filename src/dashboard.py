"""Statisk HTML/JS för /api/dashboard. Ren sträng med inline CSS/JS så att
Function App:en kan servera hela sidan utan någon extra byggprocess eller
hosting. Inloggning sköts av Easy Auth (Entra ID) - sidan har ingen egen
auth-logik, den förlitar sig på webbläsarens sessionskaka som Azure sätter
efter inloggning; samma kaka skickas automatiskt med varje fetch() nedan."""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="sv">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>E-postklassificering</title>
<style>
  :root {
    --bg: #f5f6f8; --card: #ffffff; --border: #e2e5ea; --text: #1c1f26;
    --muted: #6b7280; --accent: #2563eb; --green: #16a34a; --red: #dc2626;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 2rem; background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
  h1 { font-size: 1.4rem; margin: 0 0 1.5rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 1.1rem 1.3rem; }
  .card h2 { font-size: 0.8rem; text-transform: uppercase; letter-spacing: .03em; color: var(--muted); margin: 0 0 .4rem; font-weight: 600; }
  .card .value { font-size: 1.6rem; font-weight: 700; }
  .card .sub { font-size: 0.82rem; color: var(--muted); margin-top: .3rem; }
  .status-row { display: flex; align-items: center; gap: .8rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
  .badge { display: inline-flex; align-items: center; gap: .4rem; padding: .35rem .8rem; border-radius: 999px; font-weight: 600; font-size: .85rem; }
  .badge.on { background: #dcfce7; color: var(--green); }
  .badge.off { background: #fee2e2; color: var(--red); }
  button { border: none; border-radius: 8px; padding: .6rem 1.2rem; font-size: .9rem; font-weight: 600; cursor: pointer; }
  button.toggle-on { background: var(--red); color: white; }
  button.toggle-off { background: var(--green); color: white; }
  button.refresh, button.manual { background: var(--card); border: 1px solid var(--border); color: var(--text); }
  button:disabled { opacity: .5; cursor: wait; }
  .manual-row { display: flex; align-items: center; gap: .6rem; flex-wrap: wrap; }
  .manual-row input[type="number"] { width: 5rem; padding: .5rem; border: 1px solid var(--border); border-radius: 6px; font-size: .9rem; }
  .manual-row input[type="datetime-local"] { padding: .45rem; border: 1px solid var(--border); border-radius: 6px; font-size: .85rem; }
  .mode-row { display: flex; gap: 1.2rem; margin-bottom: .8rem; font-size: .9rem; }
  .mode-row label { display: flex; align-items: center; gap: .35rem; cursor: pointer; }
  tr.data-row { cursor: pointer; }
  tr.data-row:hover { background: #fafbfc; }
  tr.detail-row td { background: #fafbfc; padding: 1rem 1.3rem; }
  .detail-grid { display: grid; grid-template-columns: max-content 1fr; gap: .35rem 1rem; font-size: .85rem; }
  .detail-grid dt { color: var(--muted); font-weight: 600; }
  .detail-grid dd { margin: 0; }
  table { width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
  th, td { text-align: left; padding: .6rem .9rem; font-size: .85rem; border-bottom: 1px solid var(--border); }
  th { color: var(--muted); font-weight: 600; background: #fafbfc; }
  tr:last-child td { border-bottom: none; }
  .cat-pill { display: inline-block; padding: .1rem .55rem; border-radius: 999px; font-size: .78rem; font-weight: 600; }
  .cat-Privat { background: #e0e7ff; color: #3730a3; }
  .cat-Reklam { background: #fef3c7; color: #92400e; }
  .cat-AI-relaterat { background: #dbeafe; color: #1e40af; }
  .cat-Skräpmejl { background: #fee2e2; color: #991b1b; }
  .method-llm { color: var(--accent); }
  .method-rule { color: var(--muted); }
  .note { font-size: .8rem; color: var(--muted); margin-top: .6rem; line-height: 1.4; }
  .error { background: #fee2e2; color: #991b1b; padding: 1rem; border-radius: 8px; margin-bottom: 1rem; }
  a { color: var(--accent); }
  section { margin-bottom: 1.8rem; }
  section > h2.section-title { font-size: 1rem; margin: 0 0 .7rem; }
</style>
</head>
<body>

<h1>E-postklassificering &mdash; status</h1>
<p class="note" id="loggedInAs"></p>

<div id="error"></div>

<div class="status-row">
  <span id="statusBadge" class="badge off">Laddar...</span>
  <button id="toggleBtn" class="toggle-off" disabled>...</button>
  <button id="refreshBtn" class="refresh">Uppdatera</button>
  <a href="/.auth/logout" style="margin-left: auto; font-size: .85rem;">Logga ut</a>
</div>

<div class="grid">
  <div class="card">
    <h2>Totalt klassificerade</h2>
    <div class="value" id="statTotal">-</div>
  </div>
  <div class="card">
    <h2>Claude-kostnad hittills</h2>
    <div class="value" id="statCost">-</div>
    <div class="sub" id="statTokens"></div>
  </div>
  <div class="card">
    <h2>Regelmotor vs Claude</h2>
    <div class="value" id="statMethod">-</div>
    <div class="sub">Regelträffar kostar inget</div>
  </div>
  <div class="card">
    <h2>Azure-förbrukning (uppskattning)</h2>
    <div class="value" id="statAzure">-</div>
    <div class="note" id="statAzureNote"></div>
  </div>
</div>

<section>
  <h2 class="section-title">Klassificera manuellt</h2>
  <div class="card">
    <div class="mode-row">
      <label><input type="radio" name="manualMode" value="top" checked> Senaste antal mejl</label>
      <label><input type="radio" name="manualMode" value="range"> Mellan två tidpunkter</label>
    </div>
    <div class="manual-row" id="manualTopRow">
      <label for="manualTop">Antal senaste mejl:</label>
      <input type="number" id="manualTop" value="20" min="1" max="200">
    </div>
    <div class="manual-row" id="manualRangeRow" style="display: none;">
      <label for="manualSince">Från:</label>
      <input type="datetime-local" id="manualSince">
      <label for="manualUntil">Till:</label>
      <input type="datetime-local" id="manualUntil">
      <span class="sub">(max 200 mejl inom intervallet, mottagningstid)</span>
    </div>
    <div class="manual-row">
      <button id="manualBtn" class="manual">Klassificera nu</button>
      <span id="manualStatus" class="sub"></span>
    </div>
  </div>
</section>

<section>
  <h2 class="section-title">Fördelning per kategori</h2>
  <div class="grid" id="categoryGrid"></div>
</section>

<section>
  <h2 class="section-title">Senaste klassificeringarna</h2>
  <table>
    <thead>
      <tr><th>Ämne</th><th>Kategori</th><th>Metod</th><th>Kostnad</th><th>Mottaget</th></tr>
    </thead>
    <tbody id="recentBody"></tbody>
  </table>
  <p class="note">Klicka på en rad för avsändare, motivering och övrig data som också finns i Classifications-tabellen.</p>
</section>

<script>
  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function fmtUsd(n) {
    return "$" + Number(n || 0).toFixed(4);
  }

  // Tabellen lagrar allt i UTC (Azure Table Storage-konvention); visar det
  // i webbläsarens lokala tidszon istället, annars läser folk fel tid.
  function fmtLocalTime(isoString) {
    if (!isoString) return "";
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return d.toLocaleString(undefined, {
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
  }

  async function loadStats() {
    document.getElementById("error").innerHTML = "";
    try {
      const res = await fetch("/api/stats", { method: "GET" });
      if (res.status === 401 || res.status === 403) {
        window.location.reload();
        return;
      }
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      render(data);
    } catch (e) {
      document.getElementById("error").innerHTML =
        '<div class="error">Kunde inte hämta status: ' + escapeHtml(e.message) + "</div>";
    }
  }

  function render(data) {
    document.getElementById("loggedInAs").textContent = data.loggedInAs
      ? "Inloggad som " + data.loggedInAs
      : "";

    const badge = document.getElementById("statusBadge");
    const toggleBtn = document.getElementById("toggleBtn");
    if (data.subscriptionActive) {
      badge.textContent = "PÅ - klassificerar automatiskt";
      badge.className = "badge on";
      toggleBtn.textContent = "Stäng av";
      toggleBtn.className = "toggle-on";
    } else {
      badge.textContent = "AV - ingen automatisk klassificering";
      badge.className = "badge off";
      toggleBtn.textContent = "Slå på";
      toggleBtn.className = "toggle-off";
    }
    toggleBtn.disabled = false;
    toggleBtn.onclick = () => toggle(data.subscriptionActive);

    document.getElementById("statTotal").textContent = data.total;
    document.getElementById("statCost").textContent = fmtUsd(data.totalCostUsd);
    document.getElementById("statTokens").textContent =
      (data.totalInputTokens || 0).toLocaleString() + " in / " +
      (data.totalOutputTokens || 0).toLocaleString() + " out tokens";

    const byMethod = data.byMethod || {};
    document.getElementById("statMethod").textContent =
      (byMethod.rule || 0) + " regel / " + (byMethod.llm || 0) + " Claude";

    const usage = data.azureUsage || {};
    document.getElementById("statAzure").textContent =
      (usage.invocationCount || 0).toLocaleString() + " anrop";
    document.getElementById("statAzureNote").textContent =
      "~" + Number(usage.gbSeconds || 0).toFixed(2) + " GB-sekunder använda av " +
      usage.freeGbSecondsPerMonth.toLocaleString() + " gratis/månad (" +
      usage.freeExecutionsPerMonth.toLocaleString() + " gratis anrop/månad). " +
      "Uppskattning baserad på mätt körtid, inte exakt fakturering - troligen $0 " +
      "så länge ni är under kvoten. Exakt siffra: Azure Portal -> Cost Management.";

    const catGrid = document.getElementById("categoryGrid");
    catGrid.innerHTML = "";
    const categories = data.byCategory || {};
    Object.keys(categories).forEach((cat) => {
      const div = document.createElement("div");
      div.className = "card";
      div.innerHTML = '<h2>' + escapeHtml(cat) + '</h2><div class="value">' + categories[cat] + '</div>';
      catGrid.appendChild(div);
    });
    if (Object.keys(categories).length === 0) {
      catGrid.innerHTML = '<div class="card"><div class="sub">Inga klassificeringar ännu.</div></div>';
    }

    const body = document.getElementById("recentBody");
    body.innerHTML = "";
    (data.recent || []).forEach((row, index) => {
      const tr = document.createElement("tr");
      tr.className = "data-row";
      const catClass = "cat-" + String(row.category || "").replace(/\\s/g, "");
      tr.innerHTML =
        "<td>" + escapeHtml(row.subject) + "</td>" +
        '<td><span class="cat-pill ' + catClass + '">' + escapeHtml(row.category) + "</span></td>" +
        '<td class="method-' + escapeHtml(row.method) + '">' + escapeHtml(row.method) + "</td>" +
        "<td>" + fmtUsd(row.costUsd) + "</td>" +
        "<td>" + escapeHtml(fmtLocalTime(row.receivedAt)) + "</td>";

      const detailTr = document.createElement("tr");
      detailTr.className = "detail-row";
      detailTr.style.display = "none";
      const detailTd = document.createElement("td");
      detailTd.colSpan = 5;
      const fields = [
        ["Avsändare", (row.senderName || "") + " <" + (row.senderAddress || "") + ">"],
        ["Mottaget", fmtLocalTime(row.receivedAt)],
        ["Klassificerat", fmtLocalTime(row.classifiedAt)],
        ["Confidence", row.confidence],
        ["Metod", row.method],
        ["Motivering", row.reasoning],
        ["Tokens (in/ut)", (row.inputTokens || 0) + " / " + (row.outputTokens || 0)],
        ["Kostnad", fmtUsd(row.costUsd)],
      ];
      detailTd.innerHTML =
        '<dl class="detail-grid">' +
        fields.map(([label, value]) => "<dt>" + escapeHtml(label) + "</dt><dd>" + escapeHtml(value) + "</dd>").join("") +
        "</dl>";
      detailTr.appendChild(detailTd);

      tr.addEventListener("click", () => {
        detailTr.style.display = detailTr.style.display === "none" ? "" : "none";
      });

      body.appendChild(tr);
      body.appendChild(detailTr);
    });
    if ((data.recent || []).length === 0) {
      body.innerHTML = '<tr><td colspan="5">Inga klassificeringar ännu.</td></tr>';
    }
  }

  async function toggle(currentlyActive) {
    const toggleBtn = document.getElementById("toggleBtn");
    toggleBtn.disabled = true;
    toggleBtn.textContent = "...";
    try {
      const path = currentlyActive ? "/api/unsubscribe" : "/api/subscribe";
      const res = await fetch(path, { method: "POST" });
      if (!res.ok) throw new Error("HTTP " + res.status + ": " + (await res.text()));
      await loadStats();
    } catch (e) {
      document.getElementById("error").innerHTML =
        '<div class="error">Kunde inte ändra status: ' + escapeHtml(e.message) + "</div>";
      toggleBtn.disabled = false;
    }
  }

  // datetime-local ger lokal tid utan tidszon (t.ex. "2026-08-20T14:30") -
  // Graph vill ha UTC med Z-suffix, så vi tolkar värdet som lokal tid och
  // konverterar via Date, som webbläsaren redan känner till användarens tidszon för.
  function localInputToIsoUtc(value) {
    if (!value) return null;
    const d = new Date(value);
    if (isNaN(d.getTime())) return null;
    return d.toISOString().replace(/\.\d{3}Z$/, "Z");
  }

  async function classifyNow() {
    const btn = document.getElementById("manualBtn");
    const statusEl = document.getElementById("manualStatus");
    const mode = document.querySelector('input[name="manualMode"]:checked').value;

    let query = "";
    if (mode === "range") {
      const since = localInputToIsoUtc(document.getElementById("manualSince").value);
      const until = localInputToIsoUtc(document.getElementById("manualUntil").value);
      if (!since && !until) {
        document.getElementById("error").innerHTML =
          '<div class="error">Ange minst "Från" eller "Till" för intervall-läget.</div>';
        return;
      }
      const params = new URLSearchParams();
      if (since) params.set("since", since);
      if (until) params.set("until", until);
      query = "?" + params.toString();
    } else {
      const top = document.getElementById("manualTop").value || "20";
      query = "?top=" + encodeURIComponent(top);
    }

    btn.disabled = true;
    statusEl.textContent = "Klassificerar...";
    try {
      const res = await fetch("/api/classify-recent" + query, { method: "POST" });
      if (!res.ok) throw new Error("HTTP " + res.status + ": " + (await res.text()));
      const data = await res.json();
      statusEl.textContent = "Klart: " + data.classified + " mejl klassificerade.";
      await loadStats();
    } catch (e) {
      statusEl.textContent = "";
      document.getElementById("error").innerHTML =
        '<div class="error">Kunde inte klassificera: ' + escapeHtml(e.message) + "</div>";
    } finally {
      btn.disabled = false;
    }
  }

  document.querySelectorAll('input[name="manualMode"]').forEach((radio) => {
    radio.addEventListener("change", () => {
      const isRange = document.querySelector('input[name="manualMode"]:checked').value === "range";
      document.getElementById("manualTopRow").style.display = isRange ? "none" : "";
      document.getElementById("manualRangeRow").style.display = isRange ? "" : "none";
    });
  });

  document.getElementById("manualBtn").addEventListener("click", classifyNow);
  document.getElementById("refreshBtn").addEventListener("click", loadStats);
  loadStats();
</script>
</body>
</html>
"""
