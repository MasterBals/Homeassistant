from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from state_store import BRAIN_DB, brain_status, brain_upsert

LEGACY_DB = Path("/homeassistant/.chatgpt_second_brain.sqlite3")


def migrate() -> dict:
    status = brain_status()
    if status["entries"] > 0:
        return {"ok": True, "action": "skip_target_not_empty", "entries": status["entries"]}
    if not LEGACY_DB.exists():
        return {"ok": True, "action": "skip_legacy_missing", "legacy": str(LEGACY_DB)}

    legacy = sqlite3.connect(LEGACY_DB)
    legacy.row_factory = sqlite3.Row
    try:
        rows = legacy.execute(
            "SELECT * FROM notes WHERE status != ? ORDER BY updated_at ASC", ("deleted",)
        ).fetchall()
    finally:
        legacy.close()

    migrated = 0
    for row in rows:
        try:
            tags = json.loads(row["tags_json"] or "[]")
        except Exception:
            tags = []
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except Exception:
            metadata = {}
        brain_upsert(
            topic=row["topic"],
            key=row["key"],
            title=row["title"] or row["key"],
            content=row["content"],
            tags=tags,
            source=row["source"] or "legacy_second_brain",
            confidence=row["confidence"] or "verified",
            metadata={**metadata, "legacy_created_at": row["created_at"], "legacy_updated_at": row["updated_at"]},
        )
        migrated += 1

    return {"ok": True, "action": "migrated", "entries": migrated, "legacy": str(LEGACY_DB), "target": str(BRAIN_DB)}


if __name__ == "__main__":
    print(json.dumps(migrate(), ensure_ascii=False))
