from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.environ.get("CHATGPT_HA_DATA_DIR", "/data"))
AUDIT_DB = DATA_DIR / "mcp_audit.sqlite3"
BRAIN_DB = DATA_DIR / "second_brain.sqlite3"
AUDIT_MAX_ENTRIES = int(os.environ.get("AUDIT_MAX_ENTRIES", "20000"))
SENSITIVE = ("token", "password", "secret", "api_key", "apikey", "authorization", "cookie", "credential")
LARGE_KEYS = {"content", "old", "new", "template"}


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def conn(path: Path) -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=5000")
    return db


def init() -> None:
    with conn(AUDIT_DB) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS audit(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts TEXT NOT NULL,
          source TEXT NOT NULL,
          public_tool TEXT NOT NULL,
          upstream_tool TEXT,
          kind TEXT NOT NULL,
          success INTEGER NOT NULL,
          duration_ms INTEGER NOT NULL,
          arguments_json TEXT NOT NULL,
          error_text TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit(ts DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_tool ON audit(public_tool);
        CREATE INDEX IF NOT EXISTS idx_audit_source ON audit(source);
        CREATE INDEX IF NOT EXISTS idx_audit_kind ON audit(kind);
        """)
    with conn(BRAIN_DB) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS knowledge(
          topic TEXT NOT NULL,
          key TEXT NOT NULL,
          title TEXT NOT NULL,
          content TEXT NOT NULL,
          tags_json TEXT NOT NULL,
          source TEXT NOT NULL,
          confidence TEXT NOT NULL,
          metadata_json TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY(topic,key)
        );
        CREATE TABLE IF NOT EXISTS knowledge_history(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          topic TEXT NOT NULL,
          key TEXT NOT NULL,
          title TEXT NOT NULL,
          content TEXT NOT NULL,
          tags_json TEXT NOT NULL,
          source TEXT NOT NULL,
          confidence TEXT NOT NULL,
          metadata_json TEXT NOT NULL,
          archived_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_knowledge_topic ON knowledge(topic);
        """)


def sanitize(value: Any, key: str | None = None) -> Any:
    if key:
        lowered = key.lower()
        if any(word in lowered for word in SENSITIVE):
            return "<redacted>"
        if lowered in LARGE_KEYS and isinstance(value, str):
            digest = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:16]
            return f"<{len(value)} chars sha256:{digest}>"
    if isinstance(value, dict):
        return {str(k): sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v) for v in value]
    if isinstance(value, str):
        return value if len(value) <= 1200 else value[:1200] + f"... <{len(value)} chars>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return repr(value)


WRITE_TOOLS = {
    "WriteConfigFile", "ReplaceConfigText", "SaveDashboard", "PatchDashboard", "CallService",
    "StartConfigFlow", "ConfigureConfigFlow", "AbortConfigFlow", "RestoreChange",
}
ACTION_TOOLS = {"network_scan_start", "bluetooth_scan"}


def classify(tool: str) -> str:
    if tool in WRITE_TOOLS:
        return "write"
    if tool in ACTION_TOOLS:
        return "action"
    if tool.startswith("SecondBrain"):
        return "knowledge"
    if tool.startswith("McpAudit"):
        return "audit"
    return "read"


