"""Content extraction utilities for LinkedIn candidate profiles.

This module contains parsing functions and a high-level
`candidate_info_extractor` that navigates a Selenium driver to profile
pages and extracts experience, education, languages and skills.
"""
from typing import List, Tuple, Dict, Any
import time
import re
import bs4
import pandas as pd
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import os

# Set the environment variable to disable oneDNN optimizations

os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
LI_EXPERIENCE_CLASS = 'artdeco-list__item jTfcWeJMTJjmAwkRftDKyvwEfLAgiPsJkfKmpCs JpMDaMQAlbPCzsmZRGDJEOIkAymZoVQbneU'

def text_of(sel: bs4.element.Tag | None) -> str | None:
    return sel.get_text(strip=True) if sel else None


def dedupe_caption(el: bs4.element.Tag) -> str:
    # defensive: some callers pass a selector result which can be None when the
    # element is missing on the profile page. Guard and return None in that
    # case so callers can handle missing captions.
    if el is None:
        return None

    parts = [t.strip() for t in el.find_all(string=True)]
    parts = [p for p in parts if p]
    comp: list[str] = []
    for p in parts:
        if not comp or comp[-1] != p:
            comp.append(p)
    text = " ".join(comp).strip()
    m = re.match(r"^(.+?)\1+$", text)
    if m:
        return m.group(1)
    return text


def text_of(sel):
    return sel.get_text(strip=True) if sel else None
def parse_experience_entries(experience_entries):
    rows = []
    for e in experience_entries:
        # company link & image
        # a_company = e.select_one("a.optional-action-target-wrapper")
        # company_url = a_company["href"] if a_company and a_company.has_attr("href") else None
        # img = e.select_one("img")
        # image_url = img["src"] if img and img.has_attr("src") else None

        # role (bold)
        role = dedupe_caption(e.select_one(".t-bold"))  # e.g. "Intern" or "HR Manager"

        # company + employment type (first t-14 t-normal span)
        comp_and_type = dedupe_caption(e.select_one("span.t-14.t-normal"))
        company = None
        employment_type = None
        if comp_and_type and "·" in comp_and_type:
            # comp_and_type may be None; guard before split
            parts = [s.strip() for s in comp_and_type.split("·", 1)] if comp_and_type else []
            if parts:
                company = parts[0]
                employment_type = parts[1] if len(parts) > 1 else None

        # dates / duration
        dates = text_of(e.select_one("span.pvs-entity__caption-wrapper"))
        # location is often another t-14.t-normal.t-black--light span (take the last one)
        black_spans = e.select("span.t-14.t-normal.t-black--light")
        location = dedupe_caption(black_spans[-1]) if black_spans else None

        # description (inline-show-more-text)
        desc = text_of(e.select_one("div.inline-show-more-text--is-collapsed"))

        # # skills (strong inside the subcomponents)
        # skills = text_of(e.select_one("strong"))

        rows.append({
            "role": role,
            "company": company,
            # "company_url": company_url,
            "employment_type": employment_type,
            # "start_end": dates,
            "duration": None if not dates else (dates.split("·")[-1].strip() if "·" in dates else None),
            "location": location,
            "description": desc,
            # "skills": skills,
            # "image_url": image_url
        })
    return rows


def parse_education(education_section: bs4.element.Tag) -> Tuple[List[Dict[str, Any]], pd.DataFrame]:
    entries = education_section.find_all('div', {'data-view-name': 'profile-component-entity'})
    rows: list[dict] = []
    for e in entries:
        a = e.select_one('a.optional-action-target-wrapper')
        institution_url = a['href'] if a and a.has_attr('href') else None
        img = e.select_one('img')
        image_url = img['src'] if img and img.has_attr('src') else None
        institution = dedupe_caption(e.select_one('.t-bold')) or dedupe_caption(a)
        field_of_study = dedupe_caption(e.select_one('span.t-14.t-normal'))
        dates = dedupe_caption(e.select_one('span.pvs-entity__caption-wrapper'))
        duration = None

        grade_desc = dedupe_caption(e.select_one('div.inline-show-more-text--is-collapsed'))
        grade = None
        if grade_desc and 'Grade:' in grade_desc:
            # capture everything after 'Grade:'
            grade = grade_desc.split('Grade:', 1)[1].strip()
        description = dedupe_caption(e.select_one('div.display-flex full-width'))

        rows.append({
            'institution': institution,
            'institution_url': institution_url,
            'image_url': image_url,
            'field_of_study': field_of_study,
            'start_end': dates,
            'duration': duration,
            'grade': grade,
            'description': description
        })

    return rows


