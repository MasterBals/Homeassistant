from __future__ import annotations

import html
import json
import os

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from state_store import audit_query, audit_status, brain_search, brain_status

HOST = os.environ.get("AUDIT_UI_HOST", "0.0.0.0")
PORT = int(os.environ.get("AUDIT_UI_PORT", "8099"))

BASE_STYLE = """
:root {
  color-scheme: dark;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --bg: #111318;
  --panel: #181b22;
  --panel-2: #20242d;
  --border: #303541;
  --border-soft: #2d323d;
  --text: #e7e9ee;
  --muted: #aeb4c0;
  --accent: #4f7bd9;
  --accent-strong: #2b4e9a;
  --ok: #77d890;
  --fail-bg: #311c20;
  --fail: #ff9ca7;
}
* { box-sizing: border-box; }
html, body { min-height: 100%; }
body { margin: 0; background: var(--bg); color: var(--text); }
header {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 22px;
  min-height: 54px;
  padding: 12px 20px;
  background: var(--panel);
  border-bottom: 1px solid var(--border);
}
header strong { font-size: 18px; white-space: nowrap; }
nav { display: flex; align-items: center; gap: 14px; }
nav a { color: #b9c7ff; text-decoration: none; }
nav a.active { color: white; font-weight: 700; }
main { padding: 14px 18px 18px; }
.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 12px;
  align-items: end;
  background: var(--panel);
  padding: 12px;
  border-radius: 10px;
  border: 1px solid rgba(255,255,255,.025);
}
.filters label {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 118px;
  font-size: 12px;
  color: var(--muted);
}
.filters label.tool-field { min-width: 190px; flex: 0 1 230px; }
.filters label.limit-field { min-width: 76px; max-width: 90px; }
input, select, button {
  min-height: 36px;
  border: 1px solid #3b4250;
  border-radius: 7px;
  background: #101217;
  color: #eef1f7;
  padding: 6px 9px;
  font: inherit;
}
button {
  cursor: pointer;
  background: var(--accent-strong);
  border-color: #3c63b8;
  font-weight: 700;
  padding-inline: 14px;
}
button:hover { background: #365eaf; }
.live-control {
  display: inline-flex !important;
  flex-direction: row !important;
  align-items: center;
  justify-content: center;
  gap: 8px !important;
  min-width: 92px !important;
  min-height: 36px;
  padding: 6px 10px;
  border: 1px solid #3b4250;
  border-radius: 7px;
  background: #101217;
  color: var(--text) !important;
  cursor: pointer;
  user-select: none;
}
.live-control input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}
.live-check {
  display: inline-grid;
  place-items: center;
  width: 19px;
  height: 19px;
  flex: 0 0 19px;
  border: 1px solid #566071;
  border-radius: 5px;
  background: #151922;
  color: transparent;
  font-weight: 900;
  line-height: 1;
}
.live-control input:checked + .live-check {
  background: var(--accent);
  border-color: #6d94eb;
  color: white;
}
.live-control input:focus-visible + .live-check { outline: 2px solid #8aa8eb; outline-offset: 2px; }
.live-state { font-weight: 700; }
.summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 14px;
  min-height: 36px;
  margin: 8px 2px;
  color: var(--muted);
  font-size: 13px;
}
.summary-main { flex: 1 1 500px; }
.refresh-state { white-space: nowrap; color: #cbd2df; }
.live-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-right: 6px;
  border-radius: 50%;
  background: #657080;
  vertical-align: 1px;
}
.live-dot.on { background: var(--ok); box-shadow: 0 0 0 3px rgba(119,216,144,.12); }
.table-wrap {
  width: 100%;
  max-height: calc(100vh - 205px);
  overflow: auto;
  border: 1px solid var(--border-soft);
  border-radius: 10px;
  background: var(--panel);
  scrollbar-gutter: stable;
}
table {
  width: 100%;
  min-width: 930px;
  border-collapse: separate;
  border-spacing: 0;
  background: var(--panel);
}
th, td {
  padding: 9px 10px;
  border-bottom: 1px solid var(--border-soft);
  text-align: left;
  vertical-align: middle;
  font-size: 13px;
  line-height: 1.35;
}
thead th {
  position: sticky;
  top: 0;
  z-index: 5;
  background: var(--panel-2);
  box-shadow: 0 1px 0 var(--border);
  white-space: nowrap;
}
tbody tr:last-child td { border-bottom: 0; }
tbody tr:hover td { background: rgba(255,255,255,.022); }
tr.fail td { background: var(--fail-bg); }
tr.fail:hover td { background: #3a2025; }
th.col-time, td.col-time { width: 190px; min-width: 190px; white-space: nowrap; }
th.col-source, td.col-source { width: 95px; min-width: 95px; }
th.col-tool, td.col-tool { width: 190px; min-width: 170px; }
th.col-kind, td.col-kind { width: 85px; min-width: 80px; }
th.col-status, td.col-status { width: 82px; min-width: 78px; }
th.col-duration, td.col-duration { width: 100px; min-width: 90px; white-space: nowrap; }
th.col-details, td.col-details { min-width: 150px; }
.status-ok { color: var(--ok); font-weight: 650; }
.status-fail { color: var(--fail); font-weight: 650; }
details > summary { cursor: pointer; white-space: nowrap; }
pre {
  max-width: min(760px, 70vw);
  max-height: 360px;
  margin: 8px 0 0;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: #0f1115;
  padding: 8px;
  border-radius: 6px;
  border: 1px solid #272c35;
}
.detail { max-width: 760px; white-space: pre-wrap; }
.error { color: var(--fail); margin-top: 6px; }
small, code { color: var(--muted); }
.empty-row td { padding: 24px 12px; text-align: center; color: var(--muted); }
@media (max-width: 900px) {
  header { gap: 12px; padding-inline: 12px; }
  header strong { font-size: 16px; }
  main { padding: 10px; }
  .filters { gap: 8px; }
  .filters label { flex: 1 1 130px; }
  .table-wrap { max-height: calc(100vh - 235px); }
}
"""

