from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time

STREAMLIT_URL = "https://maicoach.streamlit.app/"


def main():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    print(f"Opening {STREAMLIT_URL}")

    driver = webdriver.Chrome(options=options)

    try:
        driver.get(STREAMLIT_URL)

        print(f"Current URL: {driver.current_url}")
        print(f"Page title: {driver.title}")

        # Give Streamlit's frontend time to initialize.
        time.sleep(5)

        wake_selectors = [
            (By.XPATH, "//button[contains(., 'Yes, get this app back up')]"),
            (By.CSS_SELECTOR, '[data-testid="wakeup-button-viewer"]'),
        ]

        wake_button = None

        for by, selector in wake_selectors:
            try:
                wake_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((by, selector))
                )
                break
            except TimeoutException:
                pass

        if wake_button:
            print("Sleeping app detected.")
            print("Clicking wake-up button...")

            wake_button.click()

            # Give Community Cloud time to start the application.
            WebDriverWait(driver, 120).until(
                lambda d: "Yes, get this app back up" not in d.page_source
            )

            print("Wake-up button disappeared.")
            print("mAICoach should now be starting/awake.")

        else:
            print("No wake-up button detected.")
            print("mAICoach appears to already be awake.")

        # Keep the browser session alive briefly so the visit registers.
        time.sleep(10)

        print(f"Final URL: {driver.current_url}")
        print("Keep-alive completed successfully.")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()