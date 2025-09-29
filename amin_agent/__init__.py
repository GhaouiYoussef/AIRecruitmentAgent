"""amin_agent package: recruiter agent.

This package contains lightweight modules to keep responsibilities separated:
- graph.py: simple StateGraph fallback wrapper
- llm.py: LLM calling abstraction with local stub for ollama
- tools_adapter.py: imports/adapter for existing agents.tools
- actions.py: AgentAction + helpers
- main.py: orchestrates graph construction and running
- utils.py: small helpers
"""

__all__ = ["build_and_run"]
