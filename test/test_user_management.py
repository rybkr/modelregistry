"""
Tests for user management and permissions system.

Tests cover:
- User registration and deletion
- Authentication with bcrypt password hashing
- Token creation, validation, expiration, and usage tracking
- Permission checks (upload, search, download)
- Admin-only operations
- Reset functionality
"""

import pytest
from datetime import datetime, timedelta, timezone
from src.registry_models import User, Token
from src.storage import RegistryStorage


class TestUserModel:
    """Test User model functionality."""

    def test_user_creation(self):
        """Test creating a user with permissions."""
        user = User(
            username="testuser",
            password_hash="hashed_password",
            is_admin=False,
            permissions={"upload", "search"},
            created_at=datetime.now(timezone.utc)
        )

        assert user.username == "testuser"
        assert user.is_admin is False
        assert "upload" in user.permissions
        assert "search" in user.permissions
        assert "download" not in user.permissions

    def test_user_has_permission(self):
        """Test permission checking."""
        user = User(
            username="testuser",
            password_hash="hash",
            permissions={"upload", "download"}
        )

        assert user.has_permission("upload") is True
        assert user.has_permission("download") is True
        assert user.has_permission("search") is False

    def test_user_to_dict(self):
        """Test user serialization (excludes password)."""
        user = User(
            username="testuser",
            password_hash="secret_hash",
            is_admin=True,
            permissions={"upload", "search", "download"},
            created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        )

        user_dict = user.to_dict()

        assert user_dict["username"] == "testuser"
        assert user_dict["is_admin"] is True
        assert set(user_dict["permissions"]) == {"upload", "search", "download"}
        assert "password_hash" not in user_dict  # Security check


