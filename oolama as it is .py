from pydantic import BaseModel
from langgraph.graph import StateGraph, END
import ollama
import inspect
import typing
from typing import get_origin, get_args

from semantic_router.utils.function_call import FunctionSchema
from typing import TypedDict, Annotated, List, Union
from langchain_core.agents import AgentAction
from langchain_core.messages import BaseMessage
import operator

class Rec(BaseModel):
    top_candidates_liks: list[str]

    def __str__(self):
        """LLM-friendly string representation of the candidates scrapped."""
        candidates_str = '\n'.join(self.top_candidates_liks)
        return f"Top Candidates Links:\n{candidates_str}"


import random


def linkedin_search_tool(query: str, num_candidates: int = 5):
    """
    Perform a LinkedIn search by calling the local LinkedIn Search HTTP service
    (FastAPI) at LINKEDIN_SEARCH_URL (default http://127.0.0.1:8000/search).

    Behavior:
    - Attempts an HTTP GET to the service with query and num_candidates.
    - On success returns the list of profile links from the service response.
    - On any error falls back to the static sample links to keep the agent running.

    Requirements:
    - The FastAPI service must be running (uvicorn linkedin_api.server:app --reload --host 127.0.0.1 --port 8000)
    - requests package installed (pip install requests)
    - Optionally set env LINKEDIN_SEARCH_URL to change the endpoint.
    """
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
        # expect {"query": "...", "num_candidates": n, "links": [...], "count": n}
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

from typing import TypedDict, Annotated, List, Union
from langchain_core.agents import AgentAction
from langchain_core.messages import BaseMessage
import operator


class AgentState(TypedDict):
    input: str
    chat_history: list[BaseMessage]
    intermediate_steps: Annotated[list[tuple[AgentAction, str]], operator.add]
    output: dict[str, Union[str, List[str]]]

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

from semantic_router.utils.function_call import FunctionSchema

# create the function calling schema for ollama
search_schema = FunctionSchema(linkedin_search_tool).to_ollama()
# TODO deafult None value for description and fix required fields in SR
search_schema["function"]["parameters"]["properties"]["query"]["description"] = None
search_schema

import ollama

def get_system_tools_prompt(system_prompt: str, tools: list[dict]):
    tools_str = "\n".join([str(tool) for tool in tools])
    return (
        f"{system_prompt}\n\n"
        f"You may use the following tools:\n{tools_str}"
    )
import json
class AgentAction(BaseModel):
    tool_name: str
    tool_input: dict
    tool_output: str | None = None

    @classmethod
    def from_ollama(cls, ollama_response: dict):
        try:
            # parse the output
            output = json.loads(ollama_response["message"]["content"])
            return cls(
                tool_name=output["name"],
                tool_input=output["parameters"],
            )
        except Exception as e:
            print(f"Error parsing ollama response:\n{ollama_response}\n")
            raise e

    def __str__(self):
        text = f"Tool: {self.tool_name}\nInput: {self.tool_input}"
        if self.tool_output is not None:
            text += f"\nOutput: {self.tool_output}"
        return text


# action = AgentAction.from_ollama(res)

def action_to_message(action: AgentAction):
    # create assistant "input" message
    assistant_content = json.dumps({"name": action.tool_name, "parameters": action.tool_input})
    assistant_message = {"role": "assistant", "content": assistant_content}
    # create user "response" message
    user_message = {"role": "user", "content": action.tool_output}
    return [assistant_message, user_message]

def create_scratchpad(intermediate_steps: list[AgentAction]):
    # filter for actions that have a tool_output
    intermediate_steps = [action for action in intermediate_steps if action.tool_output is not None]
    # format the intermediate steps into a "assistant" input and "user" response list
    scratch_pad_messages = []
    for action in intermediate_steps:
        scratch_pad_messages.extend(action_to_message(action))
    return scratch_pad_messages

