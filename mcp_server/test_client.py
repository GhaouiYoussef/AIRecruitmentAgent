"""Simple async test client for the local MCP server.

Run (from repo root, with mcp_venv activated):
    python mcp_server/test_client.py

It will spawn the stdio MCP server process (server.py), list tools, invoke
the `search_candidates` tool with a sample query, and print the result.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters


async def main() -> None:
    if not shutil.which("python"):
        raise SystemExit("Python executable not found in PATH")

    # Launch MCP server as subprocess over stdio
    params = StdioServerParameters(command="python", args=["mcp_server/server.py"])
    async with stdio_client(server=params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Obtain the available tools
            tools = await session.list_tools()
            print("Tools exposed by server:")
            for t in tools.tools:
                print(f" - {t.name}: {t.description}")

            # Find search tool
            search = next((t for t in tools.tools if t.name == "search_candidates"), None)
            if not search:
                raise RuntimeError("search_candidates tool not found")

            # Prepare arguments; use test_mode_score True to avoid scoring network call
            args: dict[str, Any] = {
                "query": "python backend",
                "num_candidates": 3,
                "test_mode_score": True,
            }
            print("\nInvoking search_candidates with args:", args)
            call_result = await session.call_tool(name=search.name, arguments=args)

            # call_result.content is a list of Content objects; we expect TextContent
            for c in call_result.content:
                if hasattr(c, "text"):
                    text = getattr(c, "text")
                    try:
                        data = json.loads(text)
                        print("\nParsed JSON result:")
                        print(json.dumps(data, indent=2, ensure_ascii=False))
                    except Exception:
                        print("\nRaw text result:")
                        print(text)


if __name__ == "__main__":  # pragma: no cover
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass