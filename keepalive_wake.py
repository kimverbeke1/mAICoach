"""
keepalive_wake.py
Opens https://maicoach.streamlit.app/ in headless Chrome (via GitHub Actions)
and clicks the Streamlit "Yes, get this app back up!" button if the app sleeps.
"""
import sys
import time

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

STREAMLIT_URL = "https://maicoach.streamlit.app/"
WAKE_TEXT = "Yes, get this app back up"

WAKE_SELECTORS = [
    (By.XPATH, f"//button[contains(., '{WAKE_TEXT}')]"),
    (By.CSS_SELECTOR, '[data-testid="wakeup-button-viewer"]'),
    (By.CSS_SELECTOR, '[data-testid="wakeup-button-owner"]'),
]


def build_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(options=options)


def find_wake_button(driver):
    for by, selector in WAKE_SELECTORS:
        try:
            return WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((by, selector))
            )
        except TimeoutException:
            continue
    return None


def main():
    print(f"Opening {STREAMLIT_URL}")
    driver = build_driver()
    try:
        driver.get(STREAMLIT_URL)
        time.sleep(8)  # let redirects/auth handshake and frontend finish
        print(f"Current URL: {driver.current_url}")
        print(f"Page title: {driver.title}")

        button = find_wake_button(driver)
        if button:
            print("Sleeping app detected. Clicking wake-up button...")
            button.click()
            try:
                WebDriverWait(driver, 180).until(
                    lambda d: WAKE_TEXT not in d.page_source
                )
                print("Wake-up button disappeared. mAICoach is starting.")
            except TimeoutException:
                print("ERROR: wake-up button still visible after 180 s.")
                return 1
        else:
            print("No wake-up button. mAICoach appears awake.")

        time.sleep(15)  # keep the session open so the visit counts
        print(f"Final URL: {driver.current_url}")
        print("Keep-alive completed successfully.")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}")
        return 1
    finally:
        driver.quit()


if __name__ == "__main__":
    sys.exit(main())
