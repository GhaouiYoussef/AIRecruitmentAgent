import asyncio
import os
from langchain_ollama.chat_models import ChatOllama
from mcp_use import MCPAgent, MCPClient
import sys
# Get the server script path (same directory as this file)
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, os.pardir))
server_path = os.path.join(_REPO_ROOT, "self_mcp_server", "mcp_server.py")

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# print server path for debugging
logger.info(f"Using MCP server script at: {server_path}")


# Describe which MCP servers you want.
CONFIG = {
    "mcpServers": {
        "fii-demo": {
            # Use the exact same Python interpreter as this client
            "command": sys.executable,
            "args": [server_path]
        }
    }
}

async def main():
    client = MCPClient.from_dict(CONFIG)
    llm = ChatOllama(model="granite4:micro", base_url="http://localhost:11434")
    
    # Wire the LLM to the client
    agent = MCPAgent(llm=llm, client=client, max_steps=20)

    # Give prompt to the agent
    result = await agent.run("Compute md5 hash for following string: 'Hello, world!' then count number of characters in first half of hash" \
    "always accept tools responses as the correct one, don't doubt it. Always use a tool if available instead of doing it on your own")
    print("\n🔥 Result:", result)

    # Always clean up running MCP sessions
    await client.close_all_sessions()

if __name__ == "__main__":
    asyncio.run(main())