AUDIT_SCRIPT = r"""
<script>
(() => {
  const form = document.getElementById("audit-filters");
  if (!form) return;

  const tbody = document.getElementById("audit-body");
  const countNode = document.getElementById("audit-count");
  const refreshNode = document.getElementById("last-refresh");
  const dotNode = document.getElementById("live-dot");
  const liveToggle = document.getElementById("live-toggle");
  const LIVE_KEY = "chatgpt_mcp_audit_live";
  const REFRESH_MS = 3000;
  let timer = null;
  let refreshing = false;

  const escapeHtml = (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  const localDate = (value) => {
    if (!value) return "–";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat("de-CH", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(date);
  };

  const localTime = (date = new Date()) => new Intl.DateTimeFormat("de-CH", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);

  const formatStaticTimes = () => {
    document.querySelectorAll("time.local-time[datetime]").forEach((node) => {
      node.textContent = localDate(node.getAttribute("datetime"));
      node.title = node.getAttribute("datetime") || "";
    });
  };

  const currentParams = () => {
    const data = new FormData(form);
    const params = new URLSearchParams();
    for (const [key, value] of data.entries()) {
      if (key === "view") continue;
      params.set(key, String(value));
    }
    params.set("include_arguments", "1");
    return params;
  };

  const updateBrowserUrl = () => {
    const params = currentParams();
    params.delete("include_arguments");
    params.set("view", "audit");
    history.replaceState(null, "", `${location.pathname}?${params.toString()}`);
  };

  const rowHtml = (row) => {
    const failClass = row.success ? "ok" : "fail";
    const statusClass = row.success ? "status-ok" : "status-fail";
    const statusText = row.success ? "OK" : "Fehler";
    const upstream = row.upstream_tool && row.upstream_tool !== row.public_tool
      ? `<br><small>${escapeHtml(row.upstream_tool)}</small>`
      : "";
    const args = escapeHtml(JSON.stringify(row.arguments || {}, null, 2));
    const error = row.error_text
      ? `<div class="error">${escapeHtml(row.error_text)}</div>`
      : "";
    const rawTs = escapeHtml(row.ts || "");
    return `<tr class="${failClass}">
      <td class="col-time"><time class="local-time" datetime="${rawTs}" title="${rawTs}">${escapeHtml(localDate(row.ts))}</time></td>
      <td class="col-source">${escapeHtml(row.source)}</td>
      <td class="col-tool"><strong>${escapeHtml(row.public_tool)}</strong>${upstream}</td>
      <td class="col-kind">${escapeHtml(row.kind)}</td>
      <td class="col-status ${statusClass}">${statusText}</td>
      <td class="col-duration">${escapeHtml(row.duration_ms)} ms</td>
      <td class="col-details"><details><summary>Argumente</summary><pre>${args}</pre>${error}</details></td>
    </tr>`;
  };

  const refresh = async ({ updateUrl = false } = {}) => {
    if (refreshing) return;
    refreshing = true;
    try {
      const params = currentParams();
      const response = await fetch(`api/audit?${params.toString()}`, {
        cache: "no-store",
        headers: { "Accept": "application/json" },
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      const rows = Array.isArray(payload.entries) ? payload.entries : [];
      tbody.innerHTML = rows.length
        ? rows.map(rowHtml).join("")
        : '<tr class="empty-row"><td colspan="7">Keine MCP-Aufrufe für diesen Filter gefunden.</td></tr>';
      countNode.textContent = String(rows.length);
      refreshNode.textContent = `Aktualisiert ${localTime()}`;
      refreshNode.title = `Lokale Browserzeit: ${Intl.DateTimeFormat().resolvedOptions().timeZone || "lokal"}`;
      if (updateUrl) updateBrowserUrl();
    } catch (error) {
      refreshNode.textContent = `Aktualisierung fehlgeschlagen: ${error.message || error}`;
    } finally {
      refreshing = false;
    }
  };

  const stopLive = () => {
    if (timer !== null) window.clearInterval(timer);
    timer = null;
    dotNode.classList.remove("on");
  };

  const startLive = () => {
    stopLive();
    dotNode.classList.add("on");
    refresh();
    timer = window.setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, REFRESH_MS);
  };

  const setLive = (enabled) => {
    liveToggle.checked = enabled;
    localStorage.setItem(LIVE_KEY, enabled ? "1" : "0");
    if (enabled) startLive(); else stopLive();
  };

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    refresh({ updateUrl: true });
  });

  liveToggle.addEventListener("change", () => setLive(liveToggle.checked));

  form.querySelectorAll("select, input:not(#live-toggle)").forEach((control) => {
    control.addEventListener("change", () => {
      if (liveToggle.checked) refresh({ updateUrl: true });
    });
  });

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && liveToggle.checked) refresh();
  });

  formatStaticTimes();
  const stored = localStorage.getItem(LIVE_KEY);
  setLive(stored === null ? true : stored === "1");
})();
</script>
"""

