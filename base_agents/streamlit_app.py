# streamlit_app.py
import streamlit as st
import time
import json
from concurrent.futures import ThreadPoolExecutor

# import your agent logic (place your large agent code into oracle_agent.py)
# it must expose: call_llm, run_tool, AgentAction, search_schema (or use the search tool name string)
import oracle_agent   as agent

# small helper: name of search tool (adjust if different)
SEARCH_TOOL_NAME = agent.search_schema["function"]["name"] if hasattr(agent, "search_schema") else "linkedin_search_tool"
FINAL_TOOL_NAME = "final_answer"  # if you later add final_answer handling

st.set_page_config(page_title="Recruiter Oracle", layout="wide")

if "history" not in st.session_state:
    # history: list of dicts: {"role": "user"/"assistant", "content": "..."}
    st.session_state.history = []
if "intermediate_steps" not in st.session_state:
    # store AgentAction objects (from your agent) or serialized dicts
    st.session_state.intermediate_steps = []
if "search_count" not in st.session_state:
    st.session_state.search_count = 0
if "busy" not in st.session_state:
    st.session_state.busy = False

executor = ThreadPoolExecutor(max_workers=1)

st.title("Recruiter Oracle — Conversational Agent")
st.markdown("Ask the Oracle to find candidates, rank them, and get outreach suggestions.")

chat_col, info_col = st.columns([3,1])

with info_col:
    st.markdown("**Tool usage**")
    st.write(f"Search tool used: {st.session_state.search_count} / 3")
    if st.session_state.busy:
        st.warning("Agent busy...")

def render_chat():
    for m in st.session_state.history:
        if m["role"] == "user":
            st.chat_message("user").write(m["content"])
        else:
            # assistant message may be JSON tool-calls or natural text
            st.chat_message("assistant").write(m["content"])

def append_user_message(text: str):
    st.session_state.history.append({"role": "user", "content": text})

def append_assistant_message(text: str):
    st.session_state.history.append({"role": "assistant", "content": text})

def run_agent_loop(user_text: str):
    """
    Orchestrates: call LLM -> run tool if requested -> loop until no tool call
    """
    # append user message to UI history for context
    append_user_message(user_text)

    # local copies for passing to functions
    chat_history = list(st.session_state.history)  # messages as list[dict]
    intermediate = list(st.session_state.intermediate_steps)  # AgentAction list (may be empty)

    # safety loop: prevent infinite loops
    max_iterations = 4
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        st.session_state.busy = True
        try:
            # call your LLM wrapper
            # call_llm returns an AgentAction built from ollama output
            action = agent.call_llm(user_input=user_text, chat_history=chat_history, intermediate_steps=intermediate)
        except Exception as e:
            append_assistant_message(f"Agent call error: {e}")
            st.session_state.busy = False
            return

        # show what assistant wants to do (the strict JSON format)
        try:
            assistant_json = json.dumps({"name": action.tool_name, "parameters": action.tool_input})
        except Exception:
            assistant_json = str(action)
        append_assistant_message(assistant_json)

        # If no tool requested / or final tool, end and show final output
        if action.tool_name in (None, "", FINAL_TOOL_NAME):
            # if the action contains a direct textual answer in action.tool_output, show it
            if getattr(action, "tool_output", None):
                append_assistant_message(action.tool_output)
            st.session_state.busy = False
            break

        # Enforce search usage limits
        if action.tool_name == SEARCH_TOOL_NAME:
            if st.session_state.search_count >= 3:
                append_assistant_message("Search tool usage limit reached (3). Aborting further searches.")
                st.session_state.busy = False
                break
            st.session_state.search_count += 1

        # Run the tool (this should call your linkedin_search_tool via run_tool)
        append_assistant_message(f"⏳ Running tool `{action.tool_name}` ...")
        # run_tool expects the last AgentAction in state; we simulate that:
        # create a minimal state where intermediate_steps has action
        run_state = {
            "input": user_text,
            "chat_history": chat_history,
            "intermediate_steps": [action],
        }
        try:
            tool_result = agent.run_tool(run_state)
        except Exception as e:
            append_assistant_message(f"Tool execution error: {e}")
            st.session_state.busy = False
            return

        # if run_tool returned intermediate_steps (AgentAction objects), append them
        if "intermediate_steps" in tool_result:
            for act in tool_result["intermediate_steps"]:
                # store the action in our intermediate list for the next LLM call
                intermediate.append(act)
                # show the tool output (stringified)
                append_assistant_message(f"Tool output: {act.tool_output}")
            # push the assistant->user messages modeling that tool output will be fed back
            # so on next LLM call the scratchpad is richer
            # continue the loop to call LLM again
            st.session_state.intermediate_steps = intermediate
            # also append these tool messages into chat_history so LLM sees them
            # We reuse your action_to_message function if present
            try:
                msgs = agent.action_to_message(act)  # returns [assistant_message, user_message]
                for m in msgs:
                    chat_history.append(m)
                    # reflect those messages in UI too
                    role = m["role"]
                    content = m["content"]
                    st.session_state.history.append({"role": role, "content": content})
            except Exception:
                # generic fallback: append tool output as a user message
                chat_history.append({"role": "user", "content": str(act.tool_output)})
                st.session_state.history.append({"role": "user", "content": str(act.tool_output)})

            # continue to next iteration so the LLM can generate a final_answer
            continue

        # if run_tool returned direct output (final_answer), present and finish
        if "output" in tool_result:
            append_assistant_message("Final Answer:")
            # present tool_result["output"] nicely
            out = tool_result["output"]
            if isinstance(out, (list, dict)):
                append_assistant_message(json.dumps(out, indent=2))
            else:
                append_assistant_message(str(out))
            st.session_state.busy = False
            break

    st.session_state.busy = False
    return

# Chat UI
with chat_col:
    render_chat()
    user_input = st.chat_input("Ask the Oracle to find candidates, e.g. 'Find a backend ML engineer in Tunis'")

    if user_input:
        # Run the agent synchronously but with a spinner (so user sees progress)
        with st.spinner("Oracle thinking..."):
            # you may optionally run in thread to free Streamlit reactivity
            future = executor.submit(run_agent_loop, user_input)
            # wait for completion (blocking) - you could improve by using long-running background patterns
            while not future.done():
                time.sleep(0.1)
            exc = future.exception()
            if exc:
                st.error(f"Agent error: {exc}")
        # rerun to display new messages
        st.experimental_rerun()
