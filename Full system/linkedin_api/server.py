from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
import os
from dotenv import load_dotenv
import time
import asyncio

load_dotenv()

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
    chrome_options = Options()
    # chrome_options.add_argument("--headless=new")
    # chrome_options.add_argument("--disable-dev-shm-usage")
    # chrome_options.add_argument("--disable-gpu")
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

    if not LK_USERNAME or not LK_PASSWORD:
        raise RuntimeError("LinkedIn credentials not found in environment (LK_USERNAME/LK_PASSWORD).")

    driver = _create_driver(CHROMEDRIVER)
    try:
        driver.get("https://www.linkedin.com/login")
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "username")))
        driver.find_element(By.ID, "username").send_keys(LK_USERNAME)
        driver.find_element(By.ID, "password").send_keys(LK_PASSWORD)
        driver.find_element(By.XPATH, '//*[@type="submit"]').click()
        time.sleep(2)
        linkedin_query_search(driver, query)
        links = get_candidates_links(driver, num_candidates=int(num_candidates) if num_candidates else 5)
        return links
    finally:
        try:
            driver.quit()
        except Exception:
            pass


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

    if not LK_USERNAME or not LK_PASSWORD:
        raise RuntimeError("LinkedIn credentials not found in environment (LK_USERNAME/LK_PASSWORD).")

    driver = _create_driver(CHROMEDRIVER)
    try:
        driver.get("https://www.linkedin.com/login")
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "username")))
        driver.find_element(By.ID, "username").send_keys(LK_USERNAME)
        driver.find_element(By.ID, "password").send_keys(LK_PASSWORD)
        driver.find_element(By.XPATH, '//*[@type="submit"]').click()
        time.sleep(2)
        # call the content extractor which expects an authenticated driver
        data = candidate_info_extractor(profile_url, driver)
        return data
    finally:
        try:
            driver.quit()
        except Exception:
            pass

@app.get("/search", response_model=SearchResponse)
async def search(query: str = Query(..., min_length=1), num_candidates: int = Query(5, ge=1, le=50)):
    try:
        links = await asyncio.to_thread(_run_search_sync, query, num_candidates)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return SearchResponse(query=query, num_candidates=num_candidates, links=links, count=len(links))


class ExtractResponse(BaseModel):
    url: str
    result: dict


@app.get("/extract", response_model=ExtractResponse)
async def extract(url: str = Query(..., min_length=5)):
    try:
        result = await asyncio.to_thread(_run_extract_sync, url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return ExtractResponse(url=url, result=result)

# (NewBasePy312) PS C:\YoussefENSI_backup\Eukliadia-test> uvicorn linkedin_api.server:app --reload --host 127.0.0.1 --port 8000