import streamlit as st
import ollama
import time
from typing import Iterable
def linkedin_search_tool(query: str, num_candidates: int = 5):
    """
    Performs a LinkedIn search using Selenium and returns candidate profile links.
    """
    # from linkedin_api.functions import linkedin_query_search, get_candidates_links  # adjust import path
    # import time

    # # Reuse driver setup from your previous code
    # from selenium import webdriver
    # from selenium.webdriver.chrome.service import Service
    # from selenium.webdriver.chrome.options import Options

    # chrome_options = Options()
    # chrome_options.add_argument("--disable-dev-shm-usage")
    # chrome_options.add_argument("--disable-gpu")
    # chrome_options.add_argument("--window-size=1920,1080")
    # chrome_options.add_argument("--disable-extensions")
    # chrome_options.add_argument("--disable-infobars")
    
    # service = Service(executable_path="C:/YoussefENSI_backup/Eukliadia-test/chromedriver.exe")
    # driver = webdriver.Chrome(service=service, options=chrome_options)

    # # Login
    # from dotenv import load_dotenv
    # import os
    # load_dotenv()
    # LK_USERNAME = os.getenv("LK_USERNAME")
    # LK_PASSWORD = os.getenv("LK_PASSWORD")

    # driver.get("https://www.linkedin.com/login")
    # from selenium.webdriver.common.by import By
    # from selenium.webdriver.support.ui import WebDriverWait
    # from selenium.webdriver.support import expected_conditions as EC

    # WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "username")))
    # driver.find_element(By.ID, "username").send_keys(LK_USERNAME)
    # driver.find_element(By.ID, "password").send_keys(LK_PASSWORD)
    # driver.find_element(By.XPATH, '//*[@type="submit"]').click()

    # time.sleep(5)  # wait to ensure login completes

    # # Run search
    # linkedin_query_search(driver, query)
    # links = get_candidates_links(driver, num_candidates=num_candidates)

    # driver.quit()  # close browser
    links = ['https://www.linkedin.com/in/saber-chadded-36552b192/', 'https://www.linkedin.com/in/guesmi-wejden-5269222aa/', 'https://www.linkedin.com/in/hichem-dridi/', 'https://www.linkedin.com/in/nour-hamdi/', 'https://www.linkedin.com/in/iyadh-chaouch-072077225/']
    return links

# ---------------- Helpers ----------------
def get_system_tools_prompt(system_prompt: str, tools: list[dict]):
    tools_str = "\n".join([f"{t['name']}: {t['description']}" for t in tools])
    return f"{system_prompt}\n\nAvailable tools:\n{tools_str}"

def multiply_tool(a: float, b: float) -> float:
    try:
        return a * b
    except Exception as e:
        return f"Error: {e}"

def chunk_text(text: str, chunk_size: int = 40):
    for i in range(0, len(text), chunk_size):
        yield text[i:i+chunk_size]

def stream_to_placeholder(source, placeholder, sleep: float = 0.03):
    """Stream string or generator into a Streamlit placeholder."""
    output = ""
    if isinstance(source, Iterable) and not isinstance(source, (str, bytes, dict)):
        for chunk in source:
            chunk_str = str(chunk)
            output += chunk_str
            placeholder.markdown(output)
            time.sleep(sleep)
    else:
        for chunk in chunk_text(str(source)):
            output += chunk
            placeholder.markdown(output)
            time.sleep(sleep)
    return output

SYSTEM_PROMPT = """You are the Oracle: a specialized recruiter agent and decision-maker.
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
- You may call the search tool (linkedin_search) up to 3 times total.
- After any use of the search tool, you MUST call the final_answer tool to produce the human-facing summary and recommendations.
- If the user asks something unrelated to recruiting/hiring or requests a direct answer, call final_answer directly.

Behavior & response style:
- Prioritize concise, evidence-based recommendations derived from tool outputs.
- If results are insufficient or ambiguous, ask a focused clarifying question (do not call a tool) before searching further.
- Always include practical next steps (e.g., outreach template, suggested interview questions, priority ranking).
- Do not include any explanatory or narrative text when issuing a tool call — only emit the required JSON.

Available tools:
- linkedin_search: searches LinkedIn for candidate profiles.
    Parameters: {"query": "<role or skill>", "num_candidates": <int>}
- final_answer: produces a human-facing summary and recommendations.
    Parameters: {"candidates": <list_of_candidate_profiles>, "summary_notes": "<any additional context>"}

Follow these rules strictly to ensure consistent, parseable tool usage and clear recruiter-oriented recommendations."""
import json