LOCAL_TIME_SCRIPT = r"""
<script>
(() => {
  const fmt = new Intl.DateTimeFormat("de-CH", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  document.querySelectorAll("time.local-time[datetime]").forEach((node) => {
    const raw = node.getAttribute("datetime");
    const date = new Date(raw);
    if (!Number.isNaN(date.getTime())) node.textContent = fmt.format(date);
    node.title = raw || "";
  });
})();
</script>
"""


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def selected(current: str, value: str) -> str:
    return " selected" if current == value else ""


def local_time_cell(value: object) -> str:
    raw = esc(value)
    return f'<time class="local-time" datetime="{raw}" title="{raw}">{raw}</time>'


async def api_audit(request: Request) -> JSONResponse:
    query = request.query_params
    success_raw = query.get("success", "")
    success = None if success_raw == "" else success_raw == "1"
    rows = audit_query(
        source=query.get("source") or None,
        tool=query.get("tool") or None,
        kind=query.get("kind") or None,
        success=success,
        since_minutes=int(query.get("since_minutes", "0") or 0) or None,
        limit=min(max(int(query.get("limit", "100") or 100), 1), 1000),
        include_arguments=query.get("include_arguments", "1") != "0",
    )
    return JSONResponse({"status": audit_status(), "count": len(rows), "entries": rows})


