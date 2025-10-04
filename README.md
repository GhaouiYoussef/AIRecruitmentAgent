<div align="center">

# AI Recruitment Agent System

End‑to‑end modular system for: (1) LinkedIn talent discovery & profile extraction, (2) semantic multi‑factor candidate scoring, and (3) an interactive LLM assistant (Ollama) that orchestrates the workflow via tool calls.

</div>

---

## 1. Project Overview

### High‑Level Architecture

```
┌────────────────────────┐        ┌────────────────────────┐        ┌────────────────────────┐
│  LinkedIn Search &     │  REST  │   Candidate Scorer     │  REST  │   LLM Agent / UI        │
│  Extraction Service    │ <----> │ (FAISS + Embeddings)   │ <----> │ (Ollama + Streamlit)    │
│  (FastAPI + Selenium)  │        │  /scorer_tool/*        │        │  tools: search/score    │
└──────────┬─────────────┘        └──────────┬─────────────┘        └──────────┬─────────────┘
		 │  (Selenium drives Chrome)        │                               │
		 │                                   │                               │
		 ▼                                   ▼                               ▼
   LinkedIn Web UI                    JSON Candidate Profiles          User queries (JD / intent)

				 Shared filesystem folder:  Full system/tmp_candids_jsons
				 Job description input:     ollama_recruiter/data/jd_input
```

### Components
| Component | Path | Purpose |
|-----------|------|---------|
| LinkedIn API Service | `Full system/linkedin_api/server.py` | Provides `/search` (candidate links) and `/extract` (profile JSON) using a persistent Selenium Chrome session (profile saved under `.chrome-profile-linkedin`). |
| Candidate Scorer Service | `Full system/candidate_scorer/server.py` | Indexes extracted JSON profiles and scores them against a job description (embeddings + section weighting). Exposes `/scorer_tool/*` endpoints. |
| Agent / Orchestrator | `ollama_recruiter/` (`agent_runtime.py`, `tools.py`, `streamlit_app.py`) | Uses an Ollama local model to call tools: search -> extract -> score. Presents interactive chat (Streamlit). |
| Temp Candidate JSONs | `Full system/tmp_candids_jsons/` | Intermediate storage of raw extracted candidate data (deleted/archived optionally). |
| Job Description Inputs | `ollama_recruiter/data/jd_input/` | Place a `job_description.txt` or timestamped file consumed by the agent scoring pipeline. |
| Postman Collection | `HR-AI-Agent.postman_collection.json` | Manual testing of REST endpoints for search, extraction, profile loading & scoring. |

### Data / Control Flow
1. User (or agent) supplies a job description & search intent/query.
2. Agent calls LinkedIn service `/search` → returns candidate profile URLs.
3. For each URL, agent calls `/extract` → stores structured JSON in `tmp_candids_jsons`.
4. Agent (or manual call) hits scorer `/scorer_tool/load_profiles` → indexes embeddings.
5. Agent sends JD text to `/scorer_tool/score` → gets ranked candidates with section breakdown.
6. Streamlit UI / console presents final ranked results.

Environment variables (see below) allow overriding endpoints and Selenium / credentials.

---

## 2. Environment Setup

You will create three isolated virtual environments—one per service—to keep dependencies clean.

### 2.1 Prerequisites
* Python 3.11+ (matching your local dev target)
* Google Chrome (latest stable)
* ChromeDriver (matching your Chrome version)
  * Official download: https://chromedriver.chromium.org/downloads
  * Put the executable somewhere stable (e.g. `C:/tools/chromedriver/chromedriver.exe`).
* (Optional) `Ollama` installed locally for LLM inference: https://ollama.com

### 2.2 Clone Repository
```powershell
git clone <your-fork-or-origin-url> AIRecruitmentAgent
cd AIRecruitmentAgent
```

### 2.3 Create & Activate Virtual Environments

Run these in PowerShell from the project root.

#### a) LinkedIn Service (`venv_linkedin`)
```powershell
python -m venv venv_linkedin
./venv_linkedin/Scripts/Activate.ps1
pip install --upgrade pip
pip install -r "Full system/linkedin_api/requirements_linkedin.txt"
```

#### b) Candidate Scorer (`venv_scorer`)
```powershell
python -m venv venv_scorer
./venv_scorer/Scripts/Activate.ps1
pip install --upgrade pip
pip install -r "Full system/candidate_scorer/requirements_scorer.txt"
```