def parse_languages(languages_section: bs4.element.Tag) -> Tuple[List[Dict[str, Any]], pd.DataFrame, str | None]:
    lang_mapper = {
    "elementary proficiency": 0,
    "limited working proficiency": 1,
    "professional working proficiency": 1,
    "full professional proficiency": 2,
    "native or bilingual proficiency": 2
    }
    def text_of(sel):
        return sel.get_text(strip=True) if sel else None


    # per-language entries (best paired by the profile-component-entity container)
    rows = []
    for e in languages_section.find_all('div', {'data-view-name': 'profile-component-entity'}):
        # name = text_of(e.select_one('.t-bold'))
        hidden = text_of(e.select_one('span.visually-hidden'))
        caption = text_of(e.select_one('span.pvs-entity__caption-wrapper'))
        
        # if caption non then not a language 
        if not caption:
            continue
        # caption may be None or not in the mapper; guard lookup
        level = None
        if caption:
            key = caption.lower()
            level = lang_mapper.get(key)
        rows.append({'language': hidden, 'level': level})

    return rows


def parse_skills(src: bs4.element.Tag) -> str:
    skills = list(set(dedupe_caption(s) for s in src.find_all('div', class_='display-flex flex-wrap align-items-center full-height')))
    return ' '.join(skills)



def wait_for_element(driver, by, value, timeout=10):
    try:
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )
    except TimeoutException:
        return None

def candidate_info_extractor(candidate_link, driver):
    # Visit main profile page
    driver.get(candidate_link)
    wait_for_element(driver, By.TAG_NAME, "body")  # Wait for general body load
    time.sleep(5)  # additional wait to ensure dynamic content loads

    soup = bs4.BeautifulSoup(driver.page_source, 'lxml')
    sections = soup.find_all('section', {'class': 'artdeco-card pv-profile-card break-words mt2'})

    # ----- Experience -----
    experience_rows = []
    for sec in sections:
        if sec.find('div', {'id': 'experience'}):
            experience_entries = sec.find_all('li', {'class': LI_EXPERIENCE_CLASS})
            experience_rows = parse_experience_entries(experience_entries)
            break  # Stop once found

    # ----- Education -----
    education_rows = []
    for sec in sections:
        if sec.find('div', {'id': 'education'}):
            education_rows= parse_education(sec)
            break

    # ----- Languages -----
    driver.get(candidate_link + '/details/languages/')
    wait_for_element(driver, By.CSS_SELECTOR, 'section.artdeco-card')  # wait for language section

    languages_soup = bs4.BeautifulSoup(driver.page_source, 'lxml')
    languages_rows = parse_languages(languages_soup)

    # ----- Skills -----
    driver.get(candidate_link + '/details/skills/')
    wait_for_element(driver, By.CSS_SELECTOR, 'section.artdeco-card.pb3')  # wait for skills section

    skills_soup = bs4.BeautifulSoup(driver.page_source, 'lxml')
    ember_div = skills_soup.find('section', class_='artdeco-card pb3')

    if ember_div:
        skills_row = parse_skills(ember_div)
    else:
        print(f"[WARN] Couldn't find skills section for {candidate_link}")
        skills_row = parse_skills(skills_soup)

    return {
        'experience': experience_rows,
        'education': education_rows,
        'languages': languages_rows,
        'skills': skills_row
    }