async def api_brain(request: Request) -> JSONResponse:
    query = request.query_params
    rows = brain_search(
        query.get("q", ""),
        topic=query.get("topic") or None,
        confidence=query.get("confidence") or None,
        limit=int(query.get("limit", "50") or 50),
    )
    return JSONResponse({"status": brain_status(), "count": len(rows), "entries": rows})


def page_shell(view: str, content: str) -> str:
    audit_active = "active" if view == "audit" else ""
    brain_active = "active" if view == "brain" else ""
    script = AUDIT_SCRIPT if view == "audit" else LOCAL_TIME_SCRIPT
    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ChatGPT MCP Protokoll</title>
<style>{BASE_STYLE}</style></head><body>
<header><strong>ChatGPT Home Assistant MCP</strong><nav>
<a href="?view=audit" class="{audit_active}">MCP-Protokoll</a>
<a href="?view=brain" class="{brain_active}">Second Brain</a>
</nav></header><main>{content}</main>{script}</body></html>"""


async def index(request: Request) -> HTMLResponse:
    query = request.query_params
    view = query.get("view", "audit")

    if view == "brain":
        search = query.get("q", "")
        topic = query.get("topic", "")
        confidence = query.get("confidence", "")
        rows = brain_search(search, topic=topic or None, confidence=confidence or None, limit=100)
        body = "".join(
            f"""<tr><td class="col-time">{local_time_cell(row['updated_at'])}</td><td>{esc(row['topic'])}</td>
            <td><strong>{esc(row['title'])}</strong><br><code>{esc(row['key'])}</code></td>
            <td>{esc(', '.join(row.get('tags', [])))}</td><td>{esc(row['confidence'])}</td>
            <td class="detail">{esc(row['content'])}</td></tr>"""
            for row in rows
        ) or '<tr class="empty-row"><td colspan="6">Keine Einträge gefunden.</td></tr>'
        status = brain_status()
        content = f"""
        <form method="get" class="filters"><input type="hidden" name="view" value="brain">
        <label>Suche<input name="q" value="{esc(search)}" placeholder="z.B. VCM36-W RC8"></label>
        <label>Thema<input name="topic" value="{esc(topic)}" placeholder="z.B. yealink"></label>
        <label>Vertrauen<select name="confidence"><option value="">Alle</option>
        <option value="verified"{selected(confidence,'verified')}>Verifiziert</option>
        <option value="probable"{selected(confidence,'probable')}>Wahrscheinlich</option>
        <option value="hypothesis"{selected(confidence,'hypothesis')}>Hypothese</option></select></label>
        <button type="submit">Filtern</button></form>
        <div class="summary"><span>{len(rows)} Treffer · {status['entries']} aktuelle Einträge · {status['revisions']} Revisionen</span></div>
        <div class="table-wrap"><table><thead><tr><th class="col-time">Aktualisiert</th><th>Thema</th><th>Titel / Key</th><th>Tags</th><th>Vertrauen</th><th>Inhalt</th></tr></thead><tbody>{body}</tbody></table></div>
        """
        return HTMLResponse(page_shell("brain", content))

    source = query.get("source", "")
    tool = query.get("tool", "")
    kind = query.get("kind", "")
    success_raw = query.get("success", "")
    since = query.get("since_minutes", "1440")
    limit = min(max(int(query.get("limit", "200") or 200), 1), 1000)
    success = None if success_raw == "" else success_raw == "1"
    rows = audit_query(
        source=source or None,
        tool=tool or None,
        kind=kind or None,
        success=success,
        since_minutes=int(since or 0) or None,
        limit=limit,
        include_arguments=True,
    )
    body = "".join(
        f"""<tr class="{'ok' if row['success'] else 'fail'}"><td class="col-time">{local_time_cell(row['ts'])}</td><td class="col-source">{esc(row['source'])}</td>
        <td class="col-tool"><strong>{esc(row['public_tool'])}</strong>{('<br><small>'+esc(row['upstream_tool'])+'</small>') if row.get('upstream_tool') and row['upstream_tool'] != row['public_tool'] else ''}</td>
        <td class="col-kind">{esc(row['kind'])}</td><td class="col-status {'status-ok' if row['success'] else 'status-fail'}">{'OK' if row['success'] else 'Fehler'}</td><td class="col-duration">{esc(row['duration_ms'])} ms</td>
        <td class="col-details"><details><summary>Argumente</summary><pre>{esc(json.dumps(row.get('arguments', {}), ensure_ascii=False, indent=2))}</pre>
        {('<div class="error">'+esc(row['error_text'])+'</div>') if row.get('error_text') else ''}</details></td></tr>"""
        for row in rows
    ) or '<tr class="empty-row"><td colspan="7">Keine MCP-Aufrufe für diesen Filter gefunden.</td></tr>'
    content = f"""
    <form method="get" class="filters" id="audit-filters"><input type="hidden" name="view" value="audit">
    <label>Quelle<select name="source"><option value="">Alle ChatGPT-MCP-Aufrufe</option>
    <option value="admin"{selected(source,'admin')}>Admin</option><option value="intelligence"{selected(source,'intelligence')}>Intelligence</option>
    <option value="local"{selected(source,'local')}>Lokal / Second Brain</option></select></label>
    <label>Typ<select name="kind"><option value="">Alle</option><option value="write"{selected(kind,'write')}>Schreib-/Servicebefehle</option>
    <option value="action"{selected(kind,'action')}>Aktionen/Scans</option><option value="read"{selected(kind,'read')}>Lesezugriffe</option>
    <option value="knowledge"{selected(kind,'knowledge')}>Second Brain</option><option value="audit"{selected(kind,'audit')}>Protokollabfragen</option></select></label>
    <label class="tool-field">Tool<input name="tool" value="{esc(tool)}" placeholder="z.B. CallService"></label>
    <label>Ergebnis<select name="success"><option value="">Alle</option><option value="1"{selected(success_raw,'1')}>Erfolgreich</option><option value="0"{selected(success_raw,'0')}>Fehler</option></select></label>
    <label>Zeitraum<select name="since_minutes"><option value="60"{selected(since,'60')}>1 Stunde</option><option value="360"{selected(since,'360')}>6 Stunden</option>
    <option value="1440"{selected(since,'1440')}>24 Stunden</option><option value="10080"{selected(since,'10080')}>7 Tage</option><option value="0"{selected(since,'0')}>Gesamt</option></select></label>
    <label class="limit-field">Anzahl<input type="number" min="1" max="1000" name="limit" value="{limit}"></label>
    <label class="live-control" title="Protokoll automatisch alle 3 Sekunden aktualisieren">
      <input id="live-toggle" type="checkbox" checked><span class="live-check">✓</span><span class="live-state">Live</span>
    </label>
    <button type="submit">Filtern</button></form>
    <div class="summary">
      <span class="summary-main"><strong id="audit-count">{len(rows)}</strong> Treffer · Dieses Protokoll enthält ausschliesslich Tool-Aufrufe, die über den Unified MCP eingehen. Geheimnisse und grosse Datei-Inhalte werden vor dem Speichern redigiert.</span>
      <span class="refresh-state"><span class="live-dot" id="live-dot"></span><span id="last-refresh">Lokale Zeit</span></span>
    </div>
    <div class="table-wrap"><table><thead><tr><th class="col-time">Zeit</th><th class="col-source">Quelle</th><th class="col-tool">MCP-Tool</th><th class="col-kind">Typ</th><th class="col-status">Status</th><th class="col-duration">Dauer</th><th class="col-details">Details</th></tr></thead><tbody id="audit-body">{body}</tbody></table></div>
    """
    return HTMLResponse(page_shell("audit", content))


app = Starlette(routes=[
    Route("/", index, methods=["GET"]),
    Route("/api/audit", api_audit, methods=["GET"]),
    Route("/api/brain", api_brain, methods=["GET"]),
])


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
