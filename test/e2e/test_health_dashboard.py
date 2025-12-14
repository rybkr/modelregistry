"""Selenium tests for the Health Dashboard page."""

from __future__ import annotations

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
    """Wait for an element to be clickable."""
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((by, value))
    )


def _create_test_packages(count: int = 3) -> None:
    """Create test packages via API for use in E2E tests.

    Args:
        count: Number of packages to create (default: 3)
    """
    for i in range(count):
        payload = {
            "name": f"Test Model {i+1}",
            "version": f"{i+1}.0.0",
            "metadata": {"url": f"https://huggingface.co/test/model{i+1}"},
        }
        requests.post(f"{BASE_URL}/api/packages", json=payload, timeout=5)


@pytest.mark.e2e
def test_health_dashboard_loads(browser: webdriver.Chrome) -> None:
    """Test that the health dashboard loads correctly."""
    browser.get(f"{BASE_URL}/health")

    # Check page title
    assert "Health" in browser.title or "Dashboard" in browser.title

    # Check main heading
    heading = _wait_for_element(browser, By.TAG_NAME, "h1")
    assert "Health" in heading.text or "Dashboard" in heading.text

    # Check status card
    status_card = _wait_for_element(browser, By.ID, "status-card")
    assert status_card is not None


@pytest.mark.e2e
def test_health_dashboard_status_cards(browser: webdriver.Chrome) -> None:
    """Test that all status cards are present and display information."""
    # Reset and create test packages
    requests.delete(f"{BASE_URL}/api/reset", timeout=5)
    _create_test_packages(3)

    browser.get(f"{BASE_URL}/health")

    # Wait for health data to load
    WebDriverWait(browser, 15).until(
        lambda d: d.find_element(By.ID, "health-status").text != "-"
    )

    # Check status card
    status_card = _wait_for_element(browser, By.ID, "status-card")
    health_status = browser.find_element(By.ID, "health-status")
    assert health_status.text.strip() != ""
    assert health_status.text.strip() != "-"

    # Check packages count card
    packages_count = browser.find_element(By.ID, "packages-count")
    assert packages_count.text.strip() != ""
    assert packages_count.text.strip() != "-"
    # Should show at least 3 packages
    count_value = packages_count.text.strip()
    assert any(char.isdigit() for char in count_value)

    # Check last updated card
    last_updated = browser.find_element(By.ID, "last-updated")
    assert last_updated.text.strip() != ""
    assert last_updated.text.strip() != "-"


@pytest.mark.e2e
def test_health_dashboard_refresh_buttons(browser: webdriver.Chrome) -> None:
    """Test that refresh buttons are present and functional."""
    browser.get(f"{BASE_URL}/health")

    # Check health refresh button
    health_refresh = _wait_for_clickable(browser, By.ID, "refresh-health")
    assert health_refresh is not None
    assert "Refresh" in health_refresh.text
    assert health_refresh.get_attribute("aria-label") == "Refresh health data"

    # Check activity refresh button
    activity_refresh = _wait_for_clickable(browser, By.ID, "refresh-activity")
    assert activity_refresh is not None
    assert "Refresh" in activity_refresh.text
    assert activity_refresh.get_attribute("aria-label") == "Refresh activity data"

    # Check logs refresh button
    logs_refresh = _wait_for_clickable(browser, By.ID, "refresh-logs")
    assert logs_refresh is not None
    assert "Refresh" in logs_refresh.text
    assert logs_refresh.get_attribute("aria-label") == "Refresh system logs"

    # Click refresh buttons (should not cause errors)
    health_refresh.click()
    # Wait a moment for any updates
    WebDriverWait(browser, 2).until(
        lambda d: True  # Just wait a moment
    )


@pytest.mark.e2e
def test_health_dashboard_health_details_section(browser: webdriver.Chrome) -> None:
    """Test that health details section loads and displays information."""
    browser.get(f"{BASE_URL}/health")

    # Check health details section
    health_details = _wait_for_element(browser, By.ID, "health-details")
    assert health_details is not None
    assert health_details.get_attribute("role") == "region"
    assert health_details.get_attribute("aria-live") == "polite"

    # Wait for loading to complete
    WebDriverWait(browser, 15).until(
        lambda d: "Loading" not in health_details.text or health_details.text.strip() != ""
    )

    # Health details should have content (not just loading message)
    details_text = health_details.text
    # Should have some content beyond just "Loading..."
    assert len(details_text.strip()) > 10 or "Loading" not in details_text


