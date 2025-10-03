from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
import os
from dotenv import load_dotenv
import time
import asyncio
import threading
from contextlib import contextmanager
import os
import glob
from typing import Dict, Optional, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, validator



load_dotenv()

# toggle this at the top of the file to enable/disable debug prints
# Set to True to enable prints: iDEBBUGING = True
# Default is False to avoid noisy output in production
iDEBBUGING = True

# small helper for timestamped debug prints (gated by iDEBBUGING)
def _log(msg: str):
    try:
        if not globals().get('iDEBBUGING'):
            return
    except Exception:
        return
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# reuse your functions (use package-relative import; uvicorn runs this module as `linkedin_api.server`)
from .candidate_searcher.functions import get_candidates_links, linkedin_query_search
from .content_extractor.functions import candidate_info_extractor
from .candidate_scorer.functions import CandidateScorer, DEFAULT_WEIGHTS

app = FastAPI(title="LinkedIn Search API")

class SearchResponse(BaseModel):
    query: str
    num_candidates: int
    links: list[str]
    count: int

def _create_driver(chromedriver_path: str, profile_dir: str | None = None):
    _log(f"Creating Chrome driver using chromedriver at: {chromedriver_path}")
    chrome_options = Options()
    # chrome_options.add_argument("--headless=new")
    # chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-infobars")
    # Persist cookies/session across runs using a dedicated profile directory
    if profile_dir:
        os.makedirs(profile_dir, exist_ok=True)
        chrome_options.add_argument(f"--user-data-dir={profile_dir}")
        chrome_options.add_argument("--profile-directory=Default")
    service = Service(executable_path=chromedriver_path)
    return webdriver.Chrome(service=service, options=chrome_options)


class DriverManager:
    """Manages a single shared Selenium WebDriver instance with login persistence."""

    def __init__(self, chromedriver_path: str, profile_dir: str):
        self.chromedriver_path = chromedriver_path
        self.profile_dir = profile_dir
        self.driver: webdriver.Chrome | None = None
        self._last_login_ts: float | None = None

    def _is_driver_alive(self) -> bool:
        try:
            if self.driver is None:
                return False
            # Accessing current_url will raise if session is dead
            _ = self.driver.current_url
            return True
        except Exception:
            return False

    def _create_or_get_driver(self) -> webdriver.Chrome:
        if not self._is_driver_alive():
            # Close any zombie driver
            try:
                if self.driver is not None:
                    self.driver.quit()
            except Exception:
                pass
            self.driver = _create_driver(self.chromedriver_path, self.profile_dir)
            _log("Created new shared WebDriver instance")
        return self.driver  # type: ignore[return-value]

    def _is_logged_in(self) -> bool:
        drv = self._create_or_get_driver()
        try:
            drv.get("https://www.linkedin.com/feed/")
            WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.ID, "global-nav")))
            return True
        except Exception:
            # If we see the login page or cannot load feed, assume not logged in
            return False

    def ensure_logged_in(self, username: str, password: str, wait_seconds: int = 25) -> webdriver.Chrome:
        drv = self._create_or_get_driver()
        if self._is_logged_in():
            return drv
        _log("Session not authenticated. Performing login once for the shared driver...")
        drv.get("https://www.linkedin.com/login")
        WebDriverWait(drv, 15).until(EC.presence_of_element_located((By.ID, "username")))
        drv.find_element(By.ID, "username").clear()
        drv.find_element(By.ID, "username").send_keys(username)
        drv.find_element(By.ID, "password").clear()
        drv.find_element(By.ID, "password").send_keys(password)
        drv.find_element(By.XPATH, '//*[@type="submit"]').click()
        # Give time for 2FA/manual checks if any; using env override if provided
        try:
            extra_wait = int(os.getenv("LINKEDIN_LOGIN_WAIT_SECONDS", str(wait_seconds)))
        except Exception:
            extra_wait = wait_seconds
        _log(f"Waiting up to {extra_wait}s for login/redirect to complete...")
        # Wait until feed or any authenticated element appears
        try:
            WebDriverWait(drv, extra_wait).until(
                EC.any_of(
                    EC.presence_of_element_located((By.ID, "global-nav")),
                    EC.url_contains("/feed/")
                )
            )
        except Exception:
            # Fall back to a small sleep to let cookies settle
            time.sleep(5)
        if not self._is_logged_in():
            raise RuntimeError("Login attempt did not succeed. Please resolve any 2FA or checkpoint in the opened browser window and try again.")
        self._last_login_ts = time.time()
        _log("Login completed and session is authenticated.")
        return drv

    def ensure_ready(self, username: str, password: str) -> webdriver.Chrome:
        """Ensure driver exists and is logged in; return the driver."""
        return self.ensure_logged_in(username, password)

    def reset_driver(self):
        _log("Resetting shared WebDriver instance...")
        if self.driver is not None:
            try:
                self.driver.quit()
            except Exception:
                pass
        self.driver = None
        self._last_login_ts = None