class TestTokenModel:
    """Test Token model functionality."""

    def test_token_creation(self):
        """Test creating a token."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=10)

        token = Token(
            token="bearer test-token-123",
            username="testuser",
            created_at=now,
            expires_at=expires,
            usage_count=0,
            max_usage=1000
        )

        assert token.token == "bearer test-token-123"
        assert token.username == "testuser"
        assert token.usage_count == 0
        assert token.max_usage == 1000

    def test_token_is_valid_fresh(self):
        """Test that a fresh token is valid."""
        now = datetime.now(timezone.utc)
        token = Token(
            token="bearer test",
            username="user",
            created_at=now,
            expires_at=now + timedelta(hours=10),
            usage_count=0
        )

        assert token.is_valid() is True

    def test_token_is_invalid_expired(self):
        """Test that an expired token is invalid."""
        now = datetime.now(timezone.utc)
        token = Token(
            token="bearer test",
            username="user",
            created_at=now - timedelta(hours=11),
            expires_at=now - timedelta(hours=1),  # Expired 1 hour ago
            usage_count=0
        )

        assert token.is_valid() is False

    def test_token_is_invalid_max_usage(self):
        """Test that a token with max usage is invalid."""
        now = datetime.now(timezone.utc)
        token = Token(
            token="bearer test",
            username="user",
            created_at=now,
            expires_at=now + timedelta(hours=10),
            usage_count=1000,  # At max
            max_usage=1000
        )

        assert token.is_valid() is False

    def test_token_increment_usage(self):
        """Test incrementing token usage."""
        now = datetime.now(timezone.utc)
        token = Token(
            token="bearer test",
            username="user",
            created_at=now,
            expires_at=now + timedelta(hours=10)
        )

        assert token.usage_count == 0
        token.increment_usage()
        assert token.usage_count == 1
        token.increment_usage()
        assert token.usage_count == 2


class TestStorageUserManagement:
    """Test storage layer user management."""

    @pytest.fixture
    def storage(self):
        """Create a fresh storage instance for each test."""
        storage = RegistryStorage()
        yield storage
        # Clean up after test
        storage.reset()

    def test_default_user_initialized(self, storage):
        """Test that default admin user is initialized on startup."""
        default_user = storage.get_user("ece30861defaultadminuser")

        assert default_user is not None
        assert default_user.is_admin is True
        assert "upload" in default_user.permissions
        assert "search" in default_user.permissions
        assert "download" in default_user.permissions

    def test_verify_default_password(self, storage):
        """Test default admin password verification."""
        password = "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"
        is_valid = storage.verify_password("ece30861defaultadminuser", password)

        assert is_valid is True

    def test_verify_wrong_password(self, storage):
        """Test that wrong password fails verification."""
        is_valid = storage.verify_password("ece30861defaultadminuser", "wrongpassword")

        assert is_valid is False

    def test_create_user(self, storage):
        """Test creating a new user."""
        user = storage.create_user(
            username="alice",
            password="password123",
            is_admin=False,
            permissions={"upload", "search"}
        )

        assert user.username == "alice"
        assert user.is_admin is False
        assert user.permissions == {"upload", "search"}

        # Verify user is in storage
        retrieved = storage.get_user("alice")
        assert retrieved is not None
        assert retrieved.username == "alice"

    def test_create_duplicate_user_raises_error(self, storage):
        """Test that creating duplicate user raises ValueError."""
        storage.create_user("alice", "pass123")

        with pytest.raises(ValueError, match="already exists"):
            storage.create_user("alice", "pass456")

    def test_delete_user(self, storage):
        """Test deleting a user."""
        storage.create_user("bob", "pass123")
        assert storage.get_user("bob") is not None

        deleted = storage.delete_user("bob")

        assert deleted is not None
        assert deleted.username == "bob"
        assert storage.get_user("bob") is None

    def test_delete_user_also_deletes_tokens(self, storage):
        """Test that deleting a user also deletes their tokens."""
        storage.create_user("charlie", "pass123")
        token = storage.create_token("charlie")

        assert storage.get_token(token.token) is not None

        storage.delete_user("charlie")

        # Token should be gone
        assert storage.get_token(token.token) is None

    def test_create_token(self, storage):
        """Test creating an authentication token."""
        token = storage.create_token("ece30861defaultadminuser")

        assert token.token.startswith("bearer ")
        assert token.username == "ece30861defaultadminuser"
        assert token.usage_count == 0
        assert token.max_usage == 1000

        # Token should be valid for 10 hours
        now = datetime.now(timezone.utc)
        time_until_expiry = token.expires_at - now
        assert timedelta(hours=9, minutes=59) < time_until_expiry < timedelta(hours=10, minutes=1)

    def test_validate_and_use_token(self, storage):
        """Test token validation and usage increment."""
        token = storage.create_token("ece30861defaultadminuser")

        username = storage.validate_and_use_token(token.token)

        assert username == "ece30861defaultadminuser"
        assert token.usage_count == 1

        # Use again
        username = storage.validate_and_use_token(token.token)
        assert token.usage_count == 2

    def test_validate_invalid_token_returns_none(self, storage):
        """Test that invalid token returns None."""
        username = storage.validate_and_use_token("bearer invalid-token")

        assert username is None

    def test_reset_reinitializes_default_user(self, storage):
        """Test that reset reinitializes the default admin user."""
        # Create some users and tokens
        storage.create_user("alice", "pass123")
        storage.create_user("bob", "pass456")

        assert len(storage.users) == 3  # Default + alice + bob

        # Reset
        storage.reset()

        # Only default user should remain
        assert len(storage.users) == 1
        default_user = storage.get_user("ece30861defaultadminuser")
        assert default_user is not None
        assert default_user.is_admin is True


class TestAuthenticationEndpoint:
    """Test authentication endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from src.api_server import app
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client

    @pytest.fixture(autouse=True)
    def reset_storage(self):
        """Reset storage before and after each test."""
        from src.storage import storage
        storage.reset()
        yield
        storage.reset()

    def test_authenticate_success(self, client):
        """Test successful authentication."""
        response = client.put('/api/authenticate', json={
            "user": {"name": "ece30861defaultadminuser"},
            "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
        })

        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, str)
        assert data.startswith("bearer ")

    def test_authenticate_wrong_password(self, client):
        """Test authentication with wrong password."""
        response = client.put('/api/authenticate', json={
            "user": {"name": "ece30861defaultadminuser"},
            "secret": {"password": "wrongpassword"}
        })

        assert response.status_code == 401
        data = response.get_json()
        assert "invalid" in data["error"].lower()

    def test_authenticate_missing_fields(self, client):
        """Test authentication with missing fields."""
        response = client.put('/api/authenticate', json={
            "user": {"name": "admin"}
        })

        assert response.status_code == 400


