from __future__ import annotations

import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest
import requests
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE_URL = "http://127.0.0.1:8000"

# Default admin credentials
DEFAULT_USERNAME = "ece30861defaultadminuser"
DEFAULT_PASSWORD = "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"


@contextmanager
def _run_api_server() -> Iterator[subprocess.Popen]:
    """Start the Flask API server in a background process."""
    env = os.environ.copy()
    process = subprocess.Popen(
        [sys.executable, "src/api_server.py"],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    try:
        yield process
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def _wait_for_server_ready(timeout: float = 30.0) -> None:
    """Poll the health endpoint until the server responds or timeout occurs."""
    deadline = time.time() + timeout
    last_error: Exception | None = None
    headers = {"Accept": "application/json"}

    while time.time() < deadline:
        try:
            response = requests.get(f"{BASE_URL}/api/health", headers=headers, timeout=1)
            if response.status_code == 200:
                return
        except requests.RequestException as exc:
            last_error = exc
        time.sleep(0.25)

    raise RuntimeError(f"API server did not become ready: {last_error}")


@pytest.fixture(scope="session")
def api_server() -> Iterator[str]:
    """Launch the API server once per test session."""
    with _run_api_server():
        _wait_for_server_ready()
        # Ensure we start from a clean registry state
        try:
            # Try to reset if we can authenticate
            token = _authenticate()
            if token:
                requests.delete(
                    f"{BASE_URL}/api/reset",
                    headers={"X-Authorization": token},
                    timeout=5,
                )
        except Exception:
            pass  # Ignore if reset fails
        yield BASE_URL
        # Clean up after tests
        try:
            token = _authenticate()
            if token:
                requests.delete(
                    f"{BASE_URL}/api/reset",
                    headers={"X-Authorization": token},
                    timeout=5,
                )
        except Exception:
            pass


@pytest.fixture
def browser(api_server: str) -> Iterator[webdriver.Chrome]:
    """Provide a headless Chrome WebDriver configured for CI-friendly runs."""
    try:
        driver_path = ChromeDriverManager().install()
    except Exception as exc:
        pytest.skip(f"Chrome driver not available: {exc}")

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--remote-allow-origins=*")
    chrome_options.add_argument("--window-size=1280,720")

    service = Service(driver_path)

    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)
    except WebDriverException as exc:
        pytest.skip(f"Unable to start Chrome WebDriver: {exc}")

    try:
        yield driver
    finally:
        driver.quit()


def _authenticate(password: str = DEFAULT_PASSWORD) -> str | None:
    """Authenticate and return token.

    Args:
        password: Password to use for authentication

    Returns:
        Authentication token string or None if authentication fails
    """
    payload = {
        "user": {"name": DEFAULT_USERNAME, "is_admin": True},
        "secret": {"password": password},
    }
    try:
        response = requests.put(
            f"{BASE_URL}/api/authenticate",
            json=payload,
            timeout=5,
        )
        if response.status_code == 200:
            return response.json()  # Token is returned as JSON string
        return None
    except Exception:
        return None


def _create_package(name: str, version: str, url: str) -> None:
    # Get auth token
    token = _authenticate()
    if not token:
        raise RuntimeError("Failed to authenticate for package creation")

    payload = {
        "name": name,
        "version": version,
        "metadata": {
            "url": url,
            "readme": f"{name} README describing datasets and code examples.",
        },
    }
    response = requests.post(
        f"{BASE_URL}/api/packages",
        json=payload,
        headers={"X-Authorization": token},
        timeout=5
    )
    response.raise_for_status()


def _wait_for_package_cards(driver: webdriver.Chrome, minimum: int) -> list[str]:
    wait = WebDriverWait(driver, 15)
    wait.until(
        lambda d: len(
            d.find_elements(By.CSS_SELECTOR, "#packages-container .card .card-title a")
        )
        >= minimum
    )
    links = driver.find_elements(
        By.CSS_SELECTOR, "#packages-container .card .card-title a"
    )
    return [link.text.strip() for link in links]


def _wait_for_no_results(driver: webdriver.Chrome) -> None:
    wait = WebDriverWait(driver, 10)
    wait.until(
        EC.text_to_be_present_in_element(
            (By.CSS_SELECTOR, "#packages-container .card .card-body"), "No packages"
        )
    )


@pytest.mark.e2e
def test_model_packages_page_lists_and_filters_packages(browser: webdriver.Chrome) -> None:
    """Verify that the Model Packages page renders, searches, and resets results."""
    # Reset registry state and create sample packages
    requests.delete(f"{BASE_URL}/reset", timeout=5)
    _create_package("Vision Model", "1.0.0", "https://example.com/vision")
    _create_package("Text Generator", "2.1.0", "https://example.com/text")

    browser.get(f"{BASE_URL}/")

    package_names = _wait_for_package_cards(browser, minimum=2)
    assert "Vision Model" in package_names
    assert "Text Generator" in package_names

    search_input = browser.find_element(By.ID, "search-query")
    search_input.clear()
    search_input.send_keys("Vision")

    browser.find_element(By.CSS_SELECTOR, "#search-form button[type='submit']").click()

    filtered_names = _wait_for_package_cards(browser, minimum=1)
    assert filtered_names == ["Vision Model"]

    browser.find_element(By.ID, "clear-search").click()
    reset_names = _wait_for_package_cards(browser, minimum=2)
    assert set(reset_names) == {"Vision Model", "Text Generator"}

    # Enable regex and ensure no results message appears for a non-matching pattern
    browser.find_element(By.ID, "use-regex").click()
    search_input = browser.find_element(By.ID, "search-query")
    search_input.clear()
    search_input.send_keys("^Audio")
    browser.find_element(By.CSS_SELECTOR, "#search-form button[type='submit']").click()

    _wait_for_no_results(browser)
