from __future__ import annotations

import json
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx2
import mcp.types as types
import uvicorn
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.server.lowlevel import Server
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from state_store import (
    audit_add,
    audit_query,
    audit_status,
    brain_get,
    brain_search,
    brain_status,
    brain_upsert,
)

VERSION = "2.2.0"
HOST = os.environ.get("UNIFIED_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("UNIFIED_MCP_PORT", "8765"))
INTELLIGENCE_URL = os.environ.get("INTELLIGENCE_MCP_URL", "http://127.0.0.1:18765/mcp")
INTELLIGENCE_TOKEN = os.environ.get("INTELLIGENCE_MCP_TOKEN", "")
ADMIN_URL = os.environ.get("HA_ADMIN_MCP_URL", "http://supervisor/core/api/mcp/chatgpt_ha_admin")
ADMIN_TOKEN = os.environ.get("HA_ADMIN_MCP_TOKEN", "")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("ha-unified-mcp")

TOOL_ROUTES: dict[str, tuple[str, str]] = {}
LAST_ERRORS: dict[str, str | None] = {"admin": None, "intelligence": None}
SOURCE_TOOL_COUNTS: dict[str, int] = {"admin": 0, "intelligence": 0}
SOURCE_TOOL_NAMES: dict[str, list[str]] = {"admin": [], "intelligence": []}

LOCAL_TOOL_SPECS = [
    types.Tool(
        name="UnifiedStatus",
        description="Diagnose the unified Home Assistant MCP and show Admin/Intelligence availability plus Second Brain and audit status.",
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    types.Tool(
        name="McpAuditQuery",
        description="Query the persistent protocol of ChatGPT tool calls received through this Unified MCP. Supports filters for source, tool, kind, result and time window.",
        inputSchema={
            "type": "object",
            "properties": {
                "source": {"type": "string", "enum": ["admin", "intelligence", "local"]},
                "tool": {"type": "string"},
                "kind": {"type": "string", "enum": ["read", "write", "action", "knowledge", "audit"]},
                "success": {"type": "boolean"},
                "since_minutes": {"type": "integer", "minimum": 1},
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
                "include_arguments": {"type": "boolean", "default": True},
            },
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="McpAuditStatus",
        description="Show size and last-entry timestamp of the persistent MCP audit protocol.",
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    types.Tool(
        name="SecondBrainSearch",
        description="Search persistent technical knowledge from previous Home Assistant investigations. Use this early when continuing an existing project or debugging a previously analysed device.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "default": ""},
                "topic": {"type": "string"},
                "confidence": {"type": "string", "enum": ["verified", "probable", "hypothesis"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 20},
            },
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="SecondBrainGet",
        description="Read one persistent Second Brain entry by topic and stable key, optionally including its revision history.",
        inputSchema={
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "key": {"type": "string"},
                "include_history": {"type": "boolean", "default": False},
            },
            "required": ["topic", "key"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="SecondBrainUpsert",
        description="Persist or update a durable technical finding. Use stable topic/key identifiers, distinguish verified findings from hypotheses, and avoid storing secrets or personal/private room mappings in public-project knowledge.",
        inputSchema={
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "key": {"type": "string"},
                "title": {"type": "string"},
                "content": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "source": {"type": "string", "default": "chatgpt_mcp"},
                "confidence": {"type": "string", "enum": ["verified", "probable", "hypothesis"], "default": "verified"},
                "metadata": {"type": "object", "additionalProperties": True},
            },
            "required": ["topic", "key", "title", "content"],
            "additionalProperties": False,
        },
    ),
    types.Tool(
        name="SecondBrainStatus",
        description="Show persistent Second Brain entry/revision counts and topics.",
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
]
LOCAL_TOOL_NAMES = {tool.name for tool in LOCAL_TOOL_SPECS}


@asynccontextmanager
async def upstream(url: str, token: str, timeout: float = 300.0):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx2.AsyncClient(headers=headers, timeout=timeout) as http_client:
        transport = streamable_http_client(url, http_client=http_client)
        async with Client(transport, cache=None) as client:
            yield client


async def _list_source(source: str, url: str, token: str) -> list[types.Tool]:
    try:
        async with upstream(url, token, timeout=20.0) as client:
            result = await client.list_tools()
        tools = list(result.tools)
        LAST_ERRORS[source] = None
        SOURCE_TOOL_COUNTS[source] = len(tools)
        SOURCE_TOOL_NAMES[source] = [tool.name for tool in tools]
        return tools
    except Exception as exc:
        LAST_ERRORS[source] = f"{type(exc).__name__}: {exc}"
        SOURCE_TOOL_COUNTS[source] = 0
        SOURCE_TOOL_NAMES[source] = []
        logger.warning("%s MCP unavailable: %s", source, LAST_ERRORS[source])
        return []


def status_payload() -> dict[str, Any]:
    return {
        "status": "ok" if SOURCE_TOOL_COUNTS["admin"] > 0 and SOURCE_TOOL_COUNTS["intelligence"] > 0 else "degraded",
        "version": VERSION,
        "admin": {
            "available": SOURCE_TOOL_COUNTS["admin"] > 0,
            "tool_count": SOURCE_TOOL_COUNTS["admin"],
            "tools": SOURCE_TOOL_NAMES["admin"],
            "error": LAST_ERRORS["admin"],
            "endpoint": ADMIN_URL,
        },
        "intelligence": {
            "available": SOURCE_TOOL_COUNTS["intelligence"] > 0,
            "tool_count": SOURCE_TOOL_COUNTS["intelligence"],
            "tools": SOURCE_TOOL_NAMES["intelligence"],
            "error": LAST_ERRORS["intelligence"],
            "endpoint": INTELLIGENCE_URL,
        },
        "second_brain": brain_status(),
        "audit": audit_status(),
        "public_tool_count": len(TOOL_ROUTES),
    }


async def refresh_tools() -> list[types.Tool]:
    admin_tools = await _list_source("admin", ADMIN_URL, ADMIN_TOKEN)
    intelligence_tools = await _list_source("intelligence", INTELLIGENCE_URL, INTELLIGENCE_TOKEN)
    merged: list[types.Tool] = list(LOCAL_TOOL_SPECS)
    routes: dict[str, tuple[str, str]] = {name: ("local", name) for name in LOCAL_TOOL_NAMES}

    for source, tools in (("admin", admin_tools), ("intelligence", intelligence_tools)):
        for tool in tools:
            upstream_name = tool.name
            public_name = upstream_name
            if public_name in routes:
                public_name = f"{source}_{upstream_name}"
                tool = tool.model_copy(update={"name": public_name})
            routes[public_name] = (source, upstream_name)
            merged.append(tool)

    TOOL_ROUTES.clear()
    TOOL_ROUTES.update(routes)
    logger.info(
        "Unified MCP catalog refreshed: admin=%d intelligence=%d local=%d public=%d",
        SOURCE_TOOL_COUNTS["admin"], SOURCE_TOOL_COUNTS["intelligence"], len(LOCAL_TOOL_NAMES), len(TOOL_ROUTES),
    )
    return merged


async def on_list_tools(_ctx: Any, _params: types.PaginatedRequestParams | None) -> types.ListToolsResult:
    return types.ListToolsResult(tools=await refresh_tools())


def text_result(payload: Any, *, is_error: bool = False) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))],
        is_error=is_error,
    )


def safe_audit(**kwargs: Any) -> None:
    try:
        audit_add(**kwargs)
    except Exception:
        logger.exception("Failed to persist MCP audit event")


def local_call(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
    if name == "UnifiedStatus":
        return text_result(status_payload())
    if name == "McpAuditQuery":
        return text_result({
            "status": audit_status(),
            "entries": audit_query(
                source=arguments.get("source"),
                tool=arguments.get("tool"),
                kind=arguments.get("kind"),
                success=arguments.get("success"),
                since_minutes=arguments.get("since_minutes"),
                limit=arguments.get("limit", 100),
                include_arguments=arguments.get("include_arguments", True),
            ),
        })
    if name == "McpAuditStatus":
        return text_result(audit_status())
    if name == "SecondBrainSearch":
        rows = brain_search(
            arguments.get("query", ""),
            topic=arguments.get("topic"),
            confidence=arguments.get("confidence"),
            limit=arguments.get("limit", 20),
        )
        return text_result({"count": len(rows), "entries": rows})
    if name == "SecondBrainGet":
        row = brain_get(arguments["topic"], arguments["key"], arguments.get("include_history", False))
        return text_result({"found": row is not None, "entry": row})
    if name == "SecondBrainUpsert":
        return text_result(brain_upsert(
            topic=arguments["topic"],
            key=arguments["key"],
            title=arguments["title"],
            content=arguments["content"],
            tags=arguments.get("tags"),
            source=arguments.get("source", "chatgpt_mcp"),
            confidence=arguments.get("confidence", "verified"),
            metadata=arguments.get("metadata"),
        ))
    if name == "SecondBrainStatus":
        return text_result(brain_status())
    return text_result({"error": f"Unknown local tool: {name}"}, is_error=True)


async def on_call_tool(_ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult | types.InputRequiredResult:
    arguments = params.arguments or {}
    if params.name not in TOOL_ROUTES:
        await refresh_tools()
    route = TOOL_ROUTES.get(params.name)
    if route is None:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"Unknown tool: {params.name}")],
            is_error=True,
        )

    source, upstream_name = route
    started = time.monotonic()

    if source == "local":
        try:
            result = local_call(upstream_name, arguments)
            failed = bool(getattr(result, "is_error", False))
            duration_ms = int((time.monotonic() - started) * 1000)
            safe_audit(source="local", public_tool=params.name, upstream_tool=upstream_name,
                       arguments=arguments, success=not failed, duration_ms=duration_ms,
                       error_text="local tool returned error" if failed else None)
            logger.info("MCP_CALL source=local tool=%s status=%s duration_ms=%d", params.name, "error" if failed else "ok", duration_ms)
            return result
        except Exception as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            safe_audit(source="local", public_tool=params.name, upstream_tool=upstream_name,
                       arguments=arguments, success=False, duration_ms=duration_ms,
                       error_text=f"{type(exc).__name__}: {exc}")
            logger.exception("MCP_CALL source=local tool=%s status=error duration_ms=%d", params.name, duration_ms)
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=f"local MCP error: {exc}")], is_error=True
            )

    if source == "admin":
        url, token = ADMIN_URL, ADMIN_TOKEN
    elif source == "intelligence":
        url, token = INTELLIGENCE_URL, INTELLIGENCE_TOKEN
    else:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="Invalid tool route")], is_error=True
        )

    try:
        async with upstream(url, token) as client:
            result = await client.call_tool(upstream_name, arguments)
        failed = bool(getattr(result, "is_error", False))
        duration_ms = int((time.monotonic() - started) * 1000)
        safe_audit(source=source, public_tool=params.name, upstream_tool=upstream_name,
                   arguments=arguments, success=not failed, duration_ms=duration_ms,
                   error_text="upstream tool returned error" if failed else None)
        logger.info("MCP_CALL source=%s tool=%s upstream=%s status=%s duration_ms=%d",
                    source, params.name, upstream_name, "error" if failed else "ok", duration_ms)
        return result
    except Exception as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        logger.exception("MCP_CALL source=%s tool=%s upstream=%s status=error duration_ms=%d",
                         source, params.name, upstream_name, duration_ms)
        LAST_ERRORS[source] = f"{type(exc).__name__}: {exc}"
        safe_audit(source=source, public_tool=params.name, upstream_tool=upstream_name,
                   arguments=arguments, success=False, duration_ms=duration_ms,
                   error_text=LAST_ERRORS[source])
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"{source} MCP error: {exc}")],
            is_error=True,
        )


server = Server(
    "ChatGPT Home Assistant Admin + Intelligence",
    version=VERSION,
    instructions=(
        "Unified Home Assistant administration and intelligence MCP. "
        "Inspect current state/config before writes, prefer minimal changes, validate configuration, "
        "and use network tools only for the private Home Assistant environment. "
        "For continued or previously analysed work, search SecondBrainSearch early. "
        "After a durable technical finding, workaround, protocol mapping or architectural decision is verified, "
        "persist it with SecondBrainUpsert using a stable topic/key and an explicit confidence level. "
        "Never store passwords, API keys, tokens or other secrets in Second Brain. "
        "Use McpAuditQuery to inspect which ChatGPT commands were executed through this MCP."
    ),
    on_list_tools=on_list_tools,
    on_call_tool=on_call_tool,
)


async def health(_request: Request) -> JSONResponse:
    payload = status_payload()
    payload["process_status"] = "ready"
    return JSONResponse(payload)


security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"],
    allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
)

app = server.streamable_http_app(
    streamable_http_path="/mcp",
    json_response=False,
    stateless_http=False,
    transport_security=security,
    host=HOST,
    custom_starlette_routes=[Route("/health", health, methods=["GET"])],
)


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT, log_level=LOG_LEVEL.lower())