class TestUserRegistrationEndpoint:
    """Test user registration endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from src.api_server import app
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client

    @pytest.fixture(autouse=True)
    def reset_storage(self):
        """Reset storage before and after each test."""
        from src.storage import storage
        storage.reset()
        yield
        storage.reset()

    @pytest.fixture
    def admin_token(self, client):
        """Get admin authentication token."""
        response = client.put('/api/authenticate', json={
            "user": {"name": "ece30861defaultadminuser"},
            "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
        })
        return response.get_json()

    def test_register_user_success(self, client, admin_token):
        """Test successful user registration."""
        response = client.post('/api/user',
            headers={"X-Authorization": admin_token},
            json={
                "username": "alice",
                "password": "secure123",
                "permissions": ["upload", "search"]
            }
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data["username"] == "alice"
        assert set(data["permissions"]) == {"upload", "search"}
        assert data["is_admin"] is False

    def test_register_admin_user(self, client, admin_token):
        """Test registering an admin user."""
        response = client.post('/api/user',
            headers={"X-Authorization": admin_token},
            json={
                "username": "bob",
                "password": "pass123",
                "is_admin": True,
                "permissions": ["upload", "search", "download"]
            }
        )

        assert response.status_code == 201
        data = response.get_json()
        assert data["is_admin"] is True

    def test_register_user_without_admin_fails(self, client, admin_token):
        """Test that non-admin cannot register users."""
        # First create a non-admin user
        resp = client.post('/api/user',
            headers={"X-Authorization": admin_token},
            json={
                "username": "charlie",
                "password": "pass123",
                "permissions": ["search"]
            }
        )
        assert resp.status_code == 201

        # Authenticate as charlie
        response = client.put('/api/authenticate', json={
            "user": {"name": "charlie"},
            "secret": {"password": "pass123"}
        })
        assert response.status_code == 200
        charlie_token = response.get_json()

        # Try to register another user
        response = client.post('/api/user',
            headers={"X-Authorization": charlie_token},
            json={
                "username": "dave",
                "password": "pass456",
                "permissions": ["upload"]
            }
        )

        assert response.status_code == 403
        data = response.get_json()
        assert "administrator" in data["error"].lower()

    def test_register_duplicate_user_fails(self, client, admin_token):
        """Test that registering duplicate user fails."""
        # Register first user
        client.post('/api/user',
            headers={"X-Authorization": admin_token},
            json={"username": "alice", "password": "pass123"}
        )

        # Try to register same username again
        response = client.post('/api/user',
            headers={"X-Authorization": admin_token},
            json={"username": "alice", "password": "different"}
        )

        assert response.status_code == 409


class TestUserDeletionEndpoint:
    """Test user deletion endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from src.api_server import app
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client

    @pytest.fixture(autouse=True)
    def reset_storage(self):
        """Reset storage before and after each test."""
        from src.storage import storage
        storage.reset()
        yield
        storage.reset()

    @pytest.fixture
    def admin_token(self, client):
        """Get admin authentication token."""
        response = client.put('/api/authenticate', json={
            "user": {"name": "ece30861defaultadminuser"},
            "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
        })
        return response.get_json()

    def test_user_can_delete_own_account(self, client, admin_token):
        """Test that user can delete their own account."""
        # Create user
        resp = client.post('/api/user',
            headers={"X-Authorization": admin_token},
            json={"username": "selfdelete", "password": "pass123"}
        )
        assert resp.status_code == 201

        # Authenticate as selfdelete
        response = client.put('/api/authenticate', json={
            "user": {"name": "selfdelete"},
            "secret": {"password": "pass123"}
        })
        assert response.status_code == 200
        user_token = response.get_json()

        # Delete own account
        response = client.delete('/api/user/selfdelete',
            headers={"X-Authorization": user_token}
        )

        assert response.status_code == 200

    def test_admin_can_delete_any_user(self, client, admin_token):
        """Test that admin can delete any user."""
        # Create user
        client.post('/api/user',
            headers={"X-Authorization": admin_token},
            json={"username": "alice", "password": "pass123"}
        )

        # Admin deletes alice
        response = client.delete('/api/user/alice',
            headers={"X-Authorization": admin_token}
        )

        assert response.status_code == 200

    def test_user_cannot_delete_other_users(self, client, admin_token):
        """Test that non-admin user cannot delete other users."""
        # Create two users
        client.post('/api/user',
            headers={"X-Authorization": admin_token},
            json={"username": "alice", "password": "pass123"}
        )
        client.post('/api/user',
            headers={"X-Authorization": admin_token},
            json={"username": "bob", "password": "pass456"}
        )

        # Authenticate as alice
        response = client.put('/api/authenticate', json={
            "user": {"name": "alice"},
            "secret": {"password": "pass123"}
        })
        alice_token = response.get_json()

        # Try to delete bob
        response = client.delete('/api/user/bob',
            headers={"X-Authorization": alice_token}
        )

        assert response.status_code == 403

    def test_cannot_delete_default_admin(self, client, admin_token):
        """Test that default admin user cannot be deleted."""
        response = client.delete('/api/user/ece30861defaultadminuser',
            headers={"X-Authorization": admin_token}
        )

        assert response.status_code == 403
        data = response.get_json()
        assert "default" in data["error"].lower()


