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
from auth import hash_password  # noqa: E402
from registry_models import User  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
import uuid  # noqa: E402


@pytest.fixture
def client():
    """Test client with admin authentication token."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        storage.reset()
        storage._activity_log.clear()  # type: ignore[attr-defined]
        storage._log_entries.clear()  # type: ignore[attr-defined]

        # Create test admin user with all permissions
        test_user = User(
            user_id=str(uuid.uuid4()),
            username="test_admin",
            password_hash=hash_password("test_password"),
            permissions=["upload", "search", "download", "admin"],
            is_admin=True,
            created_at=datetime.now(timezone.utc)
        )
        storage.create_user(test_user)

        # Authenticate and get token
        response = client.put(
            "/api/authenticate",
            json={"user": {"name": "test_admin"}, "secret": {"password": "test_password"}}
        )
        token = response.get_json()

        # Create a wrapper class to inject auth header automatically
        class AuthenticatedClient:
            def __init__(self, client, token):
                self._client = client
                self._token = token

            def get(self, *args, **kwargs):
                kwargs.setdefault('headers', {})['X-Authorization'] = self._token
                return self._client.get(*args, **kwargs)

            def post(self, *args, **kwargs):
                kwargs.setdefault('headers', {})['X-Authorization'] = self._token
                return self._client.post(*args, **kwargs)

            def put(self, *args, **kwargs):
                kwargs.setdefault('headers', {})['X-Authorization'] = self._token
                return self._client.put(*args, **kwargs)

            def delete(self, *args, **kwargs):
                kwargs.setdefault('headers', {})['X-Authorization'] = self._token
                return self._client.delete(*args, **kwargs)

            def patch(self, *args, **kwargs):
                kwargs.setdefault('headers', {})['X-Authorization'] = self._token
                return self._client.patch(*args, **kwargs)

        yield AuthenticatedClient(client, token)
        storage.reset()
        storage._activity_log.clear()  # type: ignore[attr-defined]
        storage._log_entries.clear()  # type: ignore[attr-defined]


@pytest.fixture
def unauth_client():
    """Test client without authentication for testing auth failure scenarios."""
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
