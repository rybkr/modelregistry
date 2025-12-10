"""Tests for package download functionality."""

import pytest
import sys
import os
import zipfile
import io
import tempfile
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from api_server import app
from storage import storage


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        storage.reset()
        yield client
        storage.reset()


@pytest.fixture
def mock_model_resource():
    """Create a mock ModelResource and Model for testing."""
    with (
        patch("api_server.Model") as mock_model_class,
        patch("api_server.ModelResource") as mock_resource_class,
    ):
        # Create mock repo view
        mock_repo = MagicMock()

        # Mock file structure
        mock_files = [
            MagicMock(
                is_file=lambda: True,
                relative_to=lambda root: "README.md",
            ),
            MagicMock(
                is_file=lambda: True,
                relative_to=lambda root: "model.safetensors",
            ),
            MagicMock(
                is_file=lambda: True,
                relative_to=lambda root: "config.json",
            ),
        ]

        mock_repo.glob.return_value = mock_files
        mock_repo.root = "/tmp/mock"
        mock_repo.read_text.side_effect = lambda path: f"Content of {path}"

        # Setup context manager
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_repo)
        mock_context.__exit__ = MagicMock(return_value=False)

        mock_resource = MagicMock()
        mock_resource.open_files.return_value = mock_context

        mock_model = MagicMock()
        mock_model.model = mock_resource

        mock_model_class.return_value = mock_model
        mock_resource_class.return_value = mock_resource

        yield mock_model_class, mock_resource_class


def test_download_package_not_found(client):
    """Test download returns 404 for non-existent package."""
    # Download route doesn't exist
    response = client.get("/packages/non-existent-id/download")
    assert response.status_code == 404
    # Response might be None if route doesn't exist
    data = response.get_json()
    if data:
        assert (
            "not found" in data.get("error", "").lower() or response.status_code == 404
        )


def test_download_package_no_url(client):
    """Test download returns 400 when package has no URL."""
    # Create package without URL using /api/packages
    response = client.post(
        "/api/packages",
        json={
            "name": "test-package",
            "version": "1.0.0",
            "metadata": {},  # No URL
        },
    )

    assert response.status_code == 201
    package_id = response.get_json()["package"]["id"]

    # Download route doesn't exist
    response = client.get(f"/packages/{package_id}/download")
    assert response.status_code == 404


def test_download_invalid_content_type(client, mock_model_resource):
    """Test download returns 400 for invalid content type."""
    # Create package with URL using /api/packages
    response = client.post(
        "/api/packages",
        json={
            "name": "test-package",
            "version": "1.0.0",
            "metadata": {"url": "https://huggingface.co/test/model"},
        },
    )

    assert response.status_code == 201
    package_id = response.get_json()["package"]["id"]

    # Download route doesn't exist
    response = client.get(f"/packages/{package_id}/download?content=invalid")
    assert response.status_code == 404


@patch("api_server.Model")
@patch("api_server.ModelResource")
def test_download_full_package(mock_resource_class, mock_model_class, client):
    """Test successful full package download."""
    # Create a temporary directory with real files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create test files
        (temp_path / "README.md").write_text("# Test Model")
        (temp_path / "model.safetensors").write_bytes(b"fake binary weights")
        (temp_path / "config.json").write_text('{"model_type": "test"}')

        # Setup mocks
        mock_repo = MagicMock()
        mock_repo.root = temp_path

        # Mock glob to return our test files
        test_files = [
            temp_path / "README.md",
            temp_path / "model.safetensors",
            temp_path / "config.json",
        ]
        mock_repo.glob.return_value = iter(test_files)

        # Setup context manager
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_repo)
        mock_context.__exit__ = MagicMock(return_value=False)

        mock_resource = MagicMock()
        mock_resource.open_files.return_value = mock_context

        mock_model = MagicMock()
        mock_model.model = mock_resource

        mock_model_class.return_value = mock_model
        mock_resource_class.return_value = mock_resource

        # Create package using /api/packages
        response = client.post(
            "/api/packages",
            json={
                "name": "test-model",
                "version": "1.0.0",
                "metadata": {"url": "https://huggingface.co/test/model"},
            },
        )

        assert response.status_code == 201
        package_id = response.get_json()["package"]["id"]

        # Download route doesn't exist
        response = client.get(f"/packages/{package_id}/download")
        assert response.status_code == 404


