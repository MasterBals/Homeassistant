from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

APP_DIR = Path('/app')
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from state_store import brain_get, brain_search, brain_status, brain_upsert  # noqa: E402


def register_second_brain_tools(mcp: Any) -> None:
    @mcp.tool()
    async def second_brain_status() -> dict[str, Any]:
        """Show Second Brain counts, revision history status and last update timestamp."""
        return brain_status()

    @mcp.tool()
    async def second_brain_search(
        query: str = '',
        topic: str = '',
        confidence: str = '',
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search durable Home Assistant/Yealink findings. Use this before continuing prior investigations."""
        rows = brain_search(
            query,
            topic=topic or None,
            confidence=confidence or None,
            limit=limit,
        )
        return {'count': len(rows), 'entries': rows}

    @mcp.tool()
    async def second_brain_get(topic: str, key: str, include_history: bool = True) -> dict[str, Any]:
        """Read one current finding and, by default, all preserved previous revisions."""
        entry = brain_get(topic, key, include_history=include_history)
        return {'found': entry is not None, 'entry': entry}

    @mcp.tool()
    async def second_brain_upsert(
        topic: str,
        key: str,
        title: str,
        content: str,
        confidence: str = 'verified',
        tags: list[str] | None = None,
        source: str = 'chatgpt_mcp',
        change_reason: str = '',
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist a durable finding immediately after it is verified.

        Reuse the SAME topic/key when a later investigation corrects or refines an
        earlier finding. The previous row is then preserved as an immutable history
        revision with its original timestamps and the new correction reason. Never
        store passwords, API keys, tokens or other secrets in the Second Brain.
        """
        return brain_upsert(
            topic=topic,
            key=key,
            title=title,
            content=content,
            confidence=confidence,
            tags=tags,
            source=source,
            change_reason=change_reason,
            metadata=metadata,
        )
