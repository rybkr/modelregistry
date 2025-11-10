"""Pytest configuration and shared fixtures."""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
SRC_PATH = os.path.join(PROJECT_ROOT, "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from api_server import app  # noqa: E402  (import after path adjustment)
from storage import storage  # noqa: E402


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        storage.reset()
        storage._activity_log.clear()  # type: ignore[attr-defined]
        storage._log_entries.clear()  # type: ignore[attr-defined]
        yield client
        storage.reset()
        storage._activity_log.clear()  # type: ignore[attr-defined]
        storage._log_entries.clear()  # type: ignore[attr-defined]


@pytest.fixture
def sample_repo_id() -> str:
    """Return a sample repository ID for testing."""
    return "test-org/test-repo"


@pytest.fixture
def sample_model_url() -> str:
    """Return a sample Hugging Face model URL."""
    return "https://huggingface.co/test-org/test-model"


@pytest.fixture
def sample_dataset_url() -> str:
    """Return a sample Hugging Face dataset URL."""
    return "https://huggingface.co/datasets/test-org/test-dataset"


@pytest.fixture
def sample_github_url() -> str:
    """Return a sample GitHub repository URL."""
    return "https://github.com/test-org/test-repo"
