from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
import os
from dotenv import load_dotenv
import time
import asyncio

load_dotenv()

# toggle this at the top of the file to enable/disable debug prints
# Set to True to enable prints: iDEBBUGING = True
# Default is False to avoid noisy output in production
iDEBBUGING = False

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

app = FastAPI(title="LinkedIn Search API")

class SearchResponse(BaseModel):
    query: str
    num_candidates: int
    links: list[str]
    count: int

def _create_driver(chromedriver_path: str):
    _log(f"Creating Chrome driver using chromedriver at: {chromedriver_path}")
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    # chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-infobars")
    service = Service(executable_path=chromedriver_path)
    return webdriver.Chrome(service=service, options=chrome_options)

def _run_search_sync(query: str, num_candidates: int):
    LK_USERNAME = os.getenv("LK_USERNAME")
    LK_PASSWORD = os.getenv("LK_PASSWORD")
    CHROMEDRIVER = os.getenv(
        "CHROMEDRIVER_PATH",
        r"C:/YoussefENSI_backup/Eukliadia-test/chromedriver.exe"
    )

    _log(f"Starting search: query='{query}' num_candidates={num_candidates}")
    if not LK_USERNAME or not LK_PASSWORD:
        _log("LinkedIn credentials not found in environment (LK_USERNAME/LK_PASSWORD). Aborting search.")
        raise RuntimeError("LinkedIn credentials not found in environment (LK_USERNAME/LK_PASSWORD).")

    _log("LinkedIn credentials present. Creating webdriver and logging in...")
    driver = _create_driver(CHROMEDRIVER)
    try:
        try:
            _log("Navigating to LinkedIn login page")
            driver.get("https://www.linkedin.com/login")
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "username")))
            _log("Filling username and password fields")
            driver.find_element(By.ID, "username").send_keys(LK_USERNAME)
            driver.find_element(By.ID, "password").send_keys(LK_PASSWORD)
            driver.find_element(By.XPATH, '//*[@type="submit"]').click()
            _log("Submitted login form, waiting a moment for authentication")
            time.sleep(2)
            _log("Calling linkedin_query_search() to apply the query")
            linkedin_query_search(driver, query)
            _log("Collecting candidate links")
            links = get_candidates_links(driver, num_candidates=int(num_candidates) if num_candidates else 5)
            _log(f"Search finished, found {len(links)} links")
            return links
        except Exception as e:
            _log(f"Error during search run: {e}")
            raise
    finally:
        _log("Shutting down webdriver for search")
        try:
            driver.quit()
            _log("Webdriver quit successfully")
        except Exception as e:
            _log(f"Exception when quitting webdriver: {e}")


def _run_extract_sync(profile_url: str):
    """Create a driver, log into LinkedIn and extract profile content.

    This mirrors the search runner: it requires LK_USERNAME/LK_PASSWORD to be
    present in the environment because the extractor accesses protected pages
    (languages/skills/details).
    """
    LK_USERNAME = os.getenv("LK_USERNAME")
    LK_PASSWORD = os.getenv("LK_PASSWORD")
    CHROMEDRIVER = os.getenv(
        "CHROMEDRIVER_PATH",
        r"C:/YoussefENSI_backup/Eukliadia-test/chromedriver.exe"
    )

    _log(f"Starting extraction for profile: {profile_url}")
    if not LK_USERNAME or not LK_PASSWORD:
        _log("LinkedIn credentials not found in environment (LK_USERNAME/LK_PASSWORD). Aborting extract.")
        raise RuntimeError("LinkedIn credentials not found in environment (LK_USERNAME/LK_PASSWORD).")

    _log("Creating webdriver and logging into LinkedIn for extraction...")
    driver = _create_driver(CHROMEDRIVER)
    try:
        try:
            _log("Navigating to LinkedIn login page for extraction")
            driver.get("https://www.linkedin.com/login")
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "username")))
            _log("Filling username and password fields (hidden)")
            driver.find_element(By.ID, "username").send_keys(LK_USERNAME)
            driver.find_element(By.ID, "password").send_keys(LK_PASSWORD)
            driver.find_element(By.XPATH, '//*[@type="submit"]').click()
            time.sleep(2)
            _log("Calling candidate_info_extractor() to fetch profile data")
            data = candidate_info_extractor(profile_url, driver)
            _log("Extraction finished successfully")
            return data
        except Exception as e:
            _log(f"Error during extraction run: {e}")
            raise
    finally:
        _log("Shutting down webdriver for extraction")
        try:
            driver.quit()
            _log("Webdriver quit successfully")
        except Exception as e:
            _log(f"Exception when quitting webdriver: {e}")

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

# (NewBasePy312) PS C:\YoussefENSI_backup\Eukliadia-test> uvicorn linkedin_api.server:app --reload --host 127.0.0.1 --port 8000