def audit_add(*, source: str, public_tool: str, upstream_tool: str | None,
              arguments: dict[str, Any] | None, success: bool, duration_ms: int,
              error_text: str | None = None) -> None:
    with conn(AUDIT_DB) as db:
        db.execute(
            """INSERT INTO audit(ts,source,public_tool,upstream_tool,kind,success,duration_ms,arguments_json,error_text)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (utcnow(), source, public_tool, upstream_tool, classify(public_tool), 1 if success else 0,
             max(0, int(duration_ms)), json.dumps(sanitize(arguments or {}), ensure_ascii=False), error_text),
        )
        if AUDIT_MAX_ENTRIES > 0:
            db.execute(
                "DELETE FROM audit WHERE id NOT IN (SELECT id FROM audit ORDER BY id DESC LIMIT ?)",
                (AUDIT_MAX_ENTRIES,),
            )


def audit_query(*, source: str | None = None, tool: str | None = None,
                kind: str | None = None, success: bool | None = None,
                since_minutes: int | None = None, limit: int = 100,
                include_arguments: bool = True) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if source:
        clauses.append("source=?")
        params.append(source)
    if tool:
        clauses.append("(public_tool LIKE ? OR upstream_tool LIKE ?)")
        pattern = f"%{tool}%"
        params.extend([pattern, pattern])
    if kind:
        clauses.append("kind=?")
        params.append(kind)
    if success is not None:
        clauses.append("success=?")
        params.append(1 if success else 0)
    if since_minutes and since_minutes > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
        clauses.append("ts>=?")
        params.append(cutoff.isoformat())
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    limit = max(1, min(int(limit), 1000))
    params.append(limit)
    with conn(AUDIT_DB) as db:
        rows = db.execute(
            "SELECT id,ts,source,public_tool,upstream_tool,kind,success,duration_ms,arguments_json,error_text "
            "FROM audit" + where + " ORDER BY id DESC LIMIT ?", params,
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["success"] = bool(item["success"])
        raw_arguments = item.pop("arguments_json")
        if include_arguments:
            try:
                item["arguments"] = json.loads(raw_arguments)
            except Exception:
                item["arguments"] = {}
        result.append(item)
    return result


def audit_status() -> dict[str, Any]:
    with conn(AUDIT_DB) as db:
        count = db.execute("SELECT COUNT(*) FROM audit").fetchone()[0]
        last = db.execute("SELECT ts FROM audit ORDER BY id DESC LIMIT 1").fetchone()
    return {
        "entries": int(count),
        "max_entries": AUDIT_MAX_ENTRIES,
        "database": str(AUDIT_DB),
        "last_entry": last[0] if last else None,
    }


def brain_upsert(*, topic: str, key: str, title: str, content: str,
                 tags: list[str] | None = None, source: str = "chatgpt_mcp",
                 confidence: str = "verified", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    topic, key, title, content = (value.strip() for value in (topic, key, title, content))
    if not all((topic, key, title, content)):
        raise ValueError("topic, key, title and content are required")
    now = utcnow()
    tags_json = json.dumps(sorted(set(tags or [])), ensure_ascii=False)
    metadata_json = json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)
    with conn(BRAIN_DB) as db:
        previous = db.execute("SELECT * FROM knowledge WHERE topic=? AND key=?", (topic, key)).fetchone()
        action = "created"
        created_at = now
        if previous:
            action = "updated"
            created_at = previous["created_at"]
            db.execute(
                """INSERT INTO knowledge_history(topic,key,title,content,tags_json,source,confidence,metadata_json,archived_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (previous["topic"], previous["key"], previous["title"], previous["content"], previous["tags_json"],
                 previous["source"], previous["confidence"], previous["metadata_json"], now),
            )
        db.execute(
            """INSERT INTO knowledge(topic,key,title,content,tags_json,source,confidence,metadata_json,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(topic,key) DO UPDATE SET
                 title=excluded.title, content=excluded.content, tags_json=excluded.tags_json,
                 source=excluded.source, confidence=excluded.confidence,
                 metadata_json=excluded.metadata_json, updated_at=excluded.updated_at""",
            (topic, key, title, content, tags_json, source, confidence, metadata_json, created_at, now),
        )
    return {"topic": topic, "key": key, "action": action, "updated_at": now}


def _brain_row(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["tags"] = json.loads(item.pop("tags_json"))
    item["metadata"] = json.loads(item.pop("metadata_json"))
    return item


def brain_get(topic: str, key: str, include_history: bool = False) -> dict[str, Any] | None:
    with conn(BRAIN_DB) as db:
        row = db.execute("SELECT * FROM knowledge WHERE topic=? AND key=?", (topic, key)).fetchone()
        if row is None:
            return None
        result = _brain_row(row)
        if include_history:
            history = db.execute(
                """SELECT topic,key,title,content,tags_json,source,confidence,metadata_json,archived_at
                   FROM knowledge_history WHERE topic=? AND key=? ORDER BY id DESC LIMIT 50""",
                (topic, key),
            ).fetchall()
            result["history"] = [_brain_row(item) for item in history]
        return result


def brain_search(query: str, *, topic: str | None = None,
                 confidence: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if topic:
        clauses.append("topic=?")
        params.append(topic)
    if confidence:
        clauses.append("confidence=?")
        params.append(confidence)
    for term in [item.lower() for item in query.split() if item.strip()]:
        pattern = f"%{term}%"
        clauses.append("(lower(title) LIKE ? OR lower(content) LIKE ? OR lower(tags_json) LIKE ? OR lower(key) LIKE ?)")
        params.extend([pattern, pattern, pattern, pattern])
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    limit = max(1, min(int(limit), 200))
    params.append(limit)
    with conn(BRAIN_DB) as db:
        rows = db.execute("SELECT * FROM knowledge" + where + " ORDER BY updated_at DESC LIMIT ?", params).fetchall()
    return [_brain_row(row) for row in rows]


def brain_status() -> dict[str, Any]:
    with conn(BRAIN_DB) as db:
        entries = db.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
        revisions = db.execute("SELECT COUNT(*) FROM knowledge_history").fetchone()[0]
        topics = [
            {"topic": row[0], "count": row[1]}
            for row in db.execute("SELECT topic,COUNT(*) FROM knowledge GROUP BY topic ORDER BY COUNT(*) DESC,topic")
        ]
        last_updated = db.execute("SELECT MAX(updated_at) FROM knowledge").fetchone()[0]
    return {
        "entries": int(entries),
        "revisions": int(revisions),
        "topics": topics,
        "database": str(BRAIN_DB),
        "last_updated": last_updated,
    }


init()
