"""Selenium tests for the Package Detail page."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .test_packages_page import browser, api_server

if TYPE_CHECKING:
    from selenium import webdriver

BASE_URL = "http://127.0.0.1:8000"


def _wait_for_element(driver: webdriver.Chrome, by: By, value: str, timeout: int = 10):
    """Wait for an element to be present in the DOM.

    Args:
        driver: Selenium WebDriver instance
        by: Locator strategy (By.ID, By.CSS_SELECTOR, etc.)
        value: Locator value
        timeout: Maximum time to wait in seconds (default: 10)

    Returns:
        WebElement: The found element
    """
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, value))
    )


def _wait_for_clickable(driver: webdriver.Chrome, by: By, value: str, timeout: int = 10):
    """Wait for an element to be clickable.

    Args:
        driver: Selenium WebDriver instance
        by: Locator strategy (By.ID, By.CSS_SELECTOR, etc.)
        value: Locator value
        timeout: Maximum time to wait in seconds (default: 10)

    Returns:
        WebElement: The clickable element
    """
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, value))
    )


def _create_test_package() -> str:
    """Create a test package via API and return its ID.

    Returns:
        str: Package ID of the created package
    """
    payload = {
        "name": "Test Detail Model",
        "version": "2.0.0",
        "metadata": {
            "url": "https://huggingface.co/test/detail-model",
            "description": "A test model for detail page testing",
        },
    }
    response = requests.post(f"{BASE_URL}/api/packages", json=payload, timeout=5)
    response.raise_for_status()
    package_data = response.json()
    return package_data["id"]


@pytest.mark.e2e
def test_package_detail_page_loads(browser: webdriver.Chrome) -> None:
    """Test that the package detail page loads correctly."""
    # Reset and create test package
    requests.delete(f"{BASE_URL}/api/reset", timeout=5)
    package_id = _create_test_package()

    browser.get(f"{BASE_URL}/packages/{package_id}")

    # Check page title
    assert "Package Details" in browser.title or "Package" in browser.title

    # Check breadcrumb navigation
    breadcrumb = _wait_for_element(browser, By.CSS_SELECTOR, "nav[aria-label='breadcrumb']")
    assert breadcrumb is not None

    # Check loading indicator initially
    loading_indicator = _wait_for_element(browser, By.ID, "loading-indicator")
    assert loading_indicator is not None


@pytest.mark.e2e
def test_package_detail_page_displays_package_info(browser: webdriver.Chrome) -> None:
    """Test that package information is displayed correctly."""
    # Reset and create test package
    requests.delete(f"{BASE_URL}/api/reset", timeout=5)
    package_id = _create_test_package()

    browser.get(f"{BASE_URL}/packages/{package_id}")

    # Wait for loading to complete and details to appear
    WebDriverWait(browser, 15).until(
        EC.invisibility_of_element_located((By.ID, "loading-indicator"))
    )

    # Wait for package details to be visible
    package_details = _wait_for_element(browser, By.ID, "package-details")
    WebDriverWait(browser, 10).until(
        lambda d: package_details.is_displayed()
    )

    # Check package name
    package_name = browser.find_element(By.ID, "package-name")
    assert "Test Detail Model" in package_name.text

    # Check package ID
    package_id_element = browser.find_element(By.ID, "package-id")
    assert package_id in package_id_element.text

    # Check version
    version_element = browser.find_element(By.ID, "package-version")
    assert "2.0.0" in version_element.text


@pytest.mark.e2e
def test_package_detail_page_action_buttons(browser: webdriver.Chrome) -> None:
    """Test that action buttons (Rate, Delete) are present and clickable."""
    # Reset and create test package
    requests.delete(f"{BASE_URL}/api/reset", timeout=5)
    package_id = _create_test_package()

    browser.get(f"{BASE_URL}/packages/{package_id}")

    # Wait for page to load
    WebDriverWait(browser, 15).until(
        EC.invisibility_of_element_located((By.ID, "loading-indicator"))
    )

    # Check Rate button
    rate_button = _wait_for_clickable(browser, By.ID, "rate-btn")
    assert rate_button is not None
    assert "Rate" in rate_button.text
    assert rate_button.get_attribute("aria-label") == "Rate this package"

    # Check Delete button
    delete_button = _wait_for_clickable(browser, By.ID, "delete-btn")
    assert delete_button is not None
    assert "Delete" in delete_button.text
    assert delete_button.get_attribute("aria-label") == "Delete this package"


@pytest.mark.e2e
def test_package_detail_page_metadata_display(browser: webdriver.Chrome) -> None:
    """Test that package metadata is displayed correctly."""
    # Reset and create test package
    requests.delete(f"{BASE_URL}/api/reset", timeout=5)
    package_id = _create_test_package()

    browser.get(f"{BASE_URL}/packages/{package_id}")

    # Wait for page to load
    WebDriverWait(browser, 15).until(
        EC.invisibility_of_element_located((By.ID, "loading-indicator"))
    )

    # Check metadata card
    metadata_card = _wait_for_element(browser, By.CSS_SELECTOR, "#package-details .card:last-child")
    assert metadata_card is not None

    # Check metadata content
    metadata_pre = browser.find_element(By.ID, "package-metadata")
    assert metadata_pre is not None
    assert metadata_pre.get_attribute("role") == "region"

    # Metadata should contain JSON
    metadata_text = metadata_pre.text
    assert "url" in metadata_text.lower() or "description" in metadata_text.lower()


@pytest.mark.e2e
def test_package_detail_page_breadcrumb_navigation(browser: webdriver.Chrome) -> None:
    """Test that breadcrumb navigation works correctly."""
    # Reset and create test package
    requests.delete(f"{BASE_URL}/api/reset", timeout=5)
    package_id = _create_test_package()

    browser.get(f"{BASE_URL}/packages/{package_id}")

    # Wait for page to load
    WebDriverWait(browser, 15).until(
        EC.invisibility_of_element_located((By.ID, "loading-indicator"))
    )

    # Check breadcrumb
    breadcrumb = _wait_for_element(browser, By.CSS_SELECTOR, "nav[aria-label='breadcrumb']")
    assert breadcrumb is not None

    # Check breadcrumb items
    breadcrumb_items = browser.find_elements(By.CSS_SELECTOR, ".breadcrumb-item")
    assert len(breadcrumb_items) >= 2

    # Check Packages link
    packages_link = browser.find_element(By.CSS_SELECTOR, ".breadcrumb-item a")
    assert packages_link is not None
    assert "Packages" in packages_link.text or "/" in packages_link.get_attribute("href")

    # Click breadcrumb link
    packages_link.click()

    # Should navigate to packages page
    WebDriverWait(browser, 5).until(
        lambda d: "/packages/" not in d.current_url
    )


@pytest.mark.e2e
def test_package_detail_page_accessibility_features(browser: webdriver.Chrome) -> None:
    """Test accessibility features on the package detail page."""
    # Reset and create test package
    requests.delete(f"{BASE_URL}/api/reset", timeout=5)
    package_id = _create_test_package()

    browser.get(f"{BASE_URL}/packages/{package_id}")

    # Wait for page to load
    WebDriverWait(browser, 15).until(
        EC.invisibility_of_element_located((By.ID, "loading-indicator"))
    )

    # Check loading indicator accessibility
    loading_indicator = browser.find_element(By.ID, "loading-indicator")
    assert loading_indicator.get_attribute("role") == "status"
    assert loading_indicator.get_attribute("aria-live") == "polite"

    # Check breadcrumb accessibility
    breadcrumb = browser.find_element(By.CSS_SELECTOR, "nav[aria-label='breadcrumb']")
    assert breadcrumb.get_attribute("aria-label") == "breadcrumb"

    # Check action buttons accessibility
    rate_button = browser.find_element(By.ID, "rate-btn")
    assert rate_button.get_attribute("aria-label") == "Rate this package"

    delete_button = browser.find_element(By.ID, "delete-btn")
    assert delete_button.get_attribute("aria-label") == "Delete this package"

    # Check metrics card accessibility (if present)
    metrics_card = browser.find_element(By.ID, "metrics-card")
    if metrics_card.is_displayed():
        assert metrics_card.get_attribute("role") == "region"
        assert metrics_card.get_attribute("aria-labelledby") == "metrics-title"


@pytest.mark.e2e
def test_package_detail_page_metrics_section(browser: webdriver.Chrome) -> None:
    """Test that metrics section exists (may be hidden if no metrics)."""
    # Reset and create test package
    requests.delete(f"{BASE_URL}/api/reset", timeout=5)
    package_id = _create_test_package()

    browser.get(f"{BASE_URL}/packages/{package_id}")

    # Wait for page to load
    WebDriverWait(browser, 15).until(
        EC.invisibility_of_element_located((By.ID, "loading-indicator"))
    )

    # Check metrics card exists
    metrics_card = browser.find_element(By.ID, "metrics-card")
    assert metrics_card is not None

    # Metrics may or may not be displayed depending on whether metrics exist
    # Just verify the structure is present
    metrics_content = browser.find_element(By.ID, "metrics-content")
    assert metrics_content.get_attribute("role") == "region"
    assert metrics_content.get_attribute("aria-live") == "polite"
