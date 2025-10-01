import streamlit as st
from agent_runtime import OracleRuntime

st.set_page_config(page_title="Oracle Recruiter", page_icon="🧠", layout="wide")

st.title("🧠 Oracle Recruiter – conversational agent")
st.caption("Backed by Ollama + LangGraph. It can search LinkedIn via your local API.")

with st.sidebar:
    st.header("Settings")
    default_query = st.text_input("Default search query", value="software engineer python")
    num_candidates = st.number_input("Num candidates", min_value=1, max_value=20, value=5)
    st.markdown("""
    Tip: Ensure your LinkedIn FastAPI search service is running on http://127.0.0.1:8000/search
    and that the model 'llama3-groq-tool-use:8b' is available in Ollama.
    """)

if "runtime" not in st.session_state:
    st.session_state.runtime = OracleRuntime()

if "messages" not in st.session_state:
    st.session_state.messages = []

# Chat history UI
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"]) 

prompt = st.chat_input("Describe the role you need to hire for…")

if prompt:
    # Append user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Invoke agent
    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            # Build a chat_history compatible with runtime (list[dict])
            history = [m for m in st.session_state.messages if m["role"] in ("user", "assistant")]
            result = st.session_state.runtime.invoke(prompt, history[:-1])

            assistant_text = result.get("assistant", "")
            st.markdown(assistant_text)

            actions = result.get("actions", [])
            tool_outputs = result.get("tool_outputs", [])
            with st.expander("Debug: tool calls", expanded=False):
                st.json({"actions": actions})
                if tool_outputs:
                    st.markdown("**Tool outputs:**")
                    for i, out in enumerate(tool_outputs, 1):
                        st.code(str(out))

    st.session_state.messages.append({"role": "assistant", "content": assistant_text})