def _env_creds():
    return (
        os.getenv("LK_USERNAME"),
        os.getenv("LK_PASSWORD"),
        os.getenv("CHROMEDRIVER_PATH", r"C:/YoussefENSI_backup/Eukliadia-test/chromedriver.exe"),
    )


_DRIVER_MANAGER: DriverManager | None = None
_DRIVER_LOCK = threading.Lock()


@contextmanager
def _acquire_driver():
    if _DRIVER_MANAGER is None:
        raise RuntimeError("Driver not initialized yet")
    LK_USERNAME, LK_PASSWORD, _ = _env_creds()
    if not LK_USERNAME or not LK_PASSWORD:
        raise RuntimeError("LinkedIn credentials not found in environment (LK_USERNAME/LK_PASSWORD).")
    with _DRIVER_LOCK:
        driver = _DRIVER_MANAGER.ensure_ready(LK_USERNAME, LK_PASSWORD)
        yield driver


def _run_search_sync(query: str, num_candidates: int):
    _log(f"Starting search: query='{query}' num_candidates={num_candidates}")
    try:
        with _acquire_driver() as driver:
            _log("Calling linkedin_query_search() to apply the query")
            linkedin_query_search(driver, query)
            _log("Collecting candidate links")
            links = get_candidates_links(driver, num_candidates=int(num_candidates) if num_candidates else 5)
            _log(f"Search finished, found {len(links)} links")
            return links
    except Exception as e:
        _log(f"Error during search run: {e}")
        raise


def _run_extract_sync(profile_url: str):
    """Use the shared driver to extract profile content without re-login each time."""
    _log(f"Starting extraction for profile: {profile_url}")
    try:
        with _acquire_driver() as driver:
            _log("Calling candidate_info_extractor() to fetch profile data")
            data = candidate_info_extractor(profile_url, driver)
            _log("Extraction finished successfully")
            return data
    except Exception as e:
        _log(f"Error during extraction run: {e}")
        raise

