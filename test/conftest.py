"""Pytest configuration and shared fixtures."""

import pytest


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
