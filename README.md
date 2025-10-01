## Oracle Recruiter – Streamlit app

This repo includes a Streamlit chat UI for the Ollama + LangGraph recruiter agent.

Requirements:
- Python 3.11 (a `.venv` is configured by VS Code)
- Ollama running locally with model `llama3-groq-tool-use:8b`
- Optional: LinkedIn FastAPI search at `http://127.0.0.1:8000/search`

Install deps:

```powershell
"C:/YoussefENSI_backup/Eukliadia-test/Git Repo/.venv/Scripts/python.exe" -m pip install -r "c:\YoussefENSI_backup\Eukliadia-test\Git Repo\requirements.txt"
```

Run:

```powershell
"C:/YoussefENSI_backup/Eukliadia-test/Git Repo/.venv/Scripts/python.exe" -m streamlit run "c:\YoussefENSI_backup\Eukliadia-test\Git Repo\ollama_recruiter\streamlit_app.py"
```

If the LinkedIn service is unavailable, the agent falls back to sample profile links.

# AI Recruitment Agent Development

- The agent that helps companies find, contact, and screen job candidates automatically. The agent
should interact with professional platforms, communicate with potential hires, and assist in decision-making.
