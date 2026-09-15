from __future__ import annotations

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

VERSION = "2.1.0"
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


@asynccontextmanager
async def upstream(url: str, token: str):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx2.AsyncClient(headers=headers, timeout=300.0) as http_client:
        transport = streamable_http_client(url, http_client=http_client)
        async with Client(transport, cache=None) as client:
            yield client


async def _list_source(source: str, url: str, token: str) -> list[types.Tool]:
    try:
        async with upstream(url, token) as client:
            result = await client.list_tools()
        LAST_ERRORS[source] = None
        return list(result.tools)
    except Exception as exc:
        LAST_ERRORS[source] = str(exc)
        logger.warning("%s MCP unavailable: %s", source, exc)
        return []


async def refresh_tools() -> list[types.Tool]:
    admin_tools = await _list_source("admin", ADMIN_URL, ADMIN_TOKEN)
    intelligence_tools = await _list_source("intelligence", INTELLIGENCE_URL, INTELLIGENCE_TOKEN)

    merged: list[types.Tool] = []
    routes: dict[str, tuple[str, str]] = {}

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
    else:
        url, token = INTELLIGENCE_URL, INTELLIGENCE_TOKEN

    try:
        async with upstream(url, token) as client:
            return await client.call_tool(upstream_name, params.arguments or {})
    except Exception as exc:
        logger.exception("Tool forwarding failed: %s", params.name)
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"{source} MCP error: {exc}")],
            is_error=True,
        )


server = Server(
    "ChatGPT Home Assistant Admin + Intelligence",
    version=VERSION,
    instructions=(
        "Unified Home Assistant administration and intelligence MCP. "
        "Inspect current state before writes, prefer minimal changes, validate configuration, "
        "and use the network tools only for the private Home Assistant environment."
    ),
    on_list_tools=on_list_tools,
    on_call_tool=on_call_tool,
)


async def health(_request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "version": VERSION,
            "admin_error": LAST_ERRORS["admin"],
            "intelligence_error": LAST_ERRORS["intelligence"],
            "tool_count": len(TOOL_ROUTES),
        }
    )


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
