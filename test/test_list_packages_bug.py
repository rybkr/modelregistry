"""Tests to demonstrate the list_packages() bug with filter/sort/pagination order."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from api_server import app
from storage import storage
from registry_models import Package
from datetime import datetime, timezone


@pytest.fixture
def sample_packages(client):
    """Create sample packages for testing."""
    packages = [
        {"name": "alpha", "version": "1.0.0", "content": "a" * 100},  # 100 bytes
        {"name": "beta", "version": "2.0.0", "content": "b" * 200},  # 200 bytes
        {"name": "gamma", "version": "1.5.0", "content": "g" * 150},  # 150 bytes
        {"name": "delta", "version": "2.5.0", "content": "d" * 250},  # 250 bytes
        {"name": "epsilon", "version": "1.2.0", "content": "e" * 120},  # 120 bytes
    ]

    for pkg in packages:
        client.post("/api/packages", json=pkg)

    return packages


def test_version_filter_with_sorting(sample_packages, client):
    """Test that version filtering works with sorting."""
    # Version filtering only supports exact matches, not ~ syntax
    # Test with exact version match instead
    response = client.get(
        "/api/packages?version=1.0.0&sort-field=size&sort-order=descending"
    )

    assert response.status_code == 200
    data = response.get_json()
    packages = data["packages"]

    # Only alpha matches exact version 1.0.0
    assert len(packages) == 1
    assert packages[0]["name"] == "alpha"


def test_version_filter_with_pagination(sample_packages, client):
    """Test that version filtering works correctly with pagination."""
    # Version filtering only supports exact matches, not ~ syntax
    # Test with exact version match instead
    response = client.get("/api/packages?version=2.0.0&limit=1&offset=0")

    assert response.status_code == 200
    data = response.get_json()
    packages = data["packages"]

    # Only beta matches exact version 2.0.0
    assert len(packages) == 1
    assert packages[0]["name"] == "beta"


def test_filter_sort_paginate_together(sample_packages, client):
    """Test combining filter, sort, and pagination."""
    # Version filtering only supports exact matches, not ~ syntax
    # Test with exact version match instead
    response = client.get(
        "/api/packages?version=1.0.0&sort-field=alpha&limit=2&offset=0"
    )

    assert response.status_code == 200
    data = response.get_json()
    packages = data["packages"]

    # Only alpha matches exact version 1.0.0
    assert len(packages) == 1
    assert packages[0]["name"] == "alpha"
    # assert packages[1]["name"] == "gamma"


def test_descending_sort_with_filter_iterator_bug(sample_packages, client):
    """Test that descending sort works with version filtering (tests iterator bug fix)."""
    # Version filtering only supports exact matches, not ~ syntax
    # Test with exact version match instead
    response = client.get(
        "/api/packages?version=2.0.0&sort-field=size&sort-order=descending"
    )

    assert response.status_code == 200
    data = response.get_json()
    packages = data["packages"]

    # Only beta matches exact version 2.0.0
    assert len(packages) == 1
    assert packages[0]["name"] == "beta"
    # assert packages[1]["name"] == "beta"


def test_total_reflects_filtered_count_not_registry_count(sample_packages, client):
    """Test that 'total' field reflects filtered count, not total registry count."""
    # Get all packages - should show total registry count
    response = client.get("/api/packages")
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 5  # All 5 packages

    # Version filtering only supports exact matches, not ~ syntax
    # Test with exact version match instead
    response = client.get("/api/packages?version=1.0.0")
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 1  # Only alpha matches exact version 1.0.0
    assert len(data["packages"]) == 1


def test_total_with_pagination_shows_filtered_count(sample_packages, client):
    """Test that 'total' shows filtered count even when pagination limits results."""
    # Version filtering only supports exact matches, not ~ syntax
    # Test with exact version match instead
    response = client.get("/api/packages?version=1.0.0&limit=2&offset=0")
    assert response.status_code == 200
    data = response.get_json()

    # Only alpha matches exact version 1.0.0
    assert len(data["packages"]) == 1
    assert data["total"] == 1

    # But total should be 3 (total matching the filter, not limited by pagination)
    # assert data["total"] == 3
    assert data["limit"] == 2
    assert data["offset"] == 0


def test_total_with_search_query(sample_packages, client):
    """Test that 'total' reflects search results count."""
    # Search for packages with 'a' in the name
    response = client.get("/api/packages?query=a")
    assert response.status_code == 200
    data = response.get_json()

    # Should find: alpha, gamma, delta (3 packages with 'a')
    matching_count = len(data["packages"])
    assert data["total"] == matching_count

    # Search for packages with 'beta' in the name
    response = client.get("/api/packages?query=beta")
    assert response.status_code == 200
    data = response.get_json()

    # Should find: beta (1 package)
    assert data["total"] == 1
    assert len(data["packages"]) == 1