#### c) Agent / UI (`venv_agent`)
```powershell
python -m venv venv_agent
./venv_agent/Scripts/Activate.ps1
pip install --upgrade pip
pip install -r "ollama_recruiter/requirements_agent.txt"
```

Deactivate an environment at any time with:
```powershell
deactivate
```

### 2.4 Environment Variables
Create a `.env` file at the project root (or set in your shell) for the LinkedIn service & agent:
```
LK_USERNAME=your_linkedIn_email
LK_PASSWORD=your_linkedIn_password
CHROMEDRIVER_PATH=C:/tools/chromedriver/chromedriver.exe
CHROME_PROFILE_DIR=.chrome-profile-linkedin
# Optional overrides:
LINKEDIN_SEARCH_URL=http://127.0.0.1:8000/search
LINKEDIN_EXTRACT_URL=http://127.0.0.1:8000/extract
CANDIDATE_SCORER_URL=http://127.0.0.1:8001/scorer_tool
LINKEDIN_LOGIN_WAIT_SECONDS=25
HEADLESS=0  # set to 1 to enable headless extraction (if implemented)
```

> Keep credentials private. For production, consider a secrets manager.

### 2.5 Verifying ChromeDriver
Run (from any activated venv):
```powershell
& "C:/tools/chromedriver/chromedriver.exe" --version
```
Ensure the major version matches installed Chrome (open chrome://settings/help).

---

## 3. LinkedIn Scraper Notes

LinkedIn frequently A/B tests and rotates CSS/class selectors. The extraction utilities in `linkedin_api/content_extractor/functions.py` or `candidate_searcher/functions.py` may break suddenly.

Troubleshooting / Updating Selectors:
1. Re-run `/search` then `/extract` and observe server terminal logs for element lookup failures.
2. Open the failing profile in a normal Chrome window (or the persisted profile directory) and inspect elements (Right‑click → Inspect) to find updated class names.
3. Edit the relevant lookup in the functions file (e.g., `driver.find_element(By.CLASS_NAME, "newClass")`).
4. Restart the LinkedIn service.
5. For iterative debugging, create a minimal notebook (see `DEBUGGER_NOTEBOOKS/`) to manually run the extraction logic and print raw HTML snippets.

Best Practices:
* Avoid heavy rapid scraping (risk of temporary blocks).
* Leverage the persistent Chrome profile to reduce logins & 2FA friction.
* If login loops occur: delete `.chrome-profile-linkedin` directory to force a clean state.

---

## 4. Testing the Functions (Postman)

Use the provided Postman collection `HR-AI-Agent.postman_collection.json`.

Steps:
1. Open Postman → Import → Choose the JSON file.
2. Ensure the LinkedIn service & scorer service are running (see next section) before invoking endpoints.
3. Example sequence:
   * `GET http://127.0.0.1:8000/search?query=python%20backend&num_candidates=5`
   * `GET http://127.0.0.1:8000/extract?profile_url=<candidate_profile_url>`
   * `POST http://127.0.0.1:8001/scorer_tool/load_profiles` (JSON body: `{ "json_folder": "Full system/tmp_candids_jsons", "exp_agg": "sum_norm", "reset": true }`)
   * `POST http://127.0.0.1:8001/scorer_tool/score` (JSON body: `{ "job_text": "<paste JD text>", "top_k_search": 200 }`)
4. Validate responses: `indexed_profiles`, `results`, and per candidate score breakdown.

---

## 5. Usage Guide (Run Order)

### 5.1 Start LinkedIn Search/Extraction Service
Environment: activate `venv_linkedin`.
```powershell
./venv_linkedin/Scripts/Activate.ps1
uvicorn "Full system.linkedin_api.server:app" --host 127.0.0.1 --port 8000 --reload
```
You should see logs about driver creation on first `/search` or `/extract` call.

### 5.2 Start Candidate Scorer Service
Environment: activate `venv_scorer`.
```powershell
./venv_scorer/Scripts/Activate.ps1
uvicorn "Full system.candidate_scorer.server:app" --host 127.0.0.1 --port 8001 --reload
```
Health check:
```powershell
curl http://127.0.0.1:8001/scorer_tool/health
```

### 5.3 (Optional) Prepare Job Description
Place a file in `ollama_recruiter/data/jd_input/` named `job_description.txt` (or use a timestamped file). The agent will load the most recent.

### 5.4 Run the Agent (CLI / Streamlit)
Environment: activate `venv_agent`.

#### a) Streamlit UI
```powershell
./venv_agent/Scripts/Activate.ps1
streamlit run ollama_recruiter/streamlit_app.py
```
Enter a search query (e.g., "senior python data engineer Tunisia") – the agent will chain: search → extract → score. Results and scores appear in the UI.

#### b) Direct Tool Invocation (Programmatic)
From inside `venv_agent`:
```powershell
python -c "from ollama_recruiter.tools import linkedin_search_tool; print(linkedin_search_tool('python backend engineer', 3))"
```
Set `test_mode_extract=True` / `test_mode_score=True` for dry runs:
```powershell
python -c "from ollama_recruiter.tools import linkedin_search_tool; print(linkedin_search_tool('python backend', 3, test_mode_extract=True))"
```

### 5.5 Manual Scoring Without Agent
If you just want to score previously extracted profiles:
```powershell
# 1. Ensure scorer running
curl -X POST http://127.0.0.1:8001/scorer_tool/load_profiles -H "Content-Type: application/json" `
	-d '{"json_folder":"Full system/tmp_candids_jsons","exp_agg":"sum_norm","reset":true}'

# 2. Send job description inline
curl -X POST http://127.0.0.1:8001/scorer_tool/score -H "Content-Type: application/json" `
	-d '{"job_text":"We need a Python engineer with FAISS & embeddings experience.","top_k_search":200}'
```

### 5.6 Stopping Services
Press `Ctrl + C` in each terminal. ChromeDriver processes should exit automatically; if orphaned, kill via Task Manager.

---

## 6. Key Environment Variables Summary
| Variable | Purpose | Default (if unset) |
|----------|---------|--------------------|
| `LK_USERNAME` / `LK_PASSWORD` | LinkedIn credentials | None (required) |
| `CHROMEDRIVER_PATH` | Path to ChromeDriver | Hardcoded fallback in code (update recommended) |
| `CHROME_PROFILE_DIR` | Persisted Chrome profile dir | `.chrome-profile-linkedin` |
| `LINKEDIN_SEARCH_URL` | Agent search endpoint | `http://127.0.0.1:8000/search` |
| `LINKEDIN_EXTRACT_URL` | Agent extraction endpoint | `http://127.0.0.1:8000/extract` |
| `CANDIDATE_SCORER_URL` | Agent scoring endpoint base | `http://127.0.0.1:8001/scorer_tool` |
| `LINKEDIN_LOGIN_WAIT_SECONDS` | Max wait after login | `25` |
| `HEADLESS` | Enable headless (if logic present) | `0` |

---

## 7. Troubleshooting & Tips
| Issue | Cause | Fix |
|-------|-------|-----|
| Selenium fails to locate element | LinkedIn DOM changed | Update selector in relevant function file. |
| Infinite login loop | Stale cookies / checkpoint | Delete `.chrome-profile-linkedin` dir and retry. |
| Empty scoring results | Profiles not loaded | Call `/scorer_tool/load_profiles` first. |
| `chromedriver` version mismatch | Chrome updated | Download matching driver version. |
| Agent returns only links (no scores) | `test_mode_score=True` or scoring error | Check scorer logs & ensure JD file present. |

Logging: watch the terminal running each service for stack traces and debug messages (search/extract scaffolding uses `_log`).

---

## 8. Extensibility Ideas (Optional)
* Add caching layer for already extracted profiles.
* Replace raw Selenium selectors with resilient XPath + heuristics.
* Add CI test harness mocking LinkedIn HTML snapshots.
* Provide Dockerfiles per service for reproducible deployment.

---

## 9. License & Attribution
Add your license information here (e.g., MIT). Ensure no proprietary LinkedIn data is stored or redistributed—use responsibly and comply with platform terms.

---

## 10. Quick Start (TL;DR)
```powershell
# 1. Create envs & install deps (see sections 2.3 a/b/c)
# 2. Set .env with LinkedIn credentials & CHROMEDRIVER_PATH
# 3. Terminal 1
./venv_linkedin/Scripts/Activate.ps1; uvicorn "Full system.linkedin_api.server:app" --port 8000 --reload
# 4. Terminal 2
./venv_scorer/Scripts/Activate.ps1; uvicorn "Full system.candidate_scorer.server:app" --port 8001 --reload
# 5. Terminal 3 (Agent UI)
./venv_agent/Scripts/Activate.ps1; streamlit run ollama_recruiter/streamlit_app.py
# 6. Interact via UI; watch tmp_candids_jsons fill with JSON; scores appear.
```

Happy recruiting!