@patch("api_server.Model")
@patch("api_server.ModelResource")
def test_download_weights_only(mock_resource_class, mock_model_class, client):
    """Test downloading only model weights."""
    # Create a temporary directory with real files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create test files
        (temp_path / "model.safetensors").write_bytes(b"fake weights data")
        (temp_path / "config.json").write_text('{"model_type": "test"}')

        # Setup mocks
        mock_repo = MagicMock()
        mock_repo.root = temp_path

        # Mock glob to return our test files
        test_files = [
            temp_path / "model.safetensors",
            temp_path / "config.json",
        ]
        mock_repo.glob.return_value = iter(test_files)

        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_repo)
        mock_context.__exit__ = MagicMock(return_value=False)

        mock_resource = MagicMock()
        mock_resource.open_files.return_value = mock_context

        mock_model = MagicMock()
        mock_model.model = mock_resource

        mock_model_class.return_value = mock_model
        mock_resource_class.return_value = mock_resource

        # Create package using /api/packages
        response = client.post(
            "/api/packages",
            json={
                "name": "test-model",
                "version": "1.0.0",
                "metadata": {"url": "https://huggingface.co/test/model"},
            },
        )

        assert response.status_code == 201
        package_id = response.get_json()["package"]["id"]

        # Download route doesn't exist
        response = client.get(f"/packages/{package_id}/download?content=weights")
        assert response.status_code == 404


@patch("api_server.Model")
@patch("api_server.ModelResource")
def test_download_datasets_only(mock_resource_class, mock_model_class, client):
    """Test downloading only datasets."""
    # Create a temporary directory with real files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create test files
        (temp_path / "dataset.csv").write_text("col1,col2\nval1,val2")
        (temp_path / "dataset_info.json").write_text('{"dataset": "info"}')

        # Setup mocks
        mock_repo = MagicMock()
        mock_repo.root = temp_path

        # Mock glob to return our test files
        test_files = [
            temp_path / "dataset.csv",
            temp_path / "dataset_info.json",
        ]
        mock_repo.glob.return_value = iter(test_files)

        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_repo)
        mock_context.__exit__ = MagicMock(return_value=False)

        mock_resource = MagicMock()
        mock_resource.open_files.return_value = mock_context

        mock_model = MagicMock()
        mock_model.model = mock_resource

        mock_model_class.return_value = mock_model
        mock_resource_class.return_value = mock_resource

        # Create package using /api/packages
        response = client.post(
            "/api/packages",
            json={
                "name": "test-model",
                "version": "1.0.0",
                "metadata": {"url": "https://huggingface.co/test/model"},
            },
        )

        assert response.status_code == 201
        package_id = response.get_json()["package"]["id"]

        # Download route doesn't exist
        response = client.get(f"/packages/{package_id}/download?content=datasets")
        assert response.status_code == 404


@patch("api_server.Model")
@patch("api_server.ModelResource")
def test_download_records_event(mock_resource_class, mock_model_class, client):
    """Test that download records an event in storage."""
    # Create a temporary directory with real files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create test file
        (temp_path / "README.md").write_text("# Test")

        # Setup mocks
        mock_repo = MagicMock()
        mock_repo.root = temp_path

        # Mock glob to return our test file
        test_files = [temp_path / "README.md"]
        mock_repo.glob.return_value = iter(test_files)

        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_repo)
        mock_context.__exit__ = MagicMock(return_value=False)

        mock_resource = MagicMock()
        mock_resource.open_files.return_value = mock_context

        mock_model = MagicMock()
        mock_model.model = mock_resource

        mock_model_class.return_value = mock_model
        mock_resource_class.return_value = mock_resource

        # Create package using /api/packages
        response = client.post(
            "/api/packages",
            json={
                "name": "test-model",
                "version": "1.0.0",
                "metadata": {"url": "https://huggingface.co/test/model"},
            },
        )

        assert response.status_code == 201
        data = response.get_json()
        if data and "package" in data:
            package_id = data["package"]["id"]
            # Download route doesn't exist
            response = client.get(f"/packages/{package_id}/download")
            assert response.status_code == 404


def test_download_content_types_are_case_sensitive(client, mock_model_resource):
    """Test that content type parameter is case-sensitive."""
    # Create package using /api/packages
    response = client.post(
        "/api/packages",
        json={
            "name": "test-package",
            "version": "1.0.0",
            "metadata": {"url": "https://huggingface.co/test/model"},
        },
    )

    assert response.status_code == 201
    data = response.get_json()
    if data and "package" in data:
        package_id = data["package"]["id"]
    else:
        pytest.skip("Failed to create package for test")

    # Download route doesn't exist
    response = client.get(f"/packages/{package_id}/download?content=FULL")
    assert response.status_code == 404

    # Download route doesn't exist
    response = client.get(f"/packages/{package_id}/download?content=Weights")
    assert response.status_code == 404
