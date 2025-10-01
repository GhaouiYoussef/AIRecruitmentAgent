from typing import List, Union, TypedDict
import json

from pydantic import BaseModel
import ollama

# Reuse the linkedin tool and system prompt from the original file
# To avoid circular imports, we embed minimal copies here. If you prefer single-source, we can refactor later.

class Rec(BaseModel):
    top_candidates_liks: list[str]

    def __str__(self):
        candidates_str = "\n".join(self.top_candidates_liks)
        return f"Top Candidates Links:\n{candidates_str}"


def linkedin_search_tool(query: str, num_candidates: int = 5):
    import os
    try:
        import requests
    except Exception as e:
        print(f"linkedin_search_tool: requests not available: {e}; returning fallback links")
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
        print(f"linkedin_search_tool: remote call failed ({e}); returning fallback links")
        return [
            "https://www.linkedin.com/in/saber-chadded-36552b192/",
            "https://www.linkedin.com/in/guesmi-wejden-5269222aa/",
            "https://www.linkedin.com/in/hichem-dridi/",
            "https://www.linkedin.com/in/nour-hamdi/",
            "https://www.linkedin.com/in/iyadh-chaouch-072077225/",
        ]


system_prompt = """You are the Oracle: a specialized recruiter agent and decision-maker.
Given the user's hiring request, decide how to proceed using the available tools.

Objective:
- Identify and recommend the best candidate(s) for the role.
- For each recommended candidate include: name/title, key skills, years of experience, location (if known), a concise rationale for fit, contact details if available, and suggested next steps for outreach/interview.

Tool-calling rules:
- When using a tool, output ONLY one JSON object and NOTHING else, exactly matching this pattern:
{
    "name": "<tool_name>",
    "parameters": {"<param_key>": <param_value>}
}
- Use at most one tool per turn.
- You may call the search tool (linkedin_search_tool) up to 3 times total.
- After any use of the search tool, you MUST call the final_answer tool to produce the human-facing summary and recommendations.
- If the user asks something unrelated to recruiting/hiring or requests a direct answer, call final_answer directly.

Behavior & response style:
- Prioritize concise, evidence-based recommendations derived from tool outputs.
- If results are insufficient or ambiguous, ask a focused clarifying question (do not call a tool) before searching further.
- Always include practical next steps (e.g., outreach template, suggested interview questions, priority ranking).
- Do not include any explanatory or narrative text when issuing a tool call — only emit the required JSON.

Available tools:
- linkedin_search_tool: searches LinkedIn for candidate profiles.
    Parameters: {"query": "<role or skill>", "num_candidates": <int>}

Follow these rules strictly to ensure consistent, parseable tool usage and clear recruiter-oriented recommendations."""


def get_system_tools_prompt(system_prompt: str, tools: list[dict]):
    tools_str = "\n".join([str(tool) for tool in tools])
    return f"{system_prompt}\n\nYou may use the following tools:\n{tools_str}"


class AgentAction(BaseModel):
    tool_name: str
    tool_input: dict
    tool_output: str | None = None

    @classmethod
    def from_ollama(cls, ollama_response: dict):
        try:
            output = json.loads(ollama_response["message"]["content"])
            return cls(
                tool_name=output["name"],
                tool_input=output["parameters"],
            )
        except Exception as e:
            print(f"Error parsing ollama response:\n{ollama_response}\n")
            raise e


def action_to_message(action: AgentAction):
    assistant_content = json.dumps({"name": action.tool_name, "parameters": action.tool_input})
    assistant_message = {"role": "assistant", "content": assistant_content}
    user_message = {"role": "user", "content": action.tool_output}
    return [assistant_message, user_message]


def create_scratchpad(intermediate_steps: list[AgentAction]):
    intermediate_steps = [a for a in intermediate_steps if a.tool_output is not None]
    scratch = []
    for a in intermediate_steps:
        scratch.extend(action_to_message(a))
    return scratch


class AgentState(TypedDict):
    input: str
    chat_history: list[dict]
    intermediate_steps: list[AgentAction]
    output: dict[str, Union[str, List[str]]]


def call_llm(user_input: str, chat_history: list[dict], intermediate_steps: list[AgentAction], tools: list[dict]) -> AgentAction:
    scratchpad = create_scratchpad(intermediate_steps)
    messages = [
        {"role": "system", "content": get_system_tools_prompt(system_prompt, tools)},
        *chat_history,
        {"role": "user", "content": user_input},
        *scratchpad,
    ]
    res = ollama.chat(
        model="llama3-groq-tool-use:8b",
        messages=messages,
        format="json",
    )
    return AgentAction.from_ollama(res)


def final_answer(answer: str) -> str:
    return answer


tool_str_to_func = {}


class OracleRuntime:
    def __init__(self):
        from semantic_router.utils.function_call import FunctionSchema
        search_schema = FunctionSchema(linkedin_search_tool).to_ollama()
        # SR workaround
        search_schema["function"]["parameters"]["properties"]["query"]["description"] = None
        final_schema = FunctionSchema(final_answer).to_ollama()

        self.schemas = [search_schema, final_schema]
        self.search_tool_name = search_schema["function"]["name"]
        self.final_tool_name = final_schema["function"]["name"]

        global tool_str_to_func
        tool_str_to_func[self.search_tool_name] = linkedin_search_tool
        tool_str_to_func[self.final_tool_name] = final_answer

    def _execute_action(self, action: AgentAction) -> AgentAction:
        fn = tool_str_to_func.get(action.tool_name)
        out = None
        if fn:
            out = fn(**action.tool_input)
        return AgentAction(tool_name=action.tool_name, tool_input=action.tool_input, tool_output=str(out) if out is not None else None)

    def invoke(self, user_input: str, history: list[dict]):
        # First turn: pick a tool and possibly execute
        action1 = call_llm(user_input, history, [], self.schemas)
        executed1 = self._execute_action(action1)

        actions = [
            {"name": executed1.tool_name, "parameters": executed1.tool_input}
        ]
        tool_outputs: List[str] = []
        if executed1.tool_output:
            tool_outputs.append(executed1.tool_output)

        assistant_text = None

        # If the first action was a search, immediately follow up with a final_answer using the scratchpad
        if executed1.tool_name == self.search_tool_name:
            action2 = call_llm(
                "Please produce the final recruiter recommendation based on the latest search results.",
                history,
                [executed1],
                self.schemas,
            )
            executed2 = self._execute_action(action2)
            actions.append({"name": executed2.tool_name, "parameters": executed2.tool_input})
            if executed2.tool_name == self.final_tool_name:
                assistant_text = executed2.tool_input.get("answer") if isinstance(executed2.tool_input, dict) else str(executed2.tool_input)
                # If the tool returned its own output, prefer it
                if executed2.tool_output and executed2.tool_output != "None":
                    assistant_text = executed2.tool_output
            elif executed2.tool_output:
                tool_outputs.append(executed2.tool_output)

        # Fallback assistant text if none
        if not assistant_text:
            assistant_text = "I've processed your request. Let me know if you'd like me to search or refine the results."

        return {
            "assistant": assistant_text,
            "actions": actions,
            "tool_outputs": tool_outputs,
        }
