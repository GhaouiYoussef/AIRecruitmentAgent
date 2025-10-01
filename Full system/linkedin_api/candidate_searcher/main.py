from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time
import pandas as pd
# import functions from the linkedin-api folder
from functions import get_candidates_links, linkedin_query_search

# Set up Chrome options
chrome_options = Options()
# chrome_options.add_argument("--headless")  # Run in headless mode
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--disable-extensions")
chrome_options.add_argument("--disable-infobars")

import os
from dotenv import load_dotenv
load_dotenv()
LK_USERNAME = os.getenv('LK_USERNAME')
LK_PASSWORD = os.getenv('LK_PASSWORD')

print(f"Connecting as {LK_USERNAME}")

# lets try to login to linkedin ----------------------------------------------------
service = Service(executable_path="C:/YoussefENSI_backup/Eukliadia-test/chromedriver.exe")  # Adjust path as needed
# Two steps verification should be disabled for this to work    
driver = webdriver.Chrome(service=service, options=chrome_options,)
driver.get('https://www.linkedin.com/login?fromSignIn=true&trk=guest_homepage-basic_nav-header-signin')  # Replace with the target URL
    # Wait until the element is present
element = WebDriverWait(driver, 10).until(
    EC.presence_of_element_located((By.ID, "username"))
)
print("Page is ready!") 
username = driver.find_element(By.ID, "username")
password = driver.find_element(By.ID, "password")

username.send_keys(LK_USERNAME)
password.send_keys(LK_PASSWORD)

login_button = driver.find_element(By.XPATH, '//*[@type="submit"]')
login_button.click()

time.sleep(5)  # wait for 5 seconds to ensure the page loads
print("Login successful!")


# ----------------------------------------------------------------------------------
# Example usage of the functions
# linkedin_query_search("data scientist")  # Example query
TEST_LIST = ['https://www.linkedin.com/in/saber-chadded-36552b192/', 'https://www.linkedin.com/in/guesmi-wejden-5269222aa/', 'https://www.linkedin.com/in/hichem-dridi/', 'https://www.linkedin.com/in/nour-hamdi/', 'https://www.linkedin.com/in/iyadh-chaouch-072077225/', 'https://www.linkedin.com/in/emna-rajhi/', 'https://www.linkedin.com/in/ons-chawach-4bb966295/', 'https://www.linkedin.com/in/montassar-belaazi-422292240/', 'https://www.linkedin.com/in/rima-essaidi/', 'https://www.linkedin.com/in/racha-bahri-543703224/']
['https://www.linkedin.com/in/haykel-hammami/', 'https://www.linkedin.com/in/hasna-elayeb-46ab92257/', 'https://www.linkedin.com/in/feres-kordani-932a0a240/', 'https://www.linkedin.com/in/dridi-oumaima-a61346218/', 'https://www.linkedin.com/in/ilyes-marghli-78a4b8181/', 'https://www.linkedin.com/in/ahmed-marnissi-205801335/', 'https://www.linkedin.com/in/wassim-bouras-82aa7821b/', 'https://www.linkedin.com/in/syrine-laabidi/', 'https://www.linkedin.com/in/kalil-dimassi/', 'https://www.linkedin.com/in/wafa-mhemdi-8ab417198/', 'https://www.linkedin.com/in/oumaima-kouki-41073a248/', 'https://www.linkedin.com/in/mahmoud-touil-b01b9b244/', 'https://www.linkedin.com/in/lina-ounaies/', 'https://www.linkedin.com/in/nader-ben-rejeb-690134226/', 'https://www.linkedin.com/in/hamza-benhamza-58494b18a/', 'https://www.linkedin.com/in/karim-fares-1a8b10149/', 'https://www.linkedin.com/in/imen-ben-boubaker-544448232/', 'https://www.linkedin.com/in/meriem-guesmi-m1995/', 'https://www.linkedin.com/in/youssef-frigui/', 'https://www.linkedin.com/in/jihene-ben-kilani-34a81a234/', 'https://www.linkedin.com/in/mahdi-belghith-942410111/', 'https://www.linkedin.com/in/med-aziz-ben-amara-156b87263/en/', 'https://www.linkedin.com/in/becem-ala-din-rezgui-ab903322a/', 'https://www.linkedin.com/in/kawther-belgacem-563a4818a/', 'https://www.linkedin.com/in/sheima-khlifa/', 'https://www.linkedin.com/in/yasmina-ouledali1/', 'https://www.linkedin.com/in/bilel-zidi-army-officer/', 'https://www.linkedin.com/in/oueslati-fouad/', 'https://www.linkedin.com/in/islem-farhan-463355275/', 'https://www.linkedin.com/in/oumaima-hmaidi-1bb64a238/', 'https://www.linkedin.com/in/saber-chadded-36552b192/', 'https://www.linkedin.com/in/guesmi-wejden-5269222aa/', 'https://www.linkedin.com/in/hichem-dridi/', 'https://www.linkedin.com/in/nour-hamdi/', 'https://www.linkedin.com/in/iyadh-chaouch-072077225/', 'https://www.linkedin.com/in/emna-rajhi/', 'https://www.linkedin.com/in/ons-chawach-4bb966295/', 'https://www.linkedin.com/in/montassar-belaazi-422292240/', 'https://www.linkedin.com/in/rima-essaidi/', 'https://www.linkedin.com/in/racha-bahri-543703224/']

if __name__ == "__main__":
    # lets give user to prove an input

    query = input("Enter LinkedIn search query: ")
    # query = "data scientist"
    num_candidates = input("Enter number of candidates to fetch (default 5): ")
    linkedin_query_search(driver, query)  # Example query
    links = get_candidates_links(driver, num_candidates=int(num_candidates) if num_candidates else 5)
    print(links)
    print(f"Number of links: {len(links)}")
    driver.quit()  # Close the browser when done

# this function is ran by using terminal command python linkedin-api/main.py "data scientist"
