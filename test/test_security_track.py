"""Tests for Security Track features: user management, permissions, sensitive models, package confusion."""

import pytest
import sys
import os
from datetime import datetime, timezone
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from api_server import app
from storage import storage
from registry_models import Package, User
from auth import hash_password


@pytest.fixture
def admin_client():
    """Authenticated admin client."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        storage.reset()

        # Create admin user
        admin = User(
            user_id=str(uuid.uuid4()),
            username="admin",
            password_hash=hash_password("admin123"),
            permissions=["upload", "search", "download", "admin"],
            is_admin=True,
            created_at=datetime.now(timezone.utc)
        )
        storage.create_user(admin)

        # Authenticate
        response = client.put("/api/authenticate", json={"user": {"name": "admin"}, "secret": {"password": "admin123"}})
        token = response.get_json()

        yield client, token
        storage.reset()


def test_user_registration_admin_only(admin_client):
    """Only admins can register users."""
    client, token = admin_client

    # Admin can register user
    response = client.post("/api/users",
        headers={"X-Authorization": token},
        json={"username": "newuser", "password": "pass123", "permissions": ["search"]})
    assert response.status_code == 201
