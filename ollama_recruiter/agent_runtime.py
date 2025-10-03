from typing import List, Union, TypedDict
import json

from pydantic import BaseModel
import ollama
from tools import linkedin_search_tool
from prompts import search_system_prompt as system_prompt

class Rec(BaseModel):
    top_candidates_liks: list[str]

    def __str__(self):
        candidates_str = "\n".join(self.top_candidates_liks)
        return f"Top Candidates Links:\n{candidates_str}"


def get_system_tools_prompt(system_prompt: str, tools: list[dict]):
    tools_str = "\n".join([str(tool) for tool in tools])
    return f"{system_prompt}\n\nYou may use the following tools:\n{tools_str}"


class AgentAction(BaseModel):
    tool_name: str
    tool_input: dict
    tool_output: str | None = None

    @classmethod
    def from_ollama_tool_call(cls, ollama_response: dict):
        """Parse a tool call from an Ollama chat response.
        Expects response["message"]["tool_calls"][0]["function"] with name and arguments.
        """
        try:
            msg = ollama_response.get("message", {})
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                return None
            fn_call = tool_calls[0].get("function", {})
            name = fn_call.get("name")
            args = fn_call.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    # Fall back to empty dict if not valid JSON string
                    args = {}
            if args is None:
                args = {}
            if not name:
                return None
            return cls(tool_name=name, tool_input=args)
        except Exception as e:
            print(f"Error parsing ollama tool call response:\n{ollama_response}\n")
            raise e


def action_to_message(action: AgentAction):
    '''Convert an AgentAction to a list of messages (assistant + user).'''

    assistant_content = json.dumps({"name": action.tool_name, "parameters": action.tool_input})

    assistant_message = {"role": "assistant", "content": assistant_content}

    user_message = {"role": "user", "content": action.tool_output}

    return [assistant_message, user_message]


def create_scratchpad(intermediate_steps: list[AgentAction]):
    '''Create a scratchpad (list of messages) from intermediate steps.'''
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


def call_llm(user_input: str, chat_history: list[dict], intermediate_steps: list[AgentAction], tools: list[dict]):
    """Call the LLM and return either an AgentAction (tool call) or assistant text.

    Returns a dict: {"assistant_text": Optional[str], "action": Optional[AgentAction], "raw": response}
    """
    scratchpad = create_scratchpad(intermediate_steps)
    messages = [
        {"role": "system", "content": get_system_tools_prompt(system_prompt, tools)},
        *chat_history,
        {"role": "user", "content": user_input},
        *scratchpad,
    ]
    res = ollama.chat(
        # model="llama3-groq-tool-use:8b",
        model="granite4:micro",
        messages=messages,
        tools=tools,
    )

    # Prefer tool call if present; otherwise return assistant text
    action = AgentAction.from_ollama_tool_call(res)
    assistant_text = None
    if not action:
        assistant_text = (res.get("message", {}) or {}).get("content")

    return {"assistant_text": assistant_text, "action": action, "raw": res}


# def final_answer(answer: str) -> str:
#     return answer


tool_str_to_func = {}


class OracleRuntime:
    '''Manages the conversational agent runtime with tool integration.'''

    def __init__(self):
        from semantic_router.utils.function_call import FunctionSchema
        search_schema = FunctionSchema(linkedin_search_tool).to_ollama()
        # SR workaround
        search_schema["function"]["parameters"]["properties"]["query"]["description"] = None
        # final_schema = FunctionSchema(final_answer).to_ollama()

        self.schemas = [search_schema]#, final_schema]
        self.search_tool_name = search_schema["function"]["name"]
        # self.final_tool_name = final_schema["function"]["name"]

        global tool_str_to_func
        tool_str_to_func[self.search_tool_name] = linkedin_search_tool
        # tool_str_to_func[self.final_tool_name] = final_answer

    def _execute_action(self, action: AgentAction) -> AgentAction:
        fn = tool_str_to_func.get(action.tool_name)
        out = None
        if fn:
            out = fn(**action.tool_input)
        return AgentAction(tool_name=action.tool_name, tool_input=action.tool_input, tool_output=str(out) if out is not None else None)

    def invoke(self, user_input: str, history: list[dict]):
        # Conversational loop: allow up to 3 tool calls, otherwise reply directly
        intermediate: list[AgentAction] = []
        actions: list[dict] = []
        tool_outputs: List[str] = []
        assistant_text: str | None = None

        max_tool_calls = 3
        for _ in range(max_tool_calls + 1):  # +1 to allow a final assistant turn after last tool
            res = call_llm(user_input, history, intermediate, self.schemas)
            if res["action"] is None:
                assistant_text = res["assistant_text"] or assistant_text
                break
            # Execute tool call
            executed = self._execute_action(res["action"])
            actions.append({"name": executed.tool_name, "parameters": executed.tool_input})
            intermediate.append(executed)
            if executed.tool_output:
                tool_outputs.append(executed.tool_output)
            # After executing a tool, iterate again to let the model decide next step or produce an answer
            # The same user_input is used; scratchpad carries tool outputs.

        # Fallback assistant text if none
        if not assistant_text:
            assistant_text = "How can I help with your hiring needs? I can search when you're ready or ask a quick clarifying question first."

        return {
            "assistant": assistant_text,
            "actions": actions,
            "tool_outputs": tool_outputs,
        }