@app.get("/search", response_model=SearchResponse)
async def search(query: str = Query(..., min_length=1), num_candidates: int = Query(5, ge=1, le=50)):
    _log(f"Received /search request: query='{query}' num_candidates={num_candidates}")
    try:
        links = await asyncio.to_thread(_run_search_sync, query, num_candidates)
    except Exception as e:
        _log(f"/search handler caught exception: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    _log(f"/search returning {len(links)} links")
    return SearchResponse(query=query, num_candidates=num_candidates, links=links, count=len(links))


class ExtractResponse(BaseModel):
    url: str
    result: dict


@app.get("/extract", response_model=ExtractResponse)
async def extract(url: str = Query(..., min_length=5)):
    _log(f"Received /extract request: url='{url}'")
    try:
        result = await asyncio.to_thread(_run_extract_sync, url)
    except Exception as e:
        _log(f"/extract handler caught exception: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    _log(f"/extract returning result for url: {url}")
    return ExtractResponse(url=url, result=result)


@app.on_event("startup")
async def _startup_driver():
    """Initialize the shared Selenium driver and log in once on app startup."""
    global _DRIVER_MANAGER
    LK_USERNAME, LK_PASSWORD, CHROMEDRIVER = _env_creds()
    if not LK_USERNAME or not LK_PASSWORD:
        _log("Warning: LK_USERNAME/LK_PASSWORD not set at startup. Driver will initialize on first request.")
    profile_dir = os.getenv("CHROME_PROFILE_DIR") or os.path.join(os.getcwd(), ".chrome-profile-linkedin")
    _DRIVER_MANAGER = DriverManager(CHROMEDRIVER, profile_dir)
    # Optionally warm up and login (best effort); do not block startup fatally
    try:
        if LK_USERNAME and LK_PASSWORD:
            with _DRIVER_LOCK:
                _DRIVER_MANAGER.ensure_ready(LK_USERNAME, LK_PASSWORD)
    except Exception as e:
        _log(f"Startup driver warm-up failed (will retry on first request): {e}")


@app.on_event("shutdown")
async def _shutdown_driver():
    global _DRIVER_MANAGER
    try:
        if _DRIVER_MANAGER is not None:
            _DRIVER_MANAGER.reset_driver()
    except Exception as e:
        _log(f"Error while shutting down driver: {e}")


@app.get("/driver/status")
async def driver_status():
    """Lightweight status endpoint to verify driver/login state."""
    global _DRIVER_MANAGER
    if _DRIVER_MANAGER is None:
        return {"initialized": False, "logged_in": False}
    try:
        with _DRIVER_LOCK:
            logged_in = _DRIVER_MANAGER._is_logged_in()
        return {"initialized": True, "logged_in": logged_in}
    except Exception:
        return {"initialized": True, "logged_in": False}


@app.post("/driver/restart")
async def restart_driver():
    """Restart the shared driver (useful if session is flagged)."""
    global _DRIVER_MANAGER
    if _DRIVER_MANAGER is None:
        return {"ok": True, "message": "Driver manager not yet initialized; nothing to restart."}
    with _DRIVER_LOCK:
        _DRIVER_MANAGER.reset_driver()
        LK_USERNAME, LK_PASSWORD, _ = _env_creds()
        if LK_USERNAME and LK_PASSWORD:
            try:
                _DRIVER_MANAGER.ensure_ready(LK_USERNAME, LK_PASSWORD)
            except Exception as e:
                return {"ok": False, "message": f"Driver restarted but login failed: {e}"}
    return {"ok": True, "message": "Driver restarted and ready."}

# (NewBasePy312) PS C:\YoussefENSI_backup\Eukliadia-test> uvicorn linkedin_api.server:app --reload --host 127.0.0.1 --port 8000



# ---- Request/Response Models ----
class LoadProfilesRequest(BaseModel):
    json_folder: str = Field(..., description="Folder containing candidate JSON files")
    exp_agg: str = Field("sum_norm", description="Experience aggregation mode: sum | mean | sum_norm")
    reset: bool = Field(True, description="Reset the scorer and re-index from scratch")

    @validator("exp_agg")
    def _check_agg(cls, v: str) -> str:
        allowed = {"sum", "mean", "sum_norm"}
        if v not in allowed:
            raise ValueError(f"exp_agg must be one of {allowed}")
        return v


class ScoreRequest(BaseModel):
    job_text: str = Field(..., description="Job description text")
    weights: Optional[Dict[str, float]] = Field(None, description="Weights for sections")
    top_k_search: int = Field(200, ge=1, le=5000, description="FAISS top_k to search per section")

    @validator("weights")
    def _normalize_weights(cls, v: Optional[Dict[str, float]]) -> Optional[Dict[str, float]]:
        if v is None:
            return None
        # Ensure only known keys are present; ignore extras
        cleaned = {k: float(v[k]) for k in ("experience", "skills", "education", "languages") if k in v}
        if not cleaned:
            return None
        return cleaned


class ScoreItem(BaseModel):
    candidate_id: str
    score: float
    breakdown: Dict[str, float]


class ScoreResponse(BaseModel):
    count: int
    results: List[ScoreItem]


# ---- Global Scorer State ----
SCORER: Optional[CandidateScorer] = None


@app.get("/scorer_tool/health")
def health():
    global SCORER
    status = {
        "status": "ok",
        "indexed_profiles": 0 if SCORER is None else len(SCORER.profiles),
        "exp_agg_mode": None if SCORER is None else SCORER.exp_agg_mode,
    }
    return status


@app.post("/scorer_tool/load_profiles")
def load_profiles(req: LoadProfilesRequest):
    global SCORER

    json_folder = req.json_folder
    if not os.path.isabs(json_folder):
        # Resolve relative to current working directory
        json_folder = os.path.abspath(os.path.join(os.getcwd(), json_folder))

    if not os.path.isdir(json_folder):
        raise HTTPException(status_code=400, detail=f"json_folder not found: {json_folder}")

    files = glob.glob(os.path.join(json_folder, "*.json"))
    if not files:
        raise HTTPException(status_code=400, detail=f"No JSON files found in {json_folder}")

    if req.reset or SCORER is None:
        SCORER = CandidateScorer(exp_agg_mode=req.exp_agg)
    else:
        # If already initialized but exp_agg changes, recreate to avoid confusion
        if SCORER.exp_agg_mode != req.exp_agg:
            SCORER = CandidateScorer(exp_agg_mode=req.exp_agg)

    SCORER.add_profiles(files)
    return {
        "indexed_profiles": len(SCORER.profiles),
        "source": json_folder,
        "files_added": len(files),
        "exp_agg_mode": SCORER.exp_agg_mode,
    }


@app.post("/scorer_tool/score", response_model=ScoreResponse)
def score(req: ScoreRequest):
    global SCORER
    if SCORER is None or len(SCORER.profiles) == 0:
        raise HTTPException(status_code=400, detail="No profiles indexed. Call /load_profiles first.")

    weights = req.weights if req.weights is not None else DEFAULT_WEIGHTS
    try:
        results = SCORER.score(req.job_text, weights=weights, top_k_search=req.top_k_search)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scoring failed: {e}")

    items = [ScoreItem(**r) for r in results]
    return ScoreResponse(count=len(items), results=items)
