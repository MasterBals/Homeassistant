from __future__ import annotations

import json
import logging
import os
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

VERSION = "2.1.4"
HOST = os.environ.get("UNIFIED_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("UNIFIED_MCP_PORT", "8765"))
INTELLIGENCE_URL = os.environ.get("INTELLIGENCE_MCP_URL", "http://127.0.0.1:18765/mcp")
INTELLIGENCE_TOKEN = os.environ.get("INTELLIGENCE_MCP_TOKEN", "")
ADMIN_URL = os.environ.get("HA_ADMIN_MCP_URL", "http://supervisor/core/api/mcp/chatgpt_ha_admin")
ADMIN_TOKEN = os.environ.get("HA_ADMIN_MCP_TOKEN", "")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
LOCAL_STATUS_TOOL = "UnifiedStatus"

logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("ha-unified-mcp")

TOOL_ROUTES: dict[str, tuple[str, str]] = {}
LAST_ERRORS: dict[str, str | None] = {"admin": None, "intelligence": None}
SOURCE_TOOL_COUNTS: dict[str, int] = {"admin": 0, "intelligence": 0}
SOURCE_TOOL_NAMES: dict[str, list[str]] = {"admin": [], "intelligence": []}


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
        "public_tool_count": len(TOOL_ROUTES),
    }


async def refresh_tools() -> list[types.Tool]:
    admin_tools = await _list_source("admin", ADMIN_URL, ADMIN_TOKEN)
    intelligence_tools = await _list_source("intelligence", INTELLIGENCE_URL, INTELLIGENCE_TOKEN)

    merged: list[types.Tool] = [
        types.Tool(
            name=LOCAL_STATUS_TOOL,
            description="Diagnose the unified Home Assistant MCP and show Admin/Intelligence tool availability and upstream errors.",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        )
    ]
    routes: dict[str, tuple[str, str]] = {LOCAL_STATUS_TOOL: ("local", LOCAL_STATUS_TOOL)}

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
        "Unified MCP catalog refreshed: admin=%d intelligence=%d public=%d",
        SOURCE_TOOL_COUNTS["admin"],
        SOURCE_TOOL_COUNTS["intelligence"],
        len(TOOL_ROUTES),
    )
    return merged


async def on_list_tools(
    _ctx: Any,
    _params: types.PaginatedRequestParams | None,
) -> types.ListToolsResult:
    return types.ListToolsResult(tools=await refresh_tools())


async def on_call_tool(
    _ctx: Any,
    params: types.CallToolRequestParams,
) -> types.CallToolResult | types.InputRequiredResult:
    if params.name == LOCAL_STATUS_TOOL:
        await refresh_tools()
        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text=json.dumps(status_payload(), ensure_ascii=False, indent=2),
                )
            ],
            is_error=False,
        )

    if params.name not in TOOL_ROUTES:
        await refresh_tools()
    route = TOOL_ROUTES.get(params.name)
    if route is None:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"Unknown tool: {params.name}")],
            is_error=True,
        )

    source, upstream_name = route
    if source == "admin":
        url, token = ADMIN_URL, ADMIN_TOKEN
    elif source == "intelligence":
        url, token = INTELLIGENCE_URL, INTELLIGENCE_TOKEN
    else:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="Invalid local tool route")],
            is_error=True,
        )

    try:
        async with upstream(url, token) as client:
            return await client.call_tool(upstream_name, params.arguments or {})
    except Exception as exc:
        logger.exception("Tool forwarding failed: %s", params.name)
        LAST_ERRORS[source] = f"{type(exc).__name__}: {exc}"
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
        "and use the network tools only for the private Home Assistant environment. "
        "Use UnifiedStatus whenever Admin or Intelligence tools appear to be missing."
    ),
    on_list_tools=on_list_tools,
    on_call_tool=on_call_tool,
)


async def health(_request: Request) -> JSONResponse:
    await refresh_tools()
    return JSONResponse(status_payload())


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
