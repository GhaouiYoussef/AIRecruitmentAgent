# oracle_agent.py
from __future__ import annotations
import os
import json
import time
import random
from typing import List, Dict, Any, Union, TypedDict
from pydantic import BaseModel
import ollama  # ensure ollama python package is installed
from semantic_router.utils.function_call import FunctionSchema  # ensure package available

# -------------------------
# Simple data models
# -------------------------
class Rec(BaseModel):
    top_candidates_liks: List[str]

    def __str__(self) -> str:
        candidates_str = "\n".join(self.top_candidates_liks)
        return f"Top Candidates Links:\n{candidates_str}"

class AgentAction(BaseModel):
    tool_name: str
    tool_input: Dict[str, Any]
    tool_output: Union[str, None] = None

    @classmethod
    def from_ollama(cls, ollama_response: dict) -> "AgentAction":
        """
        Safely parse the ollama response which we expect to be a JSON string
        in `ollama_response["message"]["content"]`.
        """
        try:
            content = ollama_response["message"]["content"]
            parsed = json.loads(content)
            return cls(tool_name=parsed["name"], tool_input=parsed.get("parameters", {}))
        except Exception as e:
            # Helpful debug information if parsing fails
            raise RuntimeError(f"Failed to parse ollama response: {e}\nResponse: {ollama_response}")

# -------------------------
# Tool: linkedin_search_tool (calls local FastAPI service)
# -------------------------
def linkedin_search_tool(query: str, num_candidates: int = 5) -> List[str]:
    """
    Calls a local LinkedIn search service (FastAPI) and returns list of profile URLs.
    Falls back to a static list if the service or requests is unavailable.
    """
    try:
        import requests
    except Exception:
        return [
            "https://www.linkedin.com/in/saber-chadded-36552b192/",
            "https://www.linkedin.com/in/guesmi-wejden-5269222aa/",
            "https://www.linkedin.com/in/hichem-dridi/",
            "https://www.linkedin.com/in/nour-hamdi/",
            "https://www.linkedin.com/in/iyadh-chaouch-072077225/",
        ]

    service_url = os.getenv("LINKEDIN_SEARCH_URL", "http://127.0.0.1:8000/search")
    try:
        resp = requests.get(service_url, params={"query": query, "num_candidates": int(num_candidates)}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        links = None
        if isinstance(data, dict):
            links = data.get("links") or data.get("results") or data.get("candidates")
        if not links or not isinstance(links, list):
            raise ValueError(f"unexpected response shape: {data}")
        return links
    except Exception as e:
        print(f"[linkedin_search_tool] remote call failed ({e}); returning fallback links")
        return [
            "https://www.linkedin.com/in/saber-chadded-36552b192/",
            "https://www.linkedin.com/in/guesmi-wejden-5269222aa/",
            "https://www.linkedin.com/in/hichem-dridi/",
            "https://www.linkedin.com/in/nour-hamdi/",
            "https://www.linkedin.com/in/iyadh-chaouch-072077225/",
        ]

# -------------------------
# AgentState typing
# -------------------------
class AgentState(TypedDict):
    input: str
    chat_history: List[Dict[str, Any]]  # list of messages {"role":..., "content":...}
    intermediate_steps: List[AgentAction]
    output: Dict[str, Any]

# -------------------------
# System prompt and schema
# -------------------------
system_prompt = """You are the Oracle: a specialized recruiter agent and decision-maker.
Given the user's hiring request, decide how to proceed using the available tools.
(see earlier conversation for full prompt)"""

# Build function schema for ollama function-calling style (depends on semantic_router)
search_schema = FunctionSchema(linkedin_search_tool).to_ollama()
# adjust description/key if necessary
if "function" in search_schema and "parameters" in search_schema["function"]:
    if "query" in search_schema["function"]["parameters"]["properties"]:
        search_schema["function"]["parameters"]["properties"]["query"]["description"] = None

# -------------------------
# Helpers for messages / scratchpad
# -------------------------
def get_system_tools_prompt(system_prompt: str, tools: List[dict]) -> str:
    tools_str = "\n".join([json.dumps(t) for t in tools])
    return f"{system_prompt}\n\nYou may use the following tools:\n{tools_str}"

def action_to_message(action: AgentAction) -> List[Dict[str, str]]:
    assistant_content = json.dumps({"name": action.tool_name, "parameters": action.tool_input})
    assistant_message = {"role": "assistant", "content": assistant_content}
    user_message = {"role": "user", "content": action.tool_output or ""}
    return [assistant_message, user_message]

def create_scratchpad(intermediate_steps: List[AgentAction]) -> List[Dict[str, str]]:
    steps_with_output = [a for a in intermediate_steps if a.tool_output is not None]
    scratch = []
    for a in steps_with_output:
        scratch.extend(action_to_message(a))
    return scratch

# -------------------------
# LLM call (ollama)
# -------------------------
def call_llm(user_input: str, chat_history: List[Dict[str, Any]], intermediate_steps: List[AgentAction]) -> AgentAction:
    scratchpad = create_scratchpad(intermediate_steps)
    tools = [search_schema]  # you can change available tools dynamically if needed

    messages = [
        {"role": "system", "content": get_system_tools_prompt(system_prompt, tools)},
        *chat_history,
        {"role": "user", "content": user_input},
        *scratchpad,
    ]

    # Call ollama: ensure the model name exists locally
    res = ollama.chat(
        model=os.getenv("OLLAMA_MODEL", "llama3-groq-tool-use:8b"),
        messages=messages,
        format="json",
    )

    return AgentAction.from_ollama(res)

# -------------------------
# Graph-run helper / tool runner
# -------------------------
# mapping of tool-name -> python callable
tool_str_to_func = {
    search_schema["function"]["name"]: linkedin_search_tool
}

def run_tool(state: AgentState) -> Dict[str, Any]:
    """
    Runs the tool indicated by the last AgentAction in state['intermediate_steps'] and
    returns either {'intermediate_steps': [AgentAction(...)]} or {'output': ...}
    """
    if not state["intermediate_steps"]:
        raise RuntimeError("run_tool called but no intermediate_steps are present")

    last_action = state["intermediate_steps"][-1]
    tool_name = last_action.tool_name
    tool_args = last_action.tool_input

    if tool_name not in tool_str_to_func:
        raise RuntimeError(f"Unknown tool requested: {tool_name}")

    print(f"[run_tool] invoking {tool_name} with {tool_args}")
    try:
        out = tool_str_to_func[tool_name](**tool_args)
    except Exception as e:
        out = f"[tool_error] {e}"

    action_out = AgentAction(tool_name=tool_name, tool_input=tool_args, tool_output=str(out))

    # If you later implement a final_answer tool, return {'output': ...} there
    return {"intermediate_steps": [action_out]}

# -------------------------
# Optional: quick local test (only run when module executed directly)
# -------------------------
if __name__ == "__main__":
    # quick smoke test - do not call in production
    print("oracle_agent module quick test")
    try:
        sample = call_llm(
            user_input="Find a backend ML engineer in Tunis",
            chat_history=[],
            intermediate_steps=[]
        )
        print("LLM action:", sample)
    except Exception as e:
        print("Quick test failed (expected if Ollama model not present):", e)
