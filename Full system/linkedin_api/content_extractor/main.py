"""CLI entry for the content_extractor package.

This script creates a Selenium Chrome driver (uses CHROMEDRIVER_PATH env or
workspace chromedriver.exe), logs into LinkedIn if credentials are provided
via env vars, and runs the extractor on a single profile URL.
"""
import os
import time
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from functions import candidate_info_extractor


def start_driver(chrome_driver_path: str | None = None, headless: bool = False):
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-infobars")

    if not chrome_driver_path:
        chrome_driver_path = os.path.join(os.getcwd(), "chromedriver.exe")
    service = Service(chrome_driver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver


def main():
    load_dotenv()
    CHROMEDRIVER_PATH = os.getenv('CHROMEDRIVER_PATH')
    PROFILE_URL = os.getenv('PROFILE_URL')
    HEADLESS = os.getenv('HEADLESS', '0') == '1'

    if not PROFILE_URL:
        print("Set PROFILE_URL in env to a LinkedIn profile URL (e.g. https://www.linkedin.com/in/someone/)")
        return

    driver = start_driver(CHROMEDRIVER_PATH, headless=HEADLESS)
    try:
        # NOTE: the caller must ensure the driver is authenticated; this script
        # does not perform login by default to avoid storing credentials here.
        result = candidate_info_extractor(PROFILE_URL, driver)
        print(result)
    finally:
        time.sleep(1)
        driver.quit()


if __name__ == '__main__':
    main()
