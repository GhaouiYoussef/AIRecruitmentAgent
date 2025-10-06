<div align="center">

# Local-AI-Recruiter — Ollama + Pydantic agent (CPU friendly)
Privacy-first, local recruitment assistant that scores and summarizes candidates using Ollama (local models) and lightweight Pydantic-based tools for structured tool-calls and data validation.

End-to-end modular system for: (1) LinkedIn talent discovery & profile extraction, (2) semantic multi-factor candidate scoring, and (3) an interactive LLM assistant (Ollama) that orchestrates the workflow via validated tool calls.

</div>

---


https://github.com/user-attachments/assets/80a33011-ab23-4121-b947-59cade08964b


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

You will now create TWO isolated virtual environments:

1. Server environment (`venv_server`): hosts BOTH FastAPI apps (LinkedIn search/extraction + candidate scorer)
2. Agent/UI environment (`venv_agent`): runs the Ollama orchestration + Streamlit interface

The previous separation into three environments is deprecated (the two old requirements files remain for reference but are superseded by `Full system/requirements_server.txt`).

### 2.1 Prerequisites
* Python 3.11+ (matching your local dev target)
* Google Chrome (latest stable)
* ChromeDriver (matching your Chrome version)
  * Official download: https://chromedriver.chromium.org/downloads
  * Put the executable somewhere stable (e.g. `C:/tools/chromedriver/chromedriver.exe`).
* (Optional) `Ollama` installed locally for LLM inference: https://ollama.com
* Hardware Note: This system was developed and tested **on CPU only** (no GPU required). Embedding & model inference paths default to CPU; if you later add GPU support, ensure dependencies (e.g., CUDA-enabled torch) are pinned accordingly.

### 2.2 Clone Repository
```powershell
git clone https://github.com/GhaouiYoussef/Ollama-Local-Recruiter-Agent.git
cd Ollama-Local-Recruiter-Agent
```

### 2.3 Create & Activate Virtual Environments (2 total)

Run these in PowerShell from the project root.

#### a) Server (LinkedIn + Scorer combined) — `venv_server`
```powershell
python -m venv venv_server
./venv_server/Scripts/Activate.ps1
pip install --upgrade pip
pip install -r "Full system/requirements_server.txt"
```

#### b) Agent / UI — `venv_agent`
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
5. For iterative debugging, use the notebooks (see `DEBUGGER_NOTEBOOKS/`) to manually run the extraction logic and print raw HTML snippets.

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

### 5.1 Start Services (Shared Environment)
Activate `venv_server` once per terminal you need. You still run two FastAPI processes (they remain separate apps) but they share the same dependencies.

#### Terminal 1: LinkedIn Search/Extraction Service
```powershell
./venv_server/Scripts/Activate.ps1
uvicorn "Full system.linkedin_api.server:app" --host 127.0.0.1 --port 8000 --reload
```

#### Terminal 2: Candidate Scorer Service
```powershell
./venv_server/Scripts/Activate.ps1
uvicorn "Full system.candidate_scorer.server:app" --host 127.0.0.1 --port 8001 --reload
```
Health check:
```powershell
curl http://127.0.0.1:8001/scorer_tool/health
```

### 5.3 Prepare Job Description
If you attach a text file containing the job description:
	- The file will be loaded into `ollama_recruiter/data/jd_input/` saved with its name + timestamp, then renamed `job_description.txt` and used for scoring.
else:
	- The agent will only return the cnadidates wuthout scoring them against the job description.

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

### 5.7 Migration Note (From 3 Envs → 2 Envs)
If you previously created `venv_linkedin` and `venv_scorer`, you can remove them after verifying `venv_server` works:
```powershell
Remove-Item -Recurse -Force venv_linkedin
Remove-Item -Recurse -Force venv_scorer
```
The old requirement files remain for historical reference but are no longer used.

---

## 6. Data Lifecycle, Temporary Artifacts & Cleanup

This section explains how the system treats candidate JSON extractions and job description (JD) files—especially when automatic cleanup is enabled.

### 6.1 Key Folders
| Path | Purpose | Created By | Typical Lifetime |
|------|---------|------------|------------------|
| `Full system/tmp_candids_jsons/` | Raw extracted candidate profile JSON files (one per LinkedIn profile). | LinkedIn extraction tool inside the agent or manual `/extract` calls. | Until you manually delete OR automatic cleanup runs. |
| `ollama_recruiter/data/jd_input/` | Input job description text files. The system picks the first `*.txt`. | User (you) drop files here. | Original file may be archived if cleanup enabled. |
| `ollama_recruiter/data/jd_input/job_description.txt` | Stable copy the agent reads for scoring. Created if missing. | Agent (`_prepare_job_description`). | Persisted (NOT auto-deleted). |
| `ollama_recruiter/data/jd_history/` | Archive of past JD files with timestamps. | Agent when cleanup enabled. | Grows over time unless pruned. |

### 6.2 What Happens During a Normal (Default) Run
1. You place (or reuse) a JD file under `jd_input/` (e.g., `20251004_051747_job_desc.txt`).
2. The agent copies the first matching file to a stable name `job_description.txt` if it doesn't already exist.
3. Each candidate extracted is saved as `<linkedin_slug>.json` in `Full system/tmp_candids_jsons/`.
4. Scoring loads all JSONs in that folder and builds an index (reset behaviour is controlled in the scorer request payload).
5. Nothing is deleted automatically (default). You can inspect JSON files or rerun scoring without re-extraction.

### 6.3 Enabling Automatic Cleanup & Archiving
Set the environment variable before running the agent (recommended) OR modify the flag in code:

#### Option A: Environment Variable (preferred)
Add to your `.env` or export in PowerShell session:
```powershell
$env:CLEANUP_AND_ARCHIVE = "1"
```
or place in `.env`:
```
CLEANUP_AND_ARCHIVE=1
```

#### Option B: Direct Code Toggle
Edit `ollama_recruiter/tools.py` and set `CLEANUP_AND_ARCHIVE = True` (not recommended for production—env var is cleaner).

### 6.4 Cleanup Sequence (Triggered Only After Successful Scoring)
If `CLEANUP_AND_ARCHIVE` resolves to true:
1. The ORIGINAL JD file that was first discovered (e.g., `20251004_051747_job_desc.txt`) is MOVED into `jd_history/` as `job_description_<timestamp>.txt`.
	* The stable `job_description.txt` copy remains for reproducibility or audit.
2. All `*.json` files within `Full system/tmp_candids_jsons/` are deleted (count is logged).
3. Failures (e.g., permission issues) are caught and printed without aborting the overall run.

### 6.5 Practical Scenarios
| Scenario | Recommended Setting | Reason |
|----------|---------------------|--------|
| Debugging extraction selectors | `CLEANUP_AND_ARCHIVE=0` | Keep JSONs to inspect their structure. |
| Regular iterative sourcing & scoring | `CLEANUP_AND_ARCHIVE=0` | Reuse previous JSONs without re-hitting LinkedIn. |
| Production / clean runs to minimize disk accumulation | `CLEANUP_AND_ARCHIVE=1` | Prevent stale data build-up & archive JD trace. |

### 6.6 Restoring or Auditing Past Runs
* Past JDs: check `jd_history/` (timestamp naming). Compare diffs with latest `job_description.txt`.
* Candidate Data: if cleanup was enabled, raw JSONs are gone—re-run extraction to regenerate. If disabled, you can snapshot the folder or version control selected anonymized examples.

### 6.7 Manual Housekeeping Commands
Delete all candidate JSONs manually (PowerShell):
```powershell
Remove-Item -Force -ErrorAction SilentlyContinue "Full system/tmp_candids_jsons/*.json"
```
List archived JDs:
```powershell
Get-ChildItem "ollama_recruiter/data/jd_history" -Filter *.txt | Sort-Object LastWriteTime -Descending
```

---

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
| Import error after upgrade to combined env | Mixed old venvs lingering | Delete old `venv_linkedin` / `venv_scorer` and reinstall `venv_server`. |
| Cleanup not happening | `CLEANUP_AND_ARCHIVE` not set correctly | Ensure env var is `1/true/yes` BEFORE starting agent process. |
| JD not archived but JSONs deleted | JD copy logic edge case | Confirm original JD still existed; ensure you didn't start with only `job_description.txt`. |
| Agent returns only links (no scores) | `test_mode_score=True` or scoring error | Check scorer logs & ensure JD file present. |

Logging: watch the terminal running each service for stack traces and debug messages (search/extract scaffolding uses `_log`) when setting iDEBBUGING=True inside the `Full system\linkedin_api\server.py` file.
- If your issue isn’t listed here, please [raise an issue](../../issues) on this repository with full logs and context.


---

## 8. Extensibility Ideas (Optional)
* Add caching layer for already extracted profiles.
* Replace raw Selenium selectors with resilient XPath + heuristics.
* Add CI test harness mocking LinkedIn HTML snapshots.
* Provide Dockerfiles per service for reproducible deployment.
---

## 9. Quick Start (TL;DR)
```powershell
# 1. Create 2 envs (server + agent) & install deps (see section 2.3)
# 2. Set .env with LinkedIn credentials & CHROMEDRIVER_PATH
# 3. Terminal 1 (LinkedIn service)
./venv_server/Scripts/Activate.ps1; uvicorn "Full system.linkedin_api.server:app" --port 8000 --reload
# 4. Terminal 2 (Scorer service)
./venv_server/Scripts/Activate.ps1; uvicorn "Full system.candidate_scorer.server:app" --port 8001 --reload
# 5. Terminal 3 (Agent UI)
./venv_agent/Scripts/Activate.ps1; streamlit run ollama_recruiter/streamlit_app.py
# 6. Interact via UI; watch tmp_candids_jsons fill with JSON; scores appear.
```

Happy recruiting!