def call_llm(user_input: str, chat_history: list[dict], intermediate_steps: list[AgentAction]) -> AgentAction:
    # format the intermediate steps into a scratchpad
    scratchpad = create_scratchpad(intermediate_steps)
    # if the scratchpad is not empty, we add a small reminder message to the agent
    if scratchpad:
        scratchpad += [{
            "role": "user",
            "content": (
                f"Please continue, as a reminder my query was '{user_input}'. "
                "Only answer to the original query, and nothing else — but use the "
                "information I provided to you to do so. Provide as much "
                "information as possible in the `answer` field of the "
                "final_answer tool and remember to leave the contact details "
                "of a promising looking candidate."
            )
        }]
        # we determine the list of tools available to the agent based on whether
        # or not we have already used the search tool
        tools_used = [action.tool_name for action in intermediate_steps]
        tools = []
        # if "search" in tools_used:
        #     # we do this because the LLM has a tendency to go off the rails
        #     # and keep searching for the same thing
        #     tools = [final_answer_schema]
        #     scratchpad[-1]["content"] = " You must now use the final_answer tool."
        # else:
        # this shouldn't happen, but we include it just in case
        tools = [search_schema]
    else:
        # this would indiciate we are on the first run, in which case we
        # allow all tools to be used
        tools = [search_schema]
    # construct our list of messages
    messages = [
        {"role": "system", "content": get_system_tools_prompt(
            system_prompt=system_prompt,
            tools=tools
        )},
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

# let's fake some chat history and test
out = call_llm(
    chat_history=[
        {"role": "user", "content": "hi im looking for a ml engineer"},
        {"role": "assistant", "content": "okey great, can you tell me more about the role?"},
        {"role": "user", "content": "the role is for a backend python  with experience in machine learning"},
        {"role": "assistant", "content": "Okay, I will start looking for candidates."},
    ],
    user_input="okey perfect, please go ahead",
    intermediate_steps=[]
)

def run_oracle(state: AgentState):
    print("run_oracle")
    chat_history = state["chat_history"]
    out = call_llm(
        user_input=state["input"],
        chat_history=chat_history,
        intermediate_steps=state["intermediate_steps"]
    )
    return {
        "intermediate_steps": [out]
    }

def router(state: AgentState):
    print("router")
    # return the tool name to use
    if isinstance(state["intermediate_steps"], list):
        return state["intermediate_steps"][-1].tool_name
    return '__end__'



# we use this to map tool names to tool functions
# map the function-schema name to the actual python function so names stay consistent
tool_str_to_func = {
    search_schema["function"]["name"]: linkedin_search_tool
}

def run_tool(state: AgentState):
    # use this as helper function so we repeat less code
    tool_name = state["intermediate_steps"][-1].tool_name
    tool_args = state["intermediate_steps"][-1].tool_input
    print(f"run_tool | {tool_name}.invoke(input={tool_args})")
    # run tool
    out = tool_str_to_func[tool_name](**tool_args)
    action_out = AgentAction(
        tool_name=tool_name,
        tool_input=tool_args,
        tool_output=str(out),
    )
    if tool_name == "final_answer":
        return {"output": out}
    else:
        return {"intermediate_steps": [action_out]}
    
    from langgraph.graph import StateGraph, END

# build the graph and add nodes using the function-schema's name so routing matches
graph = StateGraph(AgentState)

graph.add_node("oracle", run_oracle)
graph.add_node(search_schema["function"]["name"], run_tool)
# graph.add_node("final_answer", run_tool)

graph.set_entry_point("oracle")  # insert query here

graph.add_conditional_edges(  # - - - >
    source="oracle",  # where in graph to start
    path=router,  # function to determine which node is called
)

# create edges from each tool back to the oracle
for tool_obj in [search_schema]:
    tool_name = tool_obj["function"]["name"]
    if tool_name != "final_answer":
        graph.add_edge(tool_name, "oracle")  # ————————>

# # if anything goes to final answer, it must then move to END
# graph.add_edge("final_answer", END)

runnable = graph.compile()
out = runnable.invoke({
    "input": "hi im looking for a software engineer",
    "chat_history": [],
})
print(out)