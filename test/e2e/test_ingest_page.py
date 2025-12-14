"""Selenium tests for the Ingest from HuggingFace page."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest
import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

if TYPE_CHECKING:
    from selenium import webdriver

BASE_URL = "http://127.0.0.1:8000"


def _wait_for_element(driver: webdriver.Chrome, by: By, value: str, timeout: int = 10):
    """Wait for an element to be present."""
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, value))
    )


def _wait_for_clickable(driver: webdriver.Chrome, by: By, value: str, timeout: int = 10):
    """Wait for an element to be clickable."""
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, value))
    )


@pytest.mark.e2e
def test_ingest_page_loads(browser: webdriver.Chrome) -> None:
    """Test that the ingest page loads correctly."""
    browser.get(f"{BASE_URL}/ingest")
    
    # Check page title
    assert "Ingest" in browser.title or "HuggingFace" in browser.title
    
    # Check main heading
    heading = _wait_for_element(browser, By.TAG_NAME, "h1")
    assert "Ingest" in heading.text or "HuggingFace" in heading.text
    
    # Check info alert
    alert = _wait_for_element(browser, By.CSS_SELECTOR, ".alert-info")
    assert alert is not None
    assert "0.5" in alert.text or "metrics" in alert.text.lower()


@pytest.mark.e2e
def test_ingest_page_form_present(browser: webdriver.Chrome) -> None:
    """Test that the ingest form is present with correct fields."""
    browser.get(f"{BASE_URL}/ingest")
    
    # Check form
    form = _wait_for_element(browser, By.ID, "ingest-form")
    assert form.get_attribute("role") == "form"
    assert form.get_attribute("aria-label") == "Ingest model form"
    
    # Check URL field
    url_field = _wait_for_element(browser, By.ID, "model-url")
    assert url_field.get_attribute("required") is not None
    assert url_field.get_attribute("aria-required") == "true"
    assert url_field.get_attribute("type") == "url"
    
    # Check buttons
    cancel_button = _wait_for_element(browser, By.CSS_SELECTOR, 'a[href*="index"]')
    assert cancel_button is not None
    
    submit_button = _wait_for_element(browser, By.CSS_SELECTOR, "#ingest-form button[type='submit']")
    assert submit_button is not None
    assert "Ingest" in submit_button.text


@pytest.mark.e2e
def test_ingest_page_form_validation(browser: webdriver.Chrome) -> None:
    """Test form validation for the ingest form."""
    browser.get(f"{BASE_URL}/ingest")
    
    # Try to submit empty form
    submit_button = _wait_for_clickable(browser, By.CSS_SELECTOR, "#ingest-form button[type='submit']")
    submit_button.click()
    
    # HTML5 validation should prevent submission
    url_field = _wait_for_element(browser, By.ID, "model-url")
    is_invalid = browser.execute_script(
        "return arguments[0].validity.valid === false;", url_field
    )
    assert is_invalid or url_field.get_attribute("aria-invalid") == "true"
    
    # Try invalid URL format
    url_field.clear()
    url_field.send_keys("not-a-valid-url")
    submit_button.click()
    
    # Should still be invalid
    is_invalid = browser.execute_script(
        "return arguments[0].validity.valid === false;", url_field
    )
    assert is_invalid


@pytest.mark.e2e
def test_ingest_page_valid_url_format(browser: webdriver.Chrome) -> None:
    """Test that valid HuggingFace URL format is accepted."""
    browser.get(f"{BASE_URL}/ingest")
    
    url_field = _wait_for_element(browser, By.ID, "model-url")
    
    # Enter valid HuggingFace URL
    valid_url = "https://huggingface.co/test-org/test-model"
    url_field.clear()
    url_field.send_keys(valid_url)
    
    # Field should accept the URL
    assert url_field.get_attribute("value") == valid_url
    
    # Check validation state
    is_valid = browser.execute_script(
        "return arguments[0].validity.valid === true;", url_field
    )
    assert is_valid


@pytest.mark.e2e
def test_ingest_page_cancel_button(browser: webdriver.Chrome) -> None:
    """Test that cancel button navigates back to packages page."""
    browser.get(f"{BASE_URL}/ingest")
    
    cancel_button = _wait_for_clickable(browser, By.CSS_SELECTOR, 'a[href*="index"]')
    cancel_button.click()
    
    # Should navigate to packages page
    WebDriverWait(browser, 5).until(
        lambda d: "/ingest" not in d.current_url
    )
    assert "/" in browser.current_url or "packages" in browser.current_url.lower()


@pytest.mark.e2e
def test_ingest_page_evaluation_progress_section(browser: webdriver.Chrome) -> None:
    """Test that evaluation progress section exists (hidden initially)."""
    browser.get(f"{BASE_URL}/ingest")
    
    # Progress section should exist but be hidden
    progress_section = _wait_for_element(browser, By.ID, "evaluation-progress")
    assert progress_section is not None
    
    # Check that it's initially hidden
    is_displayed = progress_section.is_displayed()
    assert not is_displayed, "Progress section should be hidden initially"
    
    # Check progress bar elements
    progress_bar = browser.find_element(By.CSS_SELECTOR, "#evaluation-progress .progress")
    assert progress_bar.get_attribute("role") == "progressbar"
    assert progress_bar.get_attribute("aria-label") == "Evaluation progress"
    
    status_text = browser.find_element(By.ID, "evaluation-status")
    assert status_text.get_attribute("aria-live") == "polite"


@pytest.mark.e2e
def test_ingest_page_accessibility_features(browser: webdriver.Chrome) -> None:
    """Test accessibility features on the ingest page."""
    browser.get(f"{BASE_URL}/ingest")
    
    # Check ARIA labels
    form = _wait_for_element(browser, By.ID, "ingest-form")
    assert form.get_attribute("role") == "form"
    assert form.get_attribute("aria-label") == "Ingest model form"
    
    # Check required field
    url_field = _wait_for_element(browser, By.ID, "model-url")
    assert url_field.get_attribute("aria-required") == "true"
    assert url_field.get_attribute("aria-describedby") is not None
    
    # Check help text
    help_text = browser.find_element(By.ID, "model-url-help")
    assert help_text is not None
    
    # Check error message container
    error_container = browser.find_element(By.ID, "model-url-error")
    assert error_container.get_attribute("role") == "alert"
    assert error_container.get_attribute("aria-live") == "polite"
    
    # Check info alert
    alert = browser.find_element(By.CSS_SELECTOR, ".alert-info")
    assert alert.get_attribute("role") == "alert"
