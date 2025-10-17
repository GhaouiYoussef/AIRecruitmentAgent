"""Custom MCP client that uses the local OracleRuntime agent instead of the generic MCPAgent.

Two modes (controlled via env USE_MCP_AGENT=1):
  - Default (USE_MCP_AGENT unset or 0): Use OracleRuntime with the local python tool `linkedin_search_tool`.
  - MCP mode (USE_MCP_AGENT=1): Fall back to original MCPAgent wiring (still available for comparison).

This lets you iterate on your bespoke agent reasoning loop while optionally
still leveraging MCP if desired.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import List, Dict, Any
from langchain_ollama.chat_models import ChatOllama
from mcp_use import MCPAgent, MCPClient

# Ensure repo root in path so we can import the recruiter package
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from ollama_recruiter.agent_runtime import OracleRuntime  # type: ignore


# ---------------------------------------------------------------------------
# Shared config / server definition (points at new unified server if present)
# ---------------------------------------------------------------------------
server_script = os.path.join(_REPO_ROOT, "self_mcp_server", "mcp_server_separate.py")
if not os.path.exists(server_script):  # fallback
    server_script = os.path.join(_REPO_ROOT, "self_mcp_server", "mcp_server.py")

CONFIG: Dict[str, Any] = {
    "mcpServers": {
        "ai-recruitment-suite": {
            "command": sys.executable,
            "args": [server_script]
        }
    }
}


# ---------------------------------------------------------------------------
# OracleRuntime (local) execution path
# ---------------------------------------------------------------------------
def run_oracle_runtime(prompt: str):
    runtime = OracleRuntime()
    history: List[dict] = []
    resp = runtime.invoke(prompt, history)
    print("Assistant:", resp["assistant"])  # textual answer
    if resp.get("actions"):
        print("\nExecuted actions:")
        for a in resp["actions"]:
            print(" -", a)
    if resp.get("tool_outputs"):
        print("\nTool outputs (truncated):")
        for out in resp["tool_outputs"]:
            print(" •", (out[:140] + "...") if len(out) > 160 else out)


# ---------------------------------------------------------------------------
# MCPAgent interactive chat (default)
# ---------------------------------------------------------------------------
async def chat_mcp_agent() -> None:
    client = MCPClient.from_dict(CONFIG)
    model = os.getenv("OLLAMA_MODEL", "granite4:micro")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    llm = ChatOllama(model=model, base_url=base_url)
    agent = MCPAgent(llm=llm, client=client, max_steps=int(os.getenv("MAX_STEPS", "12")))

    print("MCP chat ready. Type 'exit' to quit.\n")
    try:
        while True:
            try:
                user = await asyncio.get_event_loop().run_in_executor(None, lambda: input("You: ").strip())
            except (EOFError, KeyboardInterrupt):
                break
            if not user:
                continue
            if user.lower() in {"exit", "quit", ":q", ":wq"}:
                break
            try:
                answer = await agent.run(user)
            except Exception as e:
                print(f"Error: {e}")
                continue
            print(f"Assistant: {answer}\n")
    finally:
        await client.close_all_sessions()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    # Default to MCP chat mode; allow fallback to local OracleRuntime
    use_local = os.getenv("USE_LOCAL_AGENT", "0").lower() in {"1", "true", "yes", "y"}
    if use_local:
        print("[Local OracleRuntime mode] Set USE_LOCAL_AGENT=0 to chat via MCP tools.")
        default_prompt = (
            "Find 2 Python backend candidates and show their links (test mode). "
            "Then summarize why they might fit."
        )
        prompt = os.getenv("PROMPT", default_prompt)
        run_oracle_runtime(prompt)
    else:
        asyncio.run(chat_mcp_agent())


if __name__ == "__main__":
    main()