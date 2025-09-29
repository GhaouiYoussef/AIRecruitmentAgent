"""Main entrypoint for the refactored agent.

This module constructs a small state graph and runs it once with an empty
input so it can be used as a smoke test. The public function `build_and_run`
is intentionally simple so the top-level launcher can call it.
"""

from .graph import StateGraph, END
from .actions import AgentAction, call_llm
from .tools_adapter import linkedin_scraper, final_answer
from .utils import AgentState, SYSTEM_PROMPT


def run_oracle(state: AgentState):
    print("run_oracle")
    chat_history = state["chat_history"]
    out = call_llm(
        user_input=state["input"],
        chat_history=chat_history,
        intermediate_steps=state["intermediate_steps"],
        system_prompt=SYSTEM_PROMPT,
    )
    return {"intermediate_steps": [out]}


def router(state: AgentState):
    print("router")
    if isinstance(state["intermediate_steps"], list):
        return state["intermediate_steps"][-1].tool_name
    print("Router invalid format")
    return "final_answer"


tool_str_to_func = {"linkedin_scraper": linkedin_scraper, "final_answer": final_answer}


def run_tool(state: AgentState):
    tool_name = state["intermediate_steps"][-1].tool_name
    tool_args = state["intermediate_steps"][-1].tool_input
    print(f"run_tool | {tool_name}.invoke(input={tool_args})")
    out = tool_str_to_func[tool_name](**tool_args)
    action_out = AgentAction(tool_name=tool_name, tool_input=tool_args, tool_output=str(out))
    if tool_name == "final_answer":
        return {"output": out}
    return {"intermediate_steps": [action_out]}


def create_runnable():
    """Create and return a compiled runnable graph instance."""
    graph = StateGraph(AgentState)
    graph.add_node("oracle", run_oracle)
    graph.add_node("linkedin_scraper", run_tool)
    graph.add_node("final_answer", run_tool)
    graph.set_entry_point("oracle")
    graph.add_conditional_edges(source="oracle", path=router)

    # create edges: after search go back to oracle; final_answer -> END
    graph.add_edge("linkedin_scraper", "oracle")
    graph.add_edge("final_answer", END)

    return graph.compile()


def run_with_input(user_input: str):
    """Run the agent conversational loop for a single user input.

    Behavior:
    - Call the LLM (oracle). If the LLM outputs an assistant reply (not a tool call),
      return that message so a UI can display it and await user input.
    - If the LLM issues a tool call, run the tool, attach the result to intermediate_steps,
      and continue the loop. If `final_answer` runs, return its `output`.
    """
    from .actions import AgentAction

    runnable = create_runnable()
    # initial state
    state = {
        "input": user_input,
        "chat_history": [],
        "intermediate_steps": [],
        "output": {},
    }

    # small loop to allow: LLM -> tool -> LLM -> ...
    for _ in range(8):
        # invoke one graph step; oracle will write an AgentAction into intermediate_steps
        state = runnable.invoke(state)
        # after invoke, intermediate_steps should contain an AgentAction-like object
        steps = state.get("intermediate_steps") or []
        if not steps:
            # nothing more to do
            return state

        last = steps[-1]
        # if the last step is an assistant reply (non-tool), return it so UI can show and await user input
        if hasattr(last, "tool_name") and last.tool_name == "assistant_reply":
            return {"assistant_reply": last.tool_input.get("content"), "state": state}

        # if final_answer tool invoked, output will be in state["output"]
        if hasattr(last, "tool_name") and last.tool_name == "final_answer":
            # run one more step to ensure final_answer node has completed
            state = runnable.invoke(state)
            return state

        # otherwise continue loop to let oracle decide next step
    # if we hit the loop limit, return current state
    return state


def build_and_run():
    """Legacy smoke-test runner (keeps previous semantics)."""
    out = run_with_input("")
    print("Final state:", out)
    return out


if __name__ == "__main__":
    build_and_run()
