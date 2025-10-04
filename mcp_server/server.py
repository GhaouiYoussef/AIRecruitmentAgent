"""Minimal MCP server exposing `linkedin_search_tool` using the core `mcp` library.

Transport: stdio (spawnable process). Configure your MCP client to execute:
    python mcp_server/server.py

Implements the required list_tools & call_tool handlers manually.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, CallToolResult, TextContent

# Ensure repository root on sys.path so we can import project modules
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ollama_recruiter.tools import linkedin_search_tool  # noqa: E402


server = Server("recruiter_tools")

SEARCH_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "Search query (keywords for candidate search)."},
        "num_candidates": {"type": "integer", "minimum": 1, "default": 5},
        "test_mode_extract": {"type": "boolean", "default": False},
        "test_mode_score": {"type": "boolean", "default": False},
    },
    "required": ["query"],
    "additionalProperties": False,
}


@server.list_tools()
async def list_tools() -> List[Tool]:  # type: ignore[override]
    return [
        Tool(
            name="search_candidates",
            description="Search and optionally score candidates for a job description (see README).",
            inputSchema=SEARCH_SCHEMA,
        )
    ]


def _invoke_search(arguments: Dict[str, Any]):
    return linkedin_search_tool(
        arguments["query"],
        arguments.get("num_candidates", 5),
        arguments.get("test_mode_extract", False),
        arguments.get("test_mode_score", False),
    )


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> CallToolResult:  # type: ignore[override]
    if name != "search_candidates":
        return CallToolResult(content=[TextContent(type="text", text=f"Unknown tool: {name}")])
    if "query" not in arguments:
        return CallToolResult(content=[TextContent(type="text", text="Missing required field 'query'")])
    result = await asyncio.to_thread(_invoke_search, arguments)
    try:
        rendered = json.dumps(result, ensure_ascii=False, indent=2)
    except TypeError:
        rendered = str(result)
    return CallToolResult(content=[TextContent(type="text", text=rendered)])


async def amain() -> None:
    default_n = os.getenv("MCP_DEFAULT_NUM_CANDIDATES")
    if default_n:
        print(f"[mcp_server] (info) Default candidate override env detected: {default_n}")
    async with stdio_server() as (read, write):
        # Provide empty initialization options object per current API signature.
        await server.run(read, write, {})


if __name__ == "__main__":  # pragma: no cover
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:  # pragma: no cover
        pass
