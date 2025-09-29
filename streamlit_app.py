"""Simple Streamlit UI for the amin_agent runner.

Run with: `streamlit run streamlit_app.py`
"""

import streamlit as st
from amin_agent.main import run_with_input
import json


st.set_page_config(page_title="Amin Agent", layout="wide")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []  # list of {'role': 'user'|'assistant', 'content': str}


st.title("Amin Recruiter Agent")


def append_message(role: str, content: str):
    st.session_state.chat_history.append({"role": role, "content": content})


with st.form("query_form"):
    query = st.text_area("Your message", value="Data Scientist with Python and SQL", height=120)
    submitted = st.form_submit_button("Send")

if submitted and query.strip():
    append_message("user", query)
    with st.spinner("Running agent..."):
        result = run_with_input(query)

    # result may be: {'assistant_reply': str, 'state': {...}} or final state dict
    if isinstance(result, dict) and "assistant_reply" in result:
        assistant_text = result["assistant_reply"]
        append_message("assistant", assistant_text)
        # store pending assistant message for Continue action
        st.session_state.pending_assistant = assistant_text
        st.session_state.last_state = result.get("state")
    else:
        # assume final state returned
        append_message("assistant", "(Agent finished and returned an answer)")
        st.session_state.last_state = result

st.subheader("Chat")
for i, msg in enumerate(st.session_state.chat_history):
    if msg["role"] == "user":
        st.markdown(f"**You:** {msg['content']}")
    else:
        st.markdown(f"**Agent:** {msg['content']}")
        # for the latest assistant message, show a Continue button
        if i == len(st.session_state.chat_history) - 1 and msg["role"] == "assistant":
            if st.button("Continue", key=f"continue_{i}"):
                # send the assistant's clarifying question back into the agent
                reply = msg["content"]
                append_message("user", reply)
                with st.spinner("Continuing agent..."):
                    result = run_with_input(reply)
                if isinstance(result, dict) and "assistant_reply" in result:
                    assistant_text = result["assistant_reply"]
                    append_message("assistant", assistant_text)
                    st.session_state.pending_assistant = assistant_text
                    st.session_state.last_state = result.get("state")
                else:
                    append_message("assistant", "(Agent finished and returned an answer)")
                    st.session_state.last_state = result

st.markdown("---")
st.subheader("Agent last state")
st.json(st.session_state.get("last_state", {}))

if st.session_state.get("last_state") and isinstance(st.session_state["last_state"], dict):
    out = st.session_state["last_state"].get("output")
    if out:
        st.subheader("Agent Output")
        st.json(out)
