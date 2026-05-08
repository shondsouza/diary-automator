"""
main.py - VTU Internship Diary Automator
=========================================
Fixes applied based on debug_step_report.txt:

  BUG 1 - Internship combobox: shadcn <button role=combobox> opens a Radix
           portal; options land in [data-radix-popper-content-wrapper] div,
           NOT inside the button's subtree. Fixed: wait for portal options.

  BUG 2 - Date picker: was clicking day "10" in the CURRENT calendar month
           (May 2026) instead of the CSV target month/year. Fixed: navigate
           months until aria-label on the grid matches target month+year,
           then click the correct day. Then press Escape to close the popup
           so React commits the value.

  BUG 3 - Gated fields: Work Summary / all other textareas only render AFTER
           both internship and date are committed and the date dialog is closed.
           Fixed: wait for textarea[@name='description'] only after the calendar
           dialog disappears from DOM.
"""

import re
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import (
    JavascriptException,
    NoSuchElementException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

# -- Config -------------------------------------------------------------------
DIARY_URL = "https://vtu.internyet.in/dashboard/student/student-diary"
LOGIN_URL = "https://vtu.internyet.in/"
CSV_PATH = Path("data.csv")
MANUAL_WAIT = 90
FIELD_WAIT = 20
SKIP_SUNDAY = True
TEST_MODE = True

# -- Column aliases (maps CSV headers -> internal keys) -----------------------
COL_ALIASES = {
    "date": ["date", "Date", "DATE", "diary_date"],
    "work_summary": ["work_summary", "Work Summary", "description", "Description", "summary"],
    "hours": ["hours", "Hours", "hours_worked", "Hours Worked"],
    "links": ["links", "Links", "reference_links", "Reference Links"],
    "learnings": ["learnings", "Learnings", "Learnings/Outcomes", "outcomes"],
    "blockers": ["blockers", "Blockers", "blocker"],
    "skills": ["skills", "Skills", "Tech Stack", "tech_stack", "Tag"],
}


def make_driver():
    opts = webdriver.ChromeOptions()
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    d = webdriver.Chrome(options=opts)
    d.implicitly_wait(0)
    return d


def js(driver, script, *args):
    try:
        return driver.execute_script(script, *args)
    except JavascriptException as e:
        print(f"  [JS ERROR] {e}")
        return None


def attr(el, a):
    try:
        return el.get_attribute(a) or ""
    except Exception:
        return ""


def wait_visible(driver, by, loc, timeout=15, label="element"):
    try:
        return WebDriverWait(driver, timeout).until(EC.visibility_of_element_located((by, loc)))
    except TimeoutException:
        raise TimeoutException(f"Timed out waiting for visible: {label} [{loc}]")


def wait_gone(driver, by, loc, timeout=10):
    try:
        WebDriverWait(driver, timeout).until_not(EC.visibility_of_element_located((by, loc)))
    except TimeoutException:
        pass


def find_col(df, key):
    for alias in COL_ALIASES.get(key, [key]):
        if alias in df.columns:
            return alias
    return None


def safe_str(val):
    if pd.isna(val):
        return ""
    return str(val).strip()


def load_csv(path):
    df = pd.read_csv(path)
    print(f"[CSV] Loaded {len(df)} rows. Columns: {list(df.columns)}")

    col_map = {}
    for key in COL_ALIASES:
        col = find_col(df, key)
        if col:
            col_map[key] = col
            print(f"  + {key!r} -> column {col!r}")
        else:
            print(f"  x {key!r} -> NOT FOUND (will use empty string)")
    return df, col_map


def select_internship(driver):
    print("  [Internship] Locating combobox ...")
    btn = wait_visible(
        driver,
        By.XPATH,
        "//button[@id='internship_id' and @role='combobox']",
        timeout=10,
        label="internship combobox button",
    )
    js(driver, "arguments[0].scrollIntoView({block:'center'})", btn)
    time.sleep(0.3)

    current_text = btn.text.strip()
    if current_text and current_text.lower() != "choose internship":
        print(f"  [Internship] Already selected: {current_text!r} - skipping")
        return

    js(driver, "arguments[0].click()", btn)
    print("  [Internship] Clicked combobox, waiting for Radix portal options ...")
    time.sleep(0.8)

    try:
        options = WebDriverWait(driver, 8).until(
            lambda d: [
                el for el in d.find_elements(By.XPATH, "//*[@role='option']") if el.is_displayed()
            ]
            or None
        )
    except TimeoutException:
        raise TimeoutException(
            "Internship dropdown options never appeared. Check if your account has internships assigned."
        )

    print(f"  [Internship] {len(options)} options found:")
    for o in options:
        print(f"    {o.text.strip()!r}")

    js(driver, "arguments[0].click()", options[0])
    print(f"  [Internship] Selected: {options[0].text.strip()!r}")
    time.sleep(0.5)

    try:
        WebDriverWait(driver, 5).until(
            lambda d: d.find_element(By.XPATH, "//button[@id='internship_id']").text.strip().lower()
            != "choose internship"
        )
        confirmed = driver.find_element(By.XPATH, "//button[@id='internship_id']").text.strip()
        print(f"  [Internship] Confirmed selection: {confirmed!r}")
    except TimeoutException:
        print("  [Internship] Warning: combobox text did not update (continuing)")


def set_date(driver, date_str):
    target = datetime.strptime(date_str, "%Y-%m-%d")
    target_month_label = target.strftime("%B %Y")
    target_day_label = str(target.day)

    print(
        f"  [Date] Targeting: {date_str} -> month='{target_month_label}' day='{target_day_label}'"
    )

    pick_btn = wait_visible(
        driver, By.XPATH, "//button[@aria-haspopup='dialog']", timeout=10, label="'Pick a Date' button"
    )
    js(driver, "arguments[0].scrollIntoView({block:'center'})", pick_btn)
    js(driver, "arguments[0].click()", pick_btn)
    time.sleep(1.0)

    wait_visible(driver, By.XPATH, "//*[@role='dialog']", timeout=8, label="date picker dialog")

    for _ in range(24):
        try:
            grid = driver.find_element(By.XPATH, "//*[@role='grid']")
            grid_label = attr(grid, "aria-label")
        except NoSuchElementException:
            time.sleep(0.5)
            continue

        print(f"  [Date] Calendar showing: {grid_label!r} (want {target_month_label!r})")
        if grid_label == target_month_label:
            break

        try:
            shown = datetime.strptime(grid_label, "%B %Y")
        except ValueError:
            print(f"  [Date] Unexpected grid label format: {grid_label!r}")
            break

        if shown > target:
            nav_btn = driver.find_element(By.XPATH, "//button[@aria-label='Go to the Previous Month']")
        else:
            nav_btn = driver.find_element(By.XPATH, "//button[@aria-label='Go to the Next Month']")
        js(driver, "arguments[0].click()", nav_btn)
        time.sleep(0.5)
    else:
        raise TimeoutException(f"Could not navigate calendar to {target_month_label} in 24 steps")

    day_xpath = (
        f"//button[@aria-haspopup='dialog']/following::*[@role='dialog']//*[@role='grid']"
        f"//button[normalize-space(.)='{target_day_label}' and not(@disabled) and not(@aria-disabled='true')]"
    )
    day_xpath_simple = (
        f"//button[normalize-space(.)='{target_day_label}' and @aria-label and not(@disabled) and not(@aria-disabled='true')]"
    )

    day_el = None
    for xp in [day_xpath, day_xpath_simple]:
        candidates = driver.find_elements(By.XPATH, xp)
        vis = [c for c in candidates if c.is_displayed()]
        if vis:
            month_abbr = target.strftime("%B")
            for c in vis:
                if month_abbr in attr(c, "aria-label"):
                    day_el = c
                    break
            if not day_el:
                day_el = vis[0]
            break

    if not day_el:
        raise NoSuchElementException(
            f"Day button '{target_day_label}' not found in calendar for {target_month_label}"
        )

    print(f"  [Date] Clicking day: {attr(day_el, 'aria-label')!r}")
    js(driver, "arguments[0].click()", day_el)
    time.sleep(0.5)

    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
    time.sleep(0.5)
    wait_gone(driver, By.XPATH, "//*[@role='dialog']", timeout=5)
    print("  [Date] Calendar closed - date committed")

    try:
        pick_btn_text = driver.find_element(By.XPATH, "//button[@aria-haspopup='dialog']").text.strip()
        print(f"  [Date] Picker button now shows: {pick_btn_text!r}")
    except Exception:
        pass


def wait_for_form_fields(driver):
    print(f"  [Form] Waiting up to {FIELD_WAIT}s for form fields to render ...")
    try:
        el = WebDriverWait(driver, FIELD_WAIT).until(
            EC.visibility_of_element_located((By.NAME, "description"))
        )
        print("  [Form] + Work Summary field is visible")
        return el
    except TimeoutException:
        textareas = driver.find_elements(By.TAG_NAME, "textarea")
        print(f"  [Form] x description not found. All textareas in DOM: {len(textareas)}")
        for t in textareas:
            print(
                f"    name={attr(t,'name')!r} id={attr(t,'id')!r} placeholder={attr(t,'placeholder')!r} visible={t.is_displayed()}"
            )
        raise TimeoutException(
            "Work Summary field never appeared. Internship or date may not have been committed correctly."
        )


def fill_textarea(driver, by, loc, value, label):
    if not value:
        print(f"  [Field] {label} - empty, skipping")
        return
    try:
        el = wait_visible(driver, by, loc, timeout=10, label=label)
        el.clear()
        el.send_keys(value)
        print(f"  [Field] {label} - filled ({len(value)} chars)")
    except TimeoutException:
        print(f"  [Field] {label} - NOT FOUND, skipping")


def fill_skills(driver, skills_str):
    if not skills_str:
        return
    skills = [s.strip() for s in re.split(r"[,;|]", skills_str) if s.strip()]
    print(f"  [Skills] Adding: {skills}")

    for skill in skills:
        try:
            inp = wait_visible(
                driver,
                By.XPATH,
                "//*[contains(@id,'react-select') and @role!='combobox'] | //input[contains(@id,'react-select')]",
                timeout=8,
                label=f"react-select input for '{skill}'",
            )
            inp.send_keys(skill)
            time.sleep(0.8)

            option_xpath = f"//*[@id[contains(.,'react-select')]]//*[contains(normalize-space(.),'{skill}')]"
            opts = driver.find_elements(By.XPATH, option_xpath)
            vis = [o for o in opts if o.is_displayed()]
            if vis:
                js(driver, "arguments[0].click()", vis[0])
                print(f"    + Selected skill: {skill!r}")
            else:
                inp.send_keys(Keys.ENTER)
                print(f"    ~ Pressed Enter for skill: {skill!r}")
            time.sleep(0.4)
        except TimeoutException:
            print(f"    x Skills input not found for: {skill!r}")


def fill_hours(driver, hours_val):
    if not hours_val:
        return
    try:
        el = wait_visible(driver, By.XPATH, "//input[@type='number']", timeout=8, label="hours input")
        el.clear()
        el.send_keys(str(hours_val))
        print(f"  [Hours] Filled: {hours_val}")
    except TimeoutException:
        print("  [Hours] Field not found, skipping")


def submit_form(driver):
    try:
        btn = wait_visible(
            driver,
            By.XPATH,
            "//button[@type='submit' and contains(normalize-space(.),'Save')]",
            timeout=10,
            label="Save button",
        )
        js(driver, "arguments[0].scrollIntoView({block:'center'})", btn)
        js(driver, "arguments[0].click()", btn)
        print("  [Submit] Clicked Save")
    except TimeoutException:
        btns = [b for b in driver.find_elements(By.XPATH, "//button[@type='submit']") if b.is_displayed()]
        if btns:
            js(driver, "arguments[0].click()", btns[0])
            print(f"  [Submit] Fallback click: {btns[0].text.strip()!r}")
        else:
            print("  [Submit] x No submit button found")
            return

    try:
        WebDriverWait(driver, 10).until(
            lambda d: (
                any(kw in d.page_source.lower() for kw in ["success", "saved", "created", "diary entry"])
                or d.find_elements(
                    By.XPATH,
                    "//*[contains(@class,'toast') or contains(@role,'alert')]"
                    "[contains(normalize-space(.),'success') or contains(normalize-space(.),'saved')]",
                )
            )
        )
        print("  [Submit] + Success signal detected")
    except TimeoutException:
        print("  [Submit] Warning: no success toast detected (entry may still have saved)")


def fill_single_entry(driver, row, col_map):
    date_str = safe_str(row.get(col_map.get("date", ""), ""))
    work_summary = safe_str(row.get(col_map.get("work_summary", ""), ""))
    hours = safe_str(row.get(col_map.get("hours", ""), ""))
    links = safe_str(row.get(col_map.get("links", ""), ""))
    learnings = safe_str(row.get(col_map.get("learnings", ""), ""))
    blockers = safe_str(row.get(col_map.get("blockers", ""), ""))
    skills = safe_str(row.get(col_map.get("skills", ""), ""))

    if not date_str:
        print("  [Skip] No date in row")
        return

    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"]:
        try:
            parsed_date = datetime.strptime(date_str, fmt)
            date_iso = parsed_date.strftime("%Y-%m-%d")
            break
        except ValueError:
            continue
    else:
        print(f"  [Skip] Unparseable date: {date_str!r}")
        return

    if SKIP_SUNDAY and parsed_date.weekday() == 6:
        print(f"  [Skip] Sunday: {date_iso}")
        return

    print(f"\n{'-' * 55}")
    print(f"  Processing: {date_iso}")
    print(f"{'-' * 55}")

    driver.get(DIARY_URL)
    time.sleep(4)

    combobox_check = driver.find_elements(By.XPATH, "//button[@id='internship_id' and @role='combobox']")
    if not [e for e in combobox_check if e.is_displayed()]:
        print("  [Nav] Form not visible - trying Create button ...")
        create_xpaths = [
            "//a[contains(normalize-space(.),'Create')]",
            "//button[contains(normalize-space(.),'Create')]",
            "//*[@data-slot='button'][contains(normalize-space(.),'Create')]",
        ]
        for xp in create_xpaths:
            els = [e for e in driver.find_elements(By.XPATH, xp) if e.is_displayed()]
            if els:
                js(driver, "arguments[0].scrollIntoView({block:'center'})", els[0])
                js(driver, "arguments[0].click()", els[0])
                print(f"  [Nav] Clicked Create: {xp}")
                time.sleep(2)
                break
        else:
            print("  [Nav] Create not found - refreshing and retrying once ...")
            driver.refresh()
            time.sleep(4)

    select_internship(driver)
    time.sleep(1)
    set_date(driver, date_iso)
    time.sleep(1)
    wait_for_form_fields(driver)
    time.sleep(0.5)

    fill_textarea(driver, By.NAME, "description", work_summary, "Work Summary")
    fill_textarea(driver, By.NAME, "links", links, "Reference Links")
    fill_textarea(driver, By.NAME, "learnings", learnings, "Learnings")
    fill_textarea(driver, By.NAME, "blockers", blockers, "Blockers")
    fill_hours(driver, hours)
    fill_skills(driver, skills)

    submit_form(driver)
    time.sleep(2)


def main():
    df, col_map = load_csv(CSV_PATH)

    if TEST_MODE:
        df = df.head(1)
        print("\n[TEST MODE] Processing only first row")

    driver = make_driver()
    try:
        print(f"\n[Login] Opening: {LOGIN_URL}")
        driver.get(LOGIN_URL)
        print(f"  >>> Complete CAPTCHA/OTP within {MANUAL_WAIT}s <<<")
        time.sleep(MANUAL_WAIT)

        for idx, row in df.iterrows():
            print(f"\n[Row {idx + 1}/{len(df)}]")
            try:
                fill_single_entry(driver, row, col_map)
            except TimeoutException as e:
                print(f"  [ERROR] TimeoutException on row {idx + 1}: {e}")
                print("  Skipping to next row ...")
            except Exception as e:
                print(f"  [ERROR] Unexpected error on row {idx + 1}: {e}")
                raise

        print("\n[Done] All rows processed.")
    finally:
        input("\n[Press ENTER to close browser]")
        driver.quit()


if __name__ == "__main__":
    main()
