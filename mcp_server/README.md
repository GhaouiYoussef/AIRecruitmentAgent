# MCP Server for Recruiter Tool

This folder contains a minimal **Model Context Protocol (MCP)** server that exposes the existing `linkedin_search_tool` (defined in `ollama_recruiter/tools.py`) as an MCP tool so any MCP‑compliant client (e.g. Claude Desktop, LangGraph Platform, `langchain-mcp-adapters`, etc.) can call it.

## Features
* Single tool: `search_candidates` (wraps `linkedin_search_tool`).
* Supports parameters: `query`, `num_candidates`, `test_mode_extract`, `test_mode_score`.
* Returns either a mapping of candidate id/link to score (when scoring succeeds) or a list of profile links (fallback path), mirroring the original function behavior.
* Async wrapper using `asyncio.to_thread` so the underlying synchronous logic doesn't block the event loop.

## Directory Layout
```
mcp_server/
  server.py              # MCP server entrypoint
  requirements_mcp.txt   # Minimal dependency list for the MCP server
  README.md              # This file
```

## 1. Create & Activate Local Virtual Environment (mcp_venv)
From repository root (Windows PowerShell):
```powershell
python -m venv mcp_venv
./mcp_venv/Scripts/Activate.ps1
```

Upgrade pip (optional but recommended):
```powershell
python -m pip install --upgrade pip
```

## 2. Install Dependencies
```powershell
pip install -r mcp_server/requirements_mcp.txt -r "Full system/requirements_server.txt" -r ollama_recruiter/requirements_agent.txt
```
If some of those requirement files contain overlapping packages, pip will resolve the final versions (you can later consolidate into one lock file if desired).

## 3. Run the MCP Server (stdio mode)
The simplest transport for local experimentation is stdio. Many MCP clients can spawn a process and communicate over stdio automatically.

Manual run:
```powershell
python mcp_server/server.py
```
You will see no traditional HTTP logs because the server speaks MCP over stdio. To integrate with a client you normally configure the client with the command used above.

## 4. Example: Using `langchain-mcp-adapters` Client (Python)
```python
import asyncio
from mcp import ClientSession
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.tools import load_mcp_tools

async def main():
    # Launch the local server as a subprocess over stdio
    async with stdio_client(command=["python", "mcp_server/server.py"]) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_mcp_tools(session)
            # There will be one tool: search_candidates
            tool = [t for t in tools if t.name == "search_candidates"][0]
            result = await tool.ainvoke({"query": "python backend", "num_candidates": 3})
            print(result)

asyncio.run(main())
```

## 5. Claude Desktop / Other MCP Clients
Add a configuration entry pointing to the command:
```
python c:/path/to/repo/mcp_server/server.py
```
No extra env vars are required unless you want to override the default service URLs used by the underlying tool (`LINKEDIN_SEARCH_URL`, `LINKEDIN_EXTRACT_URL`, `CANDIDATE_SCORER_URL`, `CLEANUP_AND_ARCHIVE`).

## 6. Environment Variables (Optional)
Set before launching the server:
```powershell
$env:LINKEDIN_SEARCH_URL = "http://127.0.0.1:8000/search"
$env:LINKEDIN_EXTRACT_URL = "http://127.0.0.1:8000/extract"
$env:CANDIDATE_SCORER_URL = "http://localhost:8001/scorer_tool"
$env:CLEANUP_AND_ARCHIVE = "0"   # or 1 to enable archive + cleanup
```

## 7. Development Notes
* The server is intentionally minimal and does not implement resource listing or prompts; only a single tool is exposed.
* If you later wrap multiple functions, add additional `@mcp.tool()` definitions in `server.py`.
* For HTTP transport instead of stdio you could adopt a small ASGI wrapper (not included here to keep scope tight).

## 8. Troubleshooting
| Issue | Cause | Fix |
|-------|-------|-----|
| Client reports no tools | Server not initialized or path wrong | Verify command path & that `server.py` runs without import errors |
| Tool hangs | Underlying sync network call blocking | Ensure services at configured URLs are reachable; add timeouts (already present) |
| JSON serialization error | Non-serializable return | Wrapper converts result directly (current return types are dict/list of strings) |

## 9. Next Steps / Enhancements
* Add structured Pydantic schema to normalize output shape.
* Provide additional tools (e.g., separate search-only, score-only variants) for finer LLM control.
* Add logging & observability (OpenTelemetry) if deploying beyond local dev.

---
Feel free to request enhancements and we can iterate.
