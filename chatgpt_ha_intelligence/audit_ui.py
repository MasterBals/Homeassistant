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


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def selected(current: str, value: str) -> str:
    return " selected" if current == value else ""


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
        limit=int(query.get("limit", "100") or 100),
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
    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ChatGPT MCP Protokoll</title>
<style>
:root{{color-scheme:dark;font-family:system-ui,sans-serif}}body{{margin:0;background:#111318;color:#e7e9ee}}
header{{position:sticky;top:0;z-index:3;display:flex;align-items:center;gap:22px;padding:14px 20px;background:#181b22;border-bottom:1px solid #303541}}
header strong{{font-size:18px}}nav a{{color:#b9c7ff;text-decoration:none;margin-right:14px}}nav a.active{{color:white;font-weight:700}}
main{{padding:18px}}.filters{{display:flex;flex-wrap:wrap;gap:12px;align-items:end;background:#181b22;padding:14px;border-radius:10px}}
label{{display:flex;flex-direction:column;gap:5px;font-size:12px;color:#aeb4c0}}input,select,button{{min-height:36px;border:1px solid #3b4250;border-radius:7px;background:#101217;color:#eef1f7;padding:6px 9px}}
button{{cursor:pointer;background:#2b4e9a;border-color:#3c63b8;font-weight:700}}.summary{{margin:14px 2px;color:#aeb4c0}}
table{{width:100%;border-collapse:collapse;background:#181b22;border-radius:10px;overflow:hidden}}th,td{{padding:9px 10px;border-bottom:1px solid #2d323d;text-align:left;vertical-align:top;font-size:13px}}
th{{position:sticky;top:55px;background:#20242d}}tr.fail td{{background:#311c20}}pre{{max-width:760px;white-space:pre-wrap;overflow-wrap:anywhere;background:#0f1115;padding:8px;border-radius:6px}}
.detail{{max-width:760px;white-space:pre-wrap}}.error{{color:#ff9ca7;margin-top:6px}}small,code{{color:#aeb4c0}}
</style></head><body><header><strong>ChatGPT Home Assistant MCP</strong><nav>
<a href="?view=audit" class="{'active' if view == 'audit' else ''}">MCP-Protokoll</a>
<a href="?view=brain" class="{'active' if view == 'brain' else ''}">Second Brain</a>
</nav></header><main>{content}</main></body></html>"""


async def index(request: Request) -> HTMLResponse:
    query = request.query_params
    view = query.get("view", "audit")

    if view == "brain":
        search = query.get("q", "")
        topic = query.get("topic", "")
        confidence = query.get("confidence", "")
        rows = brain_search(search, topic=topic or None, confidence=confidence or None, limit=100)
        body = "".join(
            f"""<tr><td>{esc(row['updated_at'])}</td><td>{esc(row['topic'])}</td>
            <td><strong>{esc(row['title'])}</strong><br><code>{esc(row['key'])}</code></td>
            <td>{esc(', '.join(row.get('tags', [])))}</td><td>{esc(row['confidence'])}</td>
            <td class="detail">{esc(row['content'])}</td></tr>"""
            for row in rows
        ) or '<tr><td colspan="6">Keine Einträge gefunden.</td></tr>'
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
        <div class="summary">{len(rows)} Treffer · {status['entries']} aktuelle Einträge · {status['revisions']} Revisionen</div>
        <table><thead><tr><th>Aktualisiert</th><th>Thema</th><th>Titel / Key</th><th>Tags</th><th>Vertrauen</th><th>Inhalt</th></tr></thead><tbody>{body}</tbody></table>
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
        f"""<tr class="{'ok' if row['success'] else 'fail'}"><td>{esc(row['ts'])}</td><td>{esc(row['source'])}</td>
        <td><strong>{esc(row['public_tool'])}</strong>{('<br><small>'+esc(row['upstream_tool'])+'</small>') if row.get('upstream_tool') and row['upstream_tool'] != row['public_tool'] else ''}</td>
        <td>{esc(row['kind'])}</td><td>{'OK' if row['success'] else 'Fehler'}</td><td>{esc(row['duration_ms'])} ms</td>
        <td><details><summary>Argumente</summary><pre>{esc(json.dumps(row.get('arguments', {}), ensure_ascii=False, indent=2))}</pre>
        {('<div class="error">'+esc(row['error_text'])+'</div>') if row.get('error_text') else ''}</details></td></tr>"""
        for row in rows
    ) or '<tr><td colspan="7">Keine MCP-Aufrufe für diesen Filter gefunden.</td></tr>'
    content = f"""
    <form method="get" class="filters"><input type="hidden" name="view" value="audit">
    <label>Quelle<select name="source"><option value="">Alle ChatGPT-MCP-Aufrufe</option>
    <option value="admin"{selected(source,'admin')}>Admin</option><option value="intelligence"{selected(source,'intelligence')}>Intelligence</option>
    <option value="local"{selected(source,'local')}>Lokal / Second Brain</option></select></label>
    <label>Typ<select name="kind"><option value="">Alle</option><option value="write"{selected(kind,'write')}>Schreib-/Servicebefehle</option>
    <option value="action"{selected(kind,'action')}>Aktionen/Scans</option><option value="read"{selected(kind,'read')}>Lesezugriffe</option>
    <option value="knowledge"{selected(kind,'knowledge')}>Second Brain</option><option value="audit"{selected(kind,'audit')}>Protokollabfragen</option></select></label>
    <label>Tool<input name="tool" value="{esc(tool)}" placeholder="z.B. CallService"></label>
    <label>Ergebnis<select name="success"><option value="">Alle</option><option value="1"{selected(success_raw,'1')}>Erfolgreich</option><option value="0"{selected(success_raw,'0')}>Fehler</option></select></label>
    <label>Zeitraum<select name="since_minutes"><option value="60"{selected(since,'60')}>1 Stunde</option><option value="360"{selected(since,'360')}>6 Stunden</option>
    <option value="1440"{selected(since,'1440')}>24 Stunden</option><option value="10080"{selected(since,'10080')}>7 Tage</option><option value="0"{selected(since,'0')}>Gesamt</option></select></label>
    <label>Anzahl<input type="number" min="1" max="1000" name="limit" value="{limit}"></label><button type="submit">Filtern</button></form>
    <div class="summary">{len(rows)} Treffer · Dieses Protokoll enthält ausschliesslich Tool-Aufrufe, die über den Unified MCP eingehen. Geheimnisse und grosse Datei-Inhalte werden vor dem Speichern redigiert.</div>
    <table><thead><tr><th>Zeit</th><th>Quelle</th><th>MCP-Tool</th><th>Typ</th><th>Status</th><th>Dauer</th><th>Details</th></tr></thead><tbody>{body}</tbody></table>
    """
    return HTMLResponse(page_shell("audit", content))


app = Starlette(routes=[
    Route("/", index, methods=["GET"]),
    Route("/api/audit", api_audit, methods=["GET"]),
    Route("/api/brain", api_brain, methods=["GET"]),
])


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
