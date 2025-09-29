"""Agent action models and helpers."""

from pydantic import BaseModel
import json
from typing import List
from .llm import func_to_ollama_schema, call_ollama
from .tools_adapter import linkedin_scraper, final_answer


class AgentAction(BaseModel):
    tool_name: str
    tool_input: dict
    tool_output: str | None = None

    @classmethod
    def from_ollama(cls, ollama_response: dict):
        try:
            content = ollama_response["message"]["content"]
            # first try to parse as JSON function/tool call
            try:
                output = json.loads(content)
                if isinstance(output, dict) and "name" in output:
                    return cls(tool_name=output["name"], tool_input=output.get("parameters", {}))
            except Exception:
                # not JSON or not a tool call
                pass

            # fallback: treat as assistant textual reply
            return cls(tool_name="assistant_reply", tool_input={"content": content})
        except Exception as e:
            print(f"Error parsing ollama response:\n{ollama_response}\n")
            raise e

    def __str__(self):
        text = f"Tool: {self.tool_name}\nInput: {self.tool_input}"
        if self.tool_output is not None:
            text += f"\nOutput: {self.tool_output}"
        return text


def action_to_message(action: AgentAction):
    assistant_content = json.dumps({"name": action.tool_name, "parameters": action.tool_input})
    assistant_message = {"role": "assistant", "content": assistant_content}
    user_message = {"role": "user", "content": action.tool_output}
    return [assistant_message, user_message]


def create_scratchpad(intermediate_steps: List[AgentAction]):
    intermediate_steps = [action for action in intermediate_steps if action.tool_output is not None]
    scratch_pad_messages = []
    for action in intermediate_steps:
        scratch_pad_messages.extend(action_to_message(action))
    return scratch_pad_messages


def call_llm(user_input: str, chat_history: list[dict], intermediate_steps: List[AgentAction], system_prompt: str):
    # build scratchpad
    scratchpad = create_scratchpad(intermediate_steps)
    # choose tools
    from .llm import func_to_ollama_schema
    search_schema = func_to_ollama_schema(linkedin_scraper)
    final_schema = func_to_ollama_schema(final_answer)

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
        tools_used = [action.tool_name for action in intermediate_steps]
        if search_schema["function"]["name"] in tools_used:
            tools = [final_schema]
            scratchpad[-1]["content"] = "You must now use the final_answer tool."
        else:
            tools = [search_schema, final_schema]
    else:
        tools = [search_schema, final_schema]

    def get_system_tools_prompt(system_prompt: str, tools: list[dict]):
        tools_str = "\n".join([str(tool) for tool in tools])
        return f"{system_prompt}\n\nYou may use the following tools:\n{tools_str}"

    messages = [
        {"role": "system", "content": get_system_tools_prompt(system_prompt, tools)},
        *chat_history,
        {"role": "user", "content": user_input},
        *scratchpad,
    ]

    res = call_ollama(model="llama3-groq-tool-use:8b", messages=messages)
    return AgentAction.from_ollama(res)
