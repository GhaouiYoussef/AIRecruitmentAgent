# ----------------------------------------------------------------------------------
from selenium.webdriver.support import expected_conditions as EC
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait




# Coonstant variables
## candidate libnnk scrapping
DIV_section_class = "e4b54b6f"
## pagination buttons
LI_section_class = "c394e924  "
pagination_btn_class = "_15f8b8fa  "
# ----------------------------------------------------------------------------------
def linkedin_query_search(driver, query):
    """Perform a LinkedIn search query with optional filters."""
    # we try using the search bar, if there is an error we fallback to url query
    try:
        search_input = driver.find_element(By.CLASS_NAME, 'search-global-typeahead__input')
        search_input.send_keys(query)
        search_input.send_keys(u'\ue007')

    except Exception as e:
        print(f"Error using search bar: {e}")
        # Fallback to URL query
        base_url = "https://www.linkedin.com/search/results/people/?keywords="
        query = query.replace(" ", "%20")
        url = base_url + query
        driver.get(url)
    time.sleep(5)  # wait for the page to load

    # go to poeple section
    li_list = WebDriverWait(driver, 10).until(
    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li.search-reusables__primary-filter"))
    )

    target_btn = None
    for li in li_list:
        try:
            # find the button inside this li (uses the shorter specific class)
            btn = li.find_element(By.CSS_SELECTOR, "button.search-reusables__filter-pill-button")
            # filter by visible text if you want a specific pill
            if "People" not in li.text: continue
            target_btn = btn
            break
        except Exception:
            continue

    if target_btn is None:
        raise Exception("scrapper didnt find people section, check the div classname")
    else:
        target_btn.click()
        time.sleep(5)  # wait for the page to load
    
 



def pagination_button_store(driver, num_pages=10, LI_section_class=LI_section_class, pagination_btn_class=pagination_btn_class) -> dict:
    pages_buttons = {}
    # check if the class name is correct

    li_list = WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, f"li.{LI_section_class}"))
            )
    target_btn = None

    for li in li_list:
        # find the button inside this li (uses the shorter specific class)
        btn = li.find_element(By.CSS_SELECTOR, f"button.{pagination_btn_class}")
        
        # We check in the li.text is a number and if its in the [2, num_pages+1] then we add it to the dict , and remove from the list [2, num_pages+1]
        if not li.text.isdigit() or int(li.text) not in range(1, num_pages + 1): continue
        target_btn = btn
        pages_buttons[int(li.text)] = target_btn

    if target_btn is None:
        raise Exception("Filter button not found in any li.search-reusables__primary-filter")
    return pages_buttons



def get_candidates_links(driver, num_candidates=10) -> list:
    
    # we create a cleaning function to mkae sure link is of a profile candid.startswith('https://www.linkedin.com/in/')
    def list_links_check(links_list):
        return [link for link in links_list if link.startswith('https://www.linkedin.com/in/')]
    # Calculate the number of pages needed
    NUM_PAGES = (num_candidates // 10) +1
    
    FULL_CANDIDATES_LIST = []
    
    # we start in page 1 then at the end of the loop we click on the next page button
    for page in range(1, NUM_PAGES + 1):

        # --- Pagination buttons
        pages_buttons = pagination_button_store(driver, num_pages=NUM_PAGES) # should be run after each pagination change


        cards = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, f"div.{DIV_section_class}"))
        )

        candidates_links = []
        for card in cards:
            href = None
            try:
                href = card.find_element(By.XPATH, "./ancestor::a[1]").get_attribute("href")
            except Exception:
                try:
                    href = card.find_element(By.CSS_SELECTOR, "a").get_attribute("href")
                except Exception:
                    href = None

            if href:
                candidates_links.append(href)

        candidates_links = list_links_check(list(dict.fromkeys([u for u in candidates_links if u])))
        print("links found:", len(candidates_links), candidates_links)

        FULL_CANDIDATES_LIST.extend(candidates_links)

        if page < NUM_PAGES:  # No need to click next on the last page
            next_page_btn = pages_buttons.get(page + 1)
            if next_page_btn:
                next_page_btn.click()
                time.sleep(5)  # wait for the page to load
            else:
                print(f"No button found for page {page + 1}, stopping.")

                # check if we got enough candidates
                if len(FULL_CANDIDATES_LIST) >= num_candidates:
                    break
                else:
                    print(f"Only {len(FULL_CANDIDATES_LIST)} candidates found, less than requested {num_candidates}.")
    if len(FULL_CANDIDATES_LIST) < num_candidates:
        print(f"Only {len(FULL_CANDIDATES_LIST)} candidates found, less than requested {num_candidates}.")
        return FULL_CANDIDATES_LIST
    return FULL_CANDIDATES_LIST[:num_candidates]   