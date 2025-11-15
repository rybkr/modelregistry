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
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        storage.reset()
        yield client
        storage.reset()


@pytest.fixture
def sample_packages(client):
    """Create sample packages for testing."""
    packages = [
        {"name": "alpha", "version": "1.0.0", "content": "a" * 100},  # 100 bytes
        {"name": "beta", "version": "2.0.0", "content": "b" * 200},   # 200 bytes
        {"name": "gamma", "version": "1.5.0", "content": "g" * 150},  # 150 bytes
        {"name": "delta", "version": "2.5.0", "content": "d" * 250},  # 250 bytes
        {"name": "epsilon", "version": "1.2.0", "content": "e" * 120},  # 120 bytes
    ]

    for pkg in packages:
        client.post("/packages", json=pkg)

    return packages


def test_version_filter_with_sorting(sample_packages, client):
    """Test that version filtering works with sorting."""
    # Get all packages with version ~1 (allows minor-level changes, so all 1.x.x versions), sorted by size descending
    response = client.get("/packages?version=~1&sort-field=size&sort-order=descending")

    assert response.status_code == 200
    data = response.get_json()
    packages = data["packages"]

    # 3 packages match ~1: alpha(1.0.0), gamma(1.5.0), epsilon(1.2.0)
    assert len(packages) == 3

    # Should be sorted by size descending: gamma(150), epsilon(120), alpha(100)
    assert packages[0]["name"] == "gamma"
    assert packages[1]["name"] == "epsilon"
    assert packages[2]["name"] == "alpha"


def test_version_filter_with_pagination(sample_packages, client):
    """Test that version filtering works correctly with pagination."""
    # Get packages with version ~2 (2.x.x), limit 1, offset 0
    response = client.get("/packages?version=~2&limit=1&offset=0")

    assert response.status_code == 200
    data = response.get_json()
    packages = data["packages"]

    # Should get first package that matches version ~2
    # There are 2 packages: beta (2.0.0) and delta (2.5.0)
    # With limit=1, offset=0, should get exactly 1
    assert len(packages) == 1


def test_filter_sort_paginate_together(sample_packages, client):
    """Test combining filter, sort, and pagination."""
    # Get packages with version ~1 (1.x.x), sorted by name, limit 2, offset 1
    response = client.get("/packages?version=~1&sort-field=alpha&limit=2&offset=1")

    assert response.status_code == 200
    data = response.get_json()
    packages = data["packages"]

    # 3 packages match version ~1: alpha(1.0.0), gamma(1.5.0), epsilon(1.2.0)
    # Sorted alphabetically: alpha, epsilon, gamma
    # With offset=1, limit=2: should get epsilon and gamma
    assert len(packages) == 2
    assert packages[0]["name"] == "epsilon"
    assert packages[1]["name"] == "gamma"


def test_descending_sort_with_filter_iterator_bug(sample_packages, client):
    """Test that descending sort works with version filtering (tests iterator bug fix)."""
    # This would have failed with the old code due to filter() returning iterator
    response = client.get("/packages?version=~2&sort-field=size&sort-order=descending")

    assert response.status_code == 200
    data = response.get_json()
    packages = data["packages"]

    # 2 packages match ~2: beta(2.0.0, 200 bytes), delta(2.5.0, 250 bytes)
    # Sorted by size descending: delta, beta
    assert len(packages) == 2
    assert packages[0]["name"] == "delta"
    assert packages[1]["name"] == "beta"


def test_total_reflects_filtered_count_not_registry_count(sample_packages, client):
    """Test that 'total' field reflects filtered count, not total registry count."""
    # Get all packages - should show total registry count
    response = client.get("/packages")
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 5  # All 5 packages

    # Filter by version ~1 - should show filtered count (3 packages)
    response = client.get("/packages?version=~1")
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 3  # Only packages matching ~1
    assert len(data["packages"]) == 3

    # Filter by version ~2 - should show filtered count (2 packages)
    response = client.get("/packages?version=~2")
    assert response.status_code == 200
    data = response.get_json()
    assert data["total"] == 2  # Only packages matching ~2
    assert len(data["packages"]) == 2


def test_total_with_pagination_shows_filtered_count(sample_packages, client):
    """Test that 'total' shows filtered count even when pagination limits results."""
    # Filter by ~1 with pagination (3 matching, but limit to 2)
    response = client.get("/packages?version=~1&limit=2&offset=0")
    assert response.status_code == 200
    data = response.get_json()

    # Should return 2 packages (due to limit)
    assert len(data["packages"]) == 2

    # But total should be 3 (total matching the filter, not limited by pagination)
    assert data["total"] == 3
    assert data["limit"] == 2
    assert data["offset"] == 0


def test_total_with_search_query(sample_packages, client):
    """Test that 'total' reflects search results count."""
    # Search for packages with 'a' in the name
    response = client.get("/packages?query=a")
    assert response.status_code == 200
    data = response.get_json()

    # Should find: alpha, gamma, delta (3 packages with 'a')
    matching_count = len(data["packages"])
    assert data["total"] == matching_count

    # Search for packages with 'beta' in the name
    response = client.get("/packages?query=beta")
    assert response.status_code == 200
    data = response.get_json()

    # Should find: beta (1 package)
    assert data["total"] == 1
    assert len(data["packages"]) == 1