def run_tool_from_model(output_text):
    try:
        # Extract JSON part from the output
        start = output_text.index("{")
        end = output_text.rindex("}") + 1
        tool_call_json = output_text[start:end]
        tool_call = json.loads(tool_call_json)
        tool_name = tool_call["name"]
        params = tool_call["parameters"]

        if tool_name == "linkedin_search":
            return linkedin_search_tool(**params)  # Call your Selenium tool
        elif tool_name == "final_answer":
            # Summarize candidate info
            return final_answer_tool(**params)
        else:
            return f"Unknown tool: {tool_name}"

    except Exception as e:
        return f"Error parsing or running tool: {e}"

# ---------------- Session ----------------
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "system", "content": get_system_tools_prompt(
            system_prompt=SYSTEM_PROMPT,
            tools = [
    {"name": "multiply", "description": "Multiply two numbers: multiply(a, b)"},
    {"name": "linkedin_search", "description": "Search LinkedIn for candidates: linkedin_search(query, num_candidates=5)"}
]
        )}
    ]

st.title("Ollama HR Chatbot (Streamlit)")

# ---------------- Tool UI ----------------
with st.expander("Multiply tool (quick test)", expanded=False):
    a = st.number_input("a", value=6.0)
    b = st.number_input("b", value=7.0)
    if st.button("Multiply"):
        result = multiply_tool(a, b)
        # Assistant reflects on tool result
        assistant_text = f"I used the multiply tool: multiply({a}, {b}) = {result}. This is the computed result."
        with st.chat_message("assistant"):
            placeholder = st.empty()
            stream_to_placeholder(assistant_text, placeholder)
        st.session_state.messages.append({"role": "assistant", "content": assistant_text})
with st.expander("LinkedIn search tool", expanded=False):
    query = st.text_input("Search query (e.g., 'Data Scientist')", value="Data Scientist")
    num_candidates = st.number_input("Number of candidates", value=5, min_value=1, max_value=20)
    if st.button("Search LinkedIn"):
        with st.chat_message("assistant"):
            placeholder = st.empty()
            # Stream tool output
            results = linkedin_search_tool(query, num_candidates)
            assistant_text = f"Found {len(results)} candidates:\n" + "\n".join(results)
            stream_to_placeholder(assistant_text, placeholder)
        # Store result in chat
        st.session_state.messages.append({"role": "assistant", "content": assistant_text})

# ---------------- Render chat history ----------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ---------------- Chat input ----------------
user_input = st.chat_input("Send a message")
import json

if user_input:
    # 1️⃣ Append user message
    st.session_state.messages.append({"role": "user", "content": user_input})

    # 2️⃣ Prepare assistant message
    assistant_content = ""
    placeholder = st.empty()

    # 3️⃣ Stream model response
    try:
        for chunk in ollama.chat(
            model="llama3-groq-tool-use:8b",
            messages=st.session_state.messages,
            stream=True
        ):
            if "message" in chunk:
                content_chunk = chunk["message"].get("content", "")
                assistant_content += content_chunk
                placeholder.markdown(assistant_content)  # stream live
    except Exception as e:
        assistant_content = f"Error: {e}"
        placeholder.markdown(assistant_content)

    # 4️⃣ Append the full assistant message after streaming finishes
    st.session_state.messages.append({"role": "assistant", "content": assistant_content})

    # 5️⃣ Check for a tool call in the assistant's output
    if "{" in assistant_content and "name" in assistant_content:
        try:
            # Parse JSON tool call
            start = assistant_content.index("{")
            end = assistant_content.rindex("}") + 1
            tool_call_json = assistant_content[start:end]
            tool_call = json.loads(tool_call_json)
            tool_name = tool_call["name"]
            params = tool_call["parameters"]

            # Run the tool
            if tool_name == "linkedin_search":
                tool_result = linkedin_search_tool(**params)
            elif tool_name == "final_answer":
                tool_result = final_answer_tool(**params)
            else:
                tool_result = f"Unknown tool: {tool_name}"

            # Append tool result to chat history
            st.session_state.messages.append({"role": "tool", "content": str(tool_result)})

            # Feed the result back to the model to get final summary
            followup_prompt = f"Use this tool result to produce a human-facing summary:\n{tool_result}"
            final_answer_content = ""
            placeholder_final = st.empty()
            for chunk in ollama.chat(
                model="llama3-groq-tool-use:8b",
                messages=st.session_state.messages + [{"role": "user", "content": followup_prompt}],
                stream=True
            ):
                if "message" in chunk:
                    final_answer_content += chunk["message"].get("content", "")
                    placeholder_final.markdown(final_answer_content)

            # Append final summary to chat history
            st.session_state.messages.append({"role": "assistant", "content": final_answer_content})

        except Exception as e:
            st.session_state.messages.append({"role": "assistant", "content": f"Error running tool: {e}"})


    # 🔟 Rerender full chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