class TestPermissions:
    """Test permission checks on endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from src.api_server import app
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client

    @pytest.fixture(autouse=True)
    def reset_storage(self):
        """Reset storage before and after each test."""
        from src.storage import storage
        storage.reset()
        yield
        storage.reset()

    @pytest.fixture
    def admin_token(self, client):
        """Get admin authentication token."""
        response = client.put('/api/authenticate', json={
            "user": {"name": "ece30861defaultadminuser"},
            "secret": {"password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"}
        })
        return response.get_json()

    def test_upload_requires_permission(self, client, admin_token):
        """Test that upload endpoint requires upload permission."""
        # Create user without upload permission
        client.post('/api/user',
            headers={"X-Authorization": admin_token},
            json={
                "username": "alice",
                "password": "pass123",
                "permissions": ["search", "download"]  # No upload
            }
        )

        # Authenticate as alice
        response = client.put('/api/authenticate', json={
            "user": {"name": "alice"},
            "secret": {"password": "pass123"}
        })
        alice_token = response.get_json()

        # Try to upload (create artifact)
        response = client.post('/api/artifact/model',
            headers={"X-Authorization": alice_token},
            json={"url": "https://huggingface.co/gpt2"}
        )

        assert response.status_code == 403
        data = response.get_json()
        assert "upload" in data["error"].lower()

    def test_search_requires_permission(self, client, admin_token):
        """Test that search/list endpoint requires search permission."""
        # Create user without search permission
        client.post('/api/user',
            headers={"X-Authorization": admin_token},
            json={
                "username": "alice",
                "password": "pass123",
                "permissions": ["upload", "download"]  # No search
            }
        )

        # Authenticate as alice
        response = client.put('/api/authenticate', json={
            "user": {"name": "alice"},
            "secret": {"password": "pass123"}
        })
        alice_token = response.get_json()

        # Try to list artifacts
        response = client.post('/api/artifacts',
            headers={"X-Authorization": alice_token},
            json=[{"name": "*"}]
        )

        assert response.status_code == 403
        data = response.get_json()
        assert "search" in data["error"].lower()

    def test_admin_bypasses_permission_checks(self, client, admin_token):
        """Test that admin users bypass permission checks."""
        # Create admin user with no explicit permissions
        client.post('/api/user',
            headers={"X-Authorization": admin_token},
            json={
                "username": "admin2",
                "password": "pass123",
                "is_admin": True,
                "permissions": []  # No permissions, but is admin
            }
        )

        # Authenticate as admin2
        response = client.put('/api/authenticate', json={
            "user": {"name": "admin2"},
            "secret": {"password": "pass123"}
        })
        admin2_token = response.get_json()

        # Should be able to list artifacts despite no search permission
        response = client.post('/api/artifacts',
            headers={"X-Authorization": admin2_token},
            json=[{"name": "*"}]
        )

        assert response.status_code == 200  # Admin bypasses permission check


class TestTokenExpiration:
    """Test token expiration and usage limits."""

    def test_token_becomes_invalid_after_max_usage(self):
        """Test that token becomes invalid after 1000 uses."""
        from src.storage import storage
        storage.reset()

        token = storage.create_token("ece30861defaultadminuser")

        # Use token 999 times
        for _ in range(999):
            username = storage.validate_and_use_token(token.token)
            assert username is not None

        assert token.usage_count == 999
        assert token.is_valid() is True

        # 1000th use should work
        username = storage.validate_and_use_token(token.token)
        assert username is not None
        assert token.usage_count == 1000

        # Token should now be invalid
        assert token.is_valid() is False

        # 1001st use should fail
        username = storage.validate_and_use_token(token.token)
        assert username is None

    def test_expired_token_cannot_be_used(self):
        """Test that expired tokens cannot be used."""
        from src.storage import storage
        from src.registry_models import Token

        storage.reset()

        # Create an already-expired token manually
        now = datetime.now(timezone.utc)
        expired_token = Token(
            token="bearer expired-token",
            username="ece30861defaultadminuser",
            created_at=now - timedelta(hours=11),
            expires_at=now - timedelta(hours=1),  # Expired 1 hour ago
            usage_count=0
        )

        storage.tokens[expired_token.token] = expired_token

        # Try to use it
        username = storage.validate_and_use_token(expired_token.token)

        assert username is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