@pytest.mark.e2e
def test_health_dashboard_activity_section(browser: webdriver.Chrome) -> None:
    """Test that activity section is present and displays information."""
    # Reset and create test packages to generate activity
    requests.delete(f"{BASE_URL}/api/reset", timeout=5)
    _create_test_packages(2)

    browser.get(f"{BASE_URL}/health")

    # Wait for activity data to load
    WebDriverWait(browser, 15).until(
        lambda d: "Loading activity data" not in d.find_element(By.ID, "activity-summary").text
    )

    # Check activity summary
    activity_summary = _wait_for_element(browser, By.ID, "activity-summary")
    assert activity_summary is not None
    assert activity_summary.get_attribute("role") == "region"
    assert activity_summary.get_attribute("aria-live") == "polite"

    # Check activity timeline
    activity_timeline = _wait_for_element(browser, By.ID, "activity-events-body")
    assert activity_timeline is not None
    assert activity_timeline.get_attribute("role") == "region"
    assert activity_timeline.get_attribute("aria-live") == "polite"


@pytest.mark.e2e
def test_health_dashboard_logs_section(browser: webdriver.Chrome) -> None:
    """Test that logs section is present and displays information."""
    browser.get(f"{BASE_URL}/health")

    # Wait for logs to load
    WebDriverWait(browser, 15).until(
        lambda d: "Loading logs" not in d.find_element(By.ID, "logs-body").text
    )

    # Check logs body
    logs_body = _wait_for_element(browser, By.ID, "logs-body")
    assert logs_body is not None
    assert logs_body.get_attribute("role") == "log"
    assert logs_body.get_attribute("aria-live") == "polite"
    assert logs_body.get_attribute("aria-label") == "System logs"


@pytest.mark.e2e
def test_health_dashboard_reset_registry_button(browser: webdriver.Chrome) -> None:
    """Test that reset registry button is present with warning."""
    browser.get(f"{BASE_URL}/health")

    # Check warning alert
    warning_alert = _wait_for_element(browser, By.CSS_SELECTOR, ".alert-warning")
    assert warning_alert is not None
    assert warning_alert.get_attribute("role") == "alert"
    assert "Warning" in warning_alert.text or "reset" in warning_alert.text.lower()

    # Check reset button
    reset_button = _wait_for_clickable(browser, By.ID, "reset-registry")
    assert reset_button is not None
    assert "Reset" in reset_button.text
    assert reset_button.get_attribute("aria-label") == "Reset registry"

    # Button should be present (we won't actually click it to avoid data loss)


@pytest.mark.e2e
def test_health_dashboard_accessibility_features(browser: webdriver.Chrome) -> None:
    """Test accessibility features on the health dashboard."""
    browser.get(f"{BASE_URL}/health")

    # Check ARIA labels on refresh buttons
    health_refresh = browser.find_element(By.ID, "refresh-health")
    assert health_refresh.get_attribute("aria-label") == "Refresh health data"

    activity_refresh = browser.find_element(By.ID, "refresh-activity")
    assert activity_refresh.get_attribute("aria-label") == "Refresh activity data"

    logs_refresh = browser.find_element(By.ID, "refresh-logs")
    assert logs_refresh.get_attribute("aria-label") == "Refresh system logs"

    # Check live regions
    health_details = browser.find_element(By.ID, "health-details")
    assert health_details.get_attribute("aria-live") == "polite"

    activity_summary = browser.find_element(By.ID, "activity-summary")
    assert activity_summary.get_attribute("aria-live") == "polite"

    logs_body = browser.find_element(By.ID, "logs-body")
    assert logs_body.get_attribute("aria-live") == "polite"

    # Check progress bar accessibility
    progress_bars = browser.find_elements(By.CSS_SELECTOR, ".progress[role='progressbar']")
    for progress_bar in progress_bars:
        assert progress_bar.get_attribute("aria-label") is not None
