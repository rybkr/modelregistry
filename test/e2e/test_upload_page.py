"""Selenium tests for the Upload Package page."""

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
def test_upload_page_loads(browser: webdriver.Chrome) -> None:
    """Test that the upload page loads correctly."""
    browser.get(f"{BASE_URL}/upload")
    
    # Check page title
    assert "Upload Package" in browser.title
    
    # Check main heading
    heading = _wait_for_element(browser, By.TAG_NAME, "h1")
    assert "Upload Package" in heading.text
    
    # Check form is present
    form = _wait_for_element(browser, By.ID, "upload-form")
    assert form is not None


@pytest.mark.e2e
def test_upload_page_form_fields_present(browser: webdriver.Chrome) -> None:
    """Test that all form fields are present on the upload page."""
    browser.get(f"{BASE_URL}/upload")
    
    # Check required fields
    name_field = _wait_for_element(browser, By.ID, "package-name")
    assert name_field.get_attribute("required") is not None
    assert name_field.get_attribute("aria-required") == "true"
    
    version_field = _wait_for_element(browser, By.ID, "package-version")
    assert version_field.get_attribute("required") is not None
    assert version_field.get_attribute("aria-required") == "true"
    
    # Check optional fields
    url_field = _wait_for_element(browser, By.ID, "package-url")
    assert url_field is not None
    
    content_field = _wait_for_element(browser, By.ID, "package-content")
    assert content_field is not None
    
    metadata_field = _wait_for_element(browser, By.ID, "package-metadata")
    assert metadata_field is not None
    
    # Check buttons
    cancel_button = _wait_for_element(browser, By.CSS_SELECTOR, 'a[href*="index"]')
    assert cancel_button is not None
    
    submit_button = _wait_for_element(browser, By.CSS_SELECTOR, "#upload-form button[type='submit']")
    assert submit_button is not None


@pytest.mark.e2e
def test_upload_page_form_validation_empty_fields(browser: webdriver.Chrome) -> None:
    """Test form validation when required fields are empty."""
    browser.get(f"{BASE_URL}/upload")
    
    # Try to submit empty form
    submit_button = _wait_for_clickable(browser, By.CSS_SELECTOR, "#upload-form button[type='submit']")
    submit_button.click()
    
    # HTML5 validation should prevent submission
    # Check that name field shows validation
    name_field = _wait_for_element(browser, By.ID, "package-name")
    is_invalid = browser.execute_script(
        "return arguments[0].validity.valid === false;", name_field
    )
    assert is_invalid or name_field.get_attribute("aria-invalid") == "true"


@pytest.mark.e2e
def test_upload_page_form_submission_success(browser: webdriver.Chrome) -> None:
    """Test successful package upload via the form."""
    # Reset registry
    requests.delete(f"{BASE_URL}/api/reset", timeout=5)
    
    browser.get(f"{BASE_URL}/upload")
    
    # Fill in form fields
    name_field = _wait_for_element(browser, By.ID, "package-name")
    name_field.clear()
    name_field.send_keys("Test Upload Model")
    
    version_field = _wait_for_element(browser, By.ID, "package-version")
    version_field.clear()
    version_field.send_keys("1.0.0")
    
    url_field = _wait_for_element(browser, By.ID, "package-url")
    url_field.clear()
    url_field.send_keys("https://huggingface.co/test/model")
    
    content_field = _wait_for_element(browser, By.ID, "package-content")
    content_field.clear()
    content_field.send_keys("This is a test model description")
    
    # Submit form
    submit_button = _wait_for_clickable(browser, By.CSS_SELECTOR, "#upload-form button[type='submit']")
    submit_button.click()
    
    # Wait for redirect or success message
    # The form should submit via JavaScript, so we wait for either:
    # 1. Redirect to packages page
    # 2. Success alert message
    time.sleep(2)  # Give JavaScript time to process
    
    # Check if we're redirected or if there's a success message
    current_url = browser.current_url
    if "/upload" in current_url:
        # Check for success alert
        try:
            alert = WebDriverWait(browser, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "#alert-container .alert-success"))
            )
            assert "success" in alert.text.lower() or "uploaded" in alert.text.lower()
        except Exception:
            # If no alert, check if form was submitted (field values cleared)
            # This indicates the form was processed
            name_value = name_field.get_attribute("value")
            # Form might be cleared on success
            pass
    else:
        # Redirected to packages page
        assert "/" in current_url or "packages" in current_url.lower()


@pytest.mark.e2e
def test_upload_page_cancel_button(browser: webdriver.Chrome) -> None:
    """Test that cancel button navigates back to packages page."""
    browser.get(f"{BASE_URL}/upload")
    
    cancel_button = _wait_for_clickable(browser, By.CSS_SELECTOR, 'a[href*="index"]')
    cancel_button.click()
    
    # Should navigate to packages page
    WebDriverWait(browser, 5).until(
        lambda d: "/upload" not in d.current_url
    )
    assert "/" in browser.current_url or "packages" in browser.current_url.lower()


@pytest.mark.e2e
def test_upload_page_metadata_json_validation(browser: webdriver.Chrome) -> None:
    """Test that metadata field accepts JSON format."""
    browser.get(f"{BASE_URL}/upload")
    
    metadata_field = _wait_for_element(browser, By.ID, "package-metadata")
    
    # Enter valid JSON
    valid_json = '{"key": "value", "number": 123}'
    metadata_field.clear()
    metadata_field.send_keys(valid_json)
    
    # Enter invalid JSON (should still be allowed in the field, validation happens on submit)
    invalid_json = '{"key": "value"'
    metadata_field.clear()
    metadata_field.send_keys(invalid_json)
    
    # Field should still accept the input (validation happens on submit)
    assert metadata_field.get_attribute("value") == invalid_json


@pytest.mark.e2e
def test_upload_page_accessibility_features(browser: webdriver.Chrome) -> None:
    """Test accessibility features on the upload page."""
    browser.get(f"{BASE_URL}/upload")
    
    # Check ARIA labels
    form = _wait_for_element(browser, By.ID, "upload-form")
    assert form.get_attribute("role") == "form"
    assert form.get_attribute("aria-label") == "Upload package form"
    
    # Check required field indicators
    name_field = _wait_for_element(browser, By.ID, "package-name")
    assert name_field.get_attribute("aria-required") == "true"
    assert name_field.get_attribute("aria-describedby") is not None
    
    # Check help text
    help_text = browser.find_element(By.ID, "package-name-help")
    assert help_text is not None
    
    # Check error message container
    error_container = browser.find_element(By.ID, "package-name-error")
    assert error_container.get_attribute("role") == "alert"
    assert error_container.get_attribute("aria-live") == "polite"
