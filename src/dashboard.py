"""Statisk HTML/JS för /api/dashboard. Ren sträng med inline CSS/JS så att
Function App:en kan servera hela sidan utan någon extra byggprocess eller
hosting - en URL (med function-nyckeln som ?code=...) räcker."""

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
  button.refresh { background: var(--card); border: 1px solid var(--border); color: var(--text); }
  button:disabled { opacity: .5; cursor: wait; }
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

<div id="error"></div>

<div class="status-row">
  <span id="statusBadge" class="badge off">Laddar...</span>
  <button id="toggleBtn" class="toggle-off" disabled>...</button>
  <button id="refreshBtn" class="refresh">Uppdatera</button>
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
  <h2 class="section-title">Fördelning per kategori</h2>
  <div class="grid" id="categoryGrid"></div>
</section>

<section>
  <h2 class="section-title">Senaste klassificeringarna</h2>
  <table>
    <thead>
      <tr><th>Ämne</th><th>Kategori</th><th>Metod</th><th>Kostnad</th><th>Tidpunkt (UTC)</th></tr>
    </thead>
    <tbody id="recentBody"></tbody>
  </table>
</section>

<script>
  const params = new URLSearchParams(window.location.search);
  const CODE = params.get("code") || "";

  function apiUrl(path) {
    if (!CODE) return path;
    return path + (path.includes("?") ? "&" : "?") + "code=" + encodeURIComponent(CODE);
  }

  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function fmtUsd(n) {
    return "$" + Number(n || 0).toFixed(4);
  }

  async function loadStats() {
    document.getElementById("error").innerHTML = "";
    try {
      const res = await fetch(apiUrl("/api/stats"), { method: "GET" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      render(data);
    } catch (e) {
      document.getElementById("error").innerHTML =
        '<div class="error">Kunde inte hämta status: ' + escapeHtml(e.message) +
        '. Kontrollera att URL:en innehåller rätt ?code=...</div>';
    }
  }

  function render(data) {
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
    (data.recent || []).forEach((row) => {
      const tr = document.createElement("tr");
      const catClass = "cat-" + String(row.category || "").replace(/\\s/g, "");
      tr.innerHTML =
        "<td>" + escapeHtml(row.subject) + "</td>" +
        '<td><span class="cat-pill ' + catClass + '">' + escapeHtml(row.category) + "</span></td>" +
        '<td class="method-' + escapeHtml(row.method) + '">' + escapeHtml(row.method) + "</td>" +
        "<td>" + fmtUsd(row.costUsd) + "</td>" +
        "<td>" + escapeHtml(row.classifiedAt) + "</td>";
      body.appendChild(tr);
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
      const res = await fetch(apiUrl(path), { method: "POST" });
      if (!res.ok) throw new Error("HTTP " + res.status + ": " + (await res.text()));
      await loadStats();
    } catch (e) {
      document.getElementById("error").innerHTML =
        '<div class="error">Kunde inte ändra status: ' + escapeHtml(e.message) + "</div>";
      toggleBtn.disabled = false;
    }
  }

  document.getElementById("refreshBtn").addEventListener("click", loadStats);
  loadStats();
</script>
</body>
</html>
"""
