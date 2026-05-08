"""
debug_post_login.py
VTU Internship Diary - Post-login DOM diagnostic
------------------------------------------------
Run this, complete the manual CAPTCHA/OTP when the browser pauses,
then let it capture the full post-login state.

Output files (written next to this script):
  debug_screenshot.png   - full-page screenshot
  debug_page_source.html - raw page HTML
  debug_report.txt       - structured DOM report
"""

import json
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import JavascriptException
from selenium.webdriver.common.by import By

# -- Config -------------------------------------------------------------------
LOGIN_URL = "https://vtu.internyet.in/"
DIARY_URL = "https://vtu.internyet.in/dashboard/student/student-diary"
MANUAL_WAIT = 90
POST_LOGIN_SETTLE = 6
OUT_DIR = Path(__file__).parent

# -- Driver setup --------------------------------------------------------------
options = webdriver.ChromeOptions()
options.add_argument("--start-maximized")
options.add_argument("--disable-blink-features=AutomationControlled")
options.add_experimental_option("excludeSwitches", ["enable-automation"])

driver = webdriver.Chrome(options=options)
driver.implicitly_wait(0)


# -- Helpers ------------------------------------------------------------------
def js(script, *args):
    try:
        return driver.execute_script(script, *args)
    except JavascriptException as exc:
        return f"[JS ERROR] {exc}"


def safe_attr(el, attr):
    try:
        return el.get_attribute(attr) or ""
    except Exception:
        return ""


def safe_text(el):
    try:
        return el.text or ""
    except Exception:
        return ""


def dump_element(el, depth=0):
    indent = "  " * depth
    tag = el.tag_name
    attrs = {k: v for k, v in el.__dict__.items() if k.startswith('_') and not k.startswith('__')}
    attrs_str = " ".join(f'{k[1:]}="{v}"' for k, v in attrs.items() if v)
    text = safe_text(el).strip()
    if text:
        text = f" TEXT={text!r}"
    return f"{indent}<{tag} {attrs_str}>{text}"


# -- Main ---------------------------------------------------------------------
try:
    print(f"[Login] Opening: {LOGIN_URL}")
    driver.get(LOGIN_URL)
    print(f"  >>> Complete CAPTCHA/OTP within {MANUAL_WAIT}s <<<")
    time.sleep(MANUAL_WAIT)

    print(f"[Nav] Going to diary: {DIARY_URL}")
    driver.get(DIARY_URL)
    print(f"  Settling for {POST_LOGIN_SETTLE}s ...")
    time.sleep(POST_LOGIN_SETTLE)

    # -- Screenshot -----------------------------------------------------------
    driver.save_screenshot(OUT_DIR / "debug_screenshot.png")
    print("  Saved: debug_screenshot.png")

    # -- Page source ---------------------------------------------------------
    with open(OUT_DIR / "debug_page_source.html", "w", encoding="utf-8") as f:
        f.write(driver.page_source)
    print("  Saved: debug_page_source.html")

    # -- Structured report ---------------------------------------------------
    report = []
    report.append("=== PAGE TITLE ===")
    report.append(driver.title)
    report.append("")

    report.append("=== URL ===")
    report.append(driver.current_url)
    report.append("")

    report.append("=== ALL BUTTONS ===")
    buttons = driver.find_elements(By.TAG_NAME, "button")
    for i, btn in enumerate(buttons):
        report.append(f"Button {i}: {dump_element(btn)}")
    report.append("")

    report.append("=== ALL SELECTS ===")
    selects = driver.find_elements(By.TAG_NAME, "select")
    for i, sel in enumerate(selects):
        report.append(f"Select {i}: {dump_element(sel)}")
    report.append("")

    report.append("=== ALL INPUTS ===")
    inputs = driver.find_elements(By.TAG_NAME, "input")
    for i, inp in enumerate(inputs):
        report.append(f"Input {i}: {dump_element(inp)}")
    report.append("")

    report.append("=== ALL TEXTAREAS ===")
    textareas = driver.find_elements(By.TAG_NAME, "textarea")
    for i, ta in enumerate(textareas):
        report.append(f"Textarea {i}: {dump_element(ta)}")
    report.append("")

    # -- Save report ---------------------------------------------------------
    with open(OUT_DIR / "debug_report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    print("  Saved: debug_report.txt")

    print("\n[Done] Files saved. Press ENTER to close browser.")
    input()

finally:
    driver.quit()</content>
<parameter name="filePath">d:\Resources\Code\Projects\diary-automator\debug_post_login.py