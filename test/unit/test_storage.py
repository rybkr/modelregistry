"""Unit tests for storage layer functionality.

This module contains comprehensive unit tests for the RegistryStorage class
and related utility functions. Tests cover CRUD operations, search functionality
with regex support, user and token management, activity logging, and security
features like ReDoS protection.
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import uuid

import pytest

from registry_models import Package, User, TokenInfo
from storage import (
    RegistryStorage,
    is_safe_regex,
    regex_compile_with_timeout,
    regex_search_with_timeout,
    storage,
)


class TestIsSafeRegex:
    """Test cases for is_safe_regex function."""

    def test_safe_pattern(self) -> None:
        """Test that safe patterns are accepted."""
        assert is_safe_regex("test") is True
        assert is_safe_regex("test.*") is True
        assert is_safe_regex("[a-z]+") is True

    def test_pattern_too_long(self) -> None:
        """Test that patterns longer than 100 chars are rejected."""
        long_pattern = "a" * 101
        assert is_safe_regex(long_pattern) is False

    def test_dangerous_nested_quantifiers(self) -> None:
        """Test that dangerous nested quantifiers are rejected."""
        assert is_safe_regex("(a+)+") is False
        assert is_safe_regex("(a*)*") is False
        assert is_safe_regex("(a?)?") is False

    def test_pattern_just_under_limit(self) -> None:
        """Test that patterns at the limit are accepted."""
        pattern = "a" * 100
        assert is_safe_regex(pattern) is True


class TestRegexCompileWithTimeout:
    """Test cases for regex_compile_with_timeout function."""

    def test_successful_compilation(self) -> None:
        """Test successful regex compilation."""
        pattern = regex_compile_with_timeout("test.*")
        assert pattern is not None
        assert pattern.search("test123") is not None

    def test_invalid_pattern(self) -> None:
        """Test that invalid patterns return None."""
        pattern = regex_compile_with_timeout("[invalid")
        assert pattern is None

    def test_compilation_exception(self) -> None:
        """Test handling of compilation exceptions."""
        with patch("storage.re.compile", side_effect=Exception("Compilation error")):
            pattern = regex_compile_with_timeout("test")
            assert pattern is None


class TestRegexSearchWithTimeout:
    """Test cases for regex_search_with_timeout function."""

    def test_successful_search(self) -> None:
        """Test successful regex search."""
        pattern = regex_compile_with_timeout("test")
        assert pattern is not None
        match = regex_search_with_timeout(pattern, "test123")
        assert match is not None

    def test_no_match(self) -> None:
        """Test search with no match."""
        pattern = regex_compile_with_timeout("nomatch")
        assert pattern is not None
        match = regex_search_with_timeout(pattern, "test123")
        assert match is None

    def test_timeout_exception(self) -> None:
        """Test handling of timeout exception."""
        # Create a mock pattern that raises TimeoutError
        mock_pattern = MagicMock()
        mock_pattern.search.side_effect = TimeoutError("Timeout")
        
        with pytest.raises(TimeoutError):
            regex_search_with_timeout(mock_pattern, "test")

    def test_general_exception(self) -> None:
        """Test handling of general exceptions."""
        # Create a mock pattern that raises a general exception
        mock_pattern = MagicMock()
        mock_pattern.search.side_effect = Exception("Search error")
        
        result = regex_search_with_timeout(mock_pattern, "test")
        assert result is None


class TestRegistryStorage:
    """Test cases for RegistryStorage class."""

    def test_init(self) -> None:
        """Test storage initialization."""
        store = RegistryStorage()
        assert store.packages == {}
        # Default admin user is created during init
        assert "ece30861defaultadminuser" in store.users
        assert len(store.tokens) > 0  # Default token is created
        assert len(store._activity_log) == 0
        assert len(store._log_entries) == 0

    def test_reset(self) -> None:
        """Test reset clears packages but not users/tokens."""
        store = RegistryStorage()
        # Add some data
        package = Package(
            id="test-id",
            artifact_type="model",
            name="test",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={},
        )
        store.create_package(package)
        user = User(
            user_id=str(uuid.uuid4()),
            username="testuser",
            password_hash="hash",
            permissions=[],
        )
        store.create_user(user)

        store.reset()

        assert len(store.packages) == 0
        assert len(store._activity_log) == 0
        assert len(store._log_entries) == 0
        # Users should still exist (default admin)
        assert "ece30861defaultadminuser" in store.users

    def test_create_package(self) -> None:
        """Test creating a package."""
        store = RegistryStorage()
        package = Package(
            id="test-id",
            artifact_type="model",
            name="test",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={},
        )
        result = store.create_package(package)
        assert result == package
        assert store.get_package("test-id") == package

    def test_get_package(self) -> None:
        """Test getting a package."""
        store = RegistryStorage()
        package = Package(
            id="test-id",
            artifact_type="model",
            name="test",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={},
        )
        store.create_package(package)
        assert store.get_package("test-id") == package
        assert store.get_package("nonexistent") is None

    def test_list_packages(self) -> None:
        """Test listing packages with pagination."""
        store = RegistryStorage()
        for i in range(5):
            package = Package(
                id=f"test-{i}",
                artifact_type="model",
                name=f"test-{i}",
                version="1.0.0",
                uploaded_by="user",
                upload_timestamp=datetime.now(timezone.utc),
                size_bytes=100,
                metadata={},
            )
            store.create_package(package)

        all_packages = store.list_packages()
        assert len(all_packages) == 5

        paginated = store.list_packages(offset=2, limit=2)
        assert len(paginated) == 2

    def test_delete_package(self) -> None:
        """Test deleting a package."""
        store = RegistryStorage()
        package = Package(
            id="test-id",
            artifact_type="model",
            name="test",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={},
        )
        store.create_package(package)
        deleted = store.delete_package("test-id")
        assert deleted == package
        assert store.get_package("test-id") is None
        assert store.delete_package("nonexistent") is None

    def test_search_packages_simple(self) -> None:
        """Test simple string search."""
        store = RegistryStorage()
        package1 = Package(
            id="test-1",
            artifact_type="model",
            name="test-model",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={"readme": "This is a test model"},
        )
        package2 = Package(
            id="test-2",
            artifact_type="model",
            name="other-model",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={},
        )
        store.create_package(package1)
        store.create_package(package2)

        results = store.search_packages("test", use_regex=False)
        assert len(results) == 1
        assert results[0].id == "test-1"

        # Search in README
        results = store.search_packages("test model", use_regex=False)
        assert len(results) == 1

    def test_search_packages_regex(self) -> None:
        """Test regex search."""
        store = RegistryStorage()
        package = Package(
            id="test-1",
            artifact_type="model",
            name="test-model",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={},
        )
        store.create_package(package)

        results = store.search_packages("test.*", use_regex=True)
        assert len(results) == 1

    def test_search_packages_regex_unsafe_pattern(self) -> None:
        """Test regex search with unsafe pattern."""
        store = RegistryStorage()
        package = Package(
            id="test-1",
            artifact_type="model",
            name="test-model",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={},
        )
        store.create_package(package)

        with pytest.raises(TimeoutError):
            store.search_packages("(a+)+", use_regex=True)

    def test_search_packages_regex_compilation_failure(self) -> None:
        """Test regex search when compilation fails."""
        store = RegistryStorage()
        package = Package(
            id="test-1",
            artifact_type="model",
            name="test-model",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={},
        )
        store.create_package(package)

        with patch("storage.regex_compile_with_timeout", return_value=None):
            results = store.search_packages("test", use_regex=True)
            assert results == []

    def test_search_packages_regex_in_readme(self) -> None:
        """Test regex search in README."""
        store = RegistryStorage()
        package = Package(
            id="test-1",
            artifact_type="model",
            name="other",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={"readme": "This is a test README"},
        )
        store.create_package(package)

        results = store.search_packages("test.*README", use_regex=True)
        assert len(results) == 1

    def test_search_packages_regex_case_insensitive_readme_key(self) -> None:
        """Test regex search with case-insensitive README key."""
        store = RegistryStorage()
        package = Package(
            id="test-1",
            artifact_type="model",
            name="other",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={"README": "This is a test README"},
        )
        store.create_package(package)

        results = store.search_packages("test.*README", use_regex=True)
        assert len(results) == 1

    def test_search_packages_regex_long_readme(self) -> None:
        """Test regex search with long README (truncated)."""
        store = RegistryStorage()
        long_readme = "test " + "x" * 20000
        package = Package(
            id="test-1",
            artifact_type="model",
            name="other",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={"readme": long_readme},
        )
        store.create_package(package)

        results = store.search_packages("test", use_regex=True)
        assert len(results) == 1

    def test_search_packages_regex_empty_readme(self) -> None:
        """Test regex search with empty README."""
        store = RegistryStorage()
        package = Package(
            id="test-1",
            artifact_type="model",
            name="other",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={"readme": ""},
        )
        store.create_package(package)

        results = store.search_packages("test", use_regex=True)
        assert len(results) == 0

    @patch("storage.requests.get")
    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"})
    def test_search_packages_regex_huggingface_readme(self, mock_get: MagicMock) -> None:
        """Test regex search fetching README from HuggingFace."""
        store = RegistryStorage()
        package = Package(
            id="test-1",
            artifact_type="model",
            name="other",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={"url": "https://huggingface.co/test/model"},
        )
        store.create_package(package)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "This is a test README"
        mock_get.return_value = mock_response

        results = store.search_packages("test.*README", use_regex=True)
        assert len(results) == 1
        mock_get.assert_called_once()

    @patch("storage.requests.get")
    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"})
    def test_search_packages_regex_github_readme(self, mock_get: MagicMock) -> None:
        """Test regex search fetching README from GitHub."""
        store = RegistryStorage()
        package = Package(
            id="test-1",
            artifact_type="model",
            name="other",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={"url": "https://github.com/owner/repo"},
        )
        store.create_package(package)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"content": base64.b64encode(b"test README").decode()}
        mock_get.return_value = mock_response

        results = store.search_packages("test.*README", use_regex=True)
        assert len(results) == 1

    @patch("storage.requests.get")
    @patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"})
    def test_search_packages_regex_remote_readme_404(self, mock_get: MagicMock) -> None:
        """Test regex search when remote README returns 404."""
        store = RegistryStorage()
        package = Package(
            id="test-1",
            artifact_type="model",
            name="other",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={"url": "https://huggingface.co/test/model"},
        )
        store.create_package(package)

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        results = store.search_packages("test", use_regex=True)
        assert len(results) == 0

    def test_get_artifacts_by_query_enumerate_all(self) -> None:
        """Test get_artifacts_by_query with enumerate all (*)."""
        store = RegistryStorage()
        for i in range(3):
            package = Package(
                id=f"test-{i}",
                artifact_type="model",
                name=f"test-{i}",
                version="1.0.0",
                uploaded_by="user",
                upload_timestamp=datetime.now(timezone.utc),
                size_bytes=100,
                metadata={"url": "https://huggingface.co/test/model"},
            )
            store.create_package(package)

        packages, count = store.get_artifacts_by_query([{"name": "*"}])
        assert count == 3
        assert len(packages) == 3

    def test_get_artifacts_by_query_enumerate_all_with_type_filter(self) -> None:
        """Test enumerate all with type filter."""
        store = RegistryStorage()
        model_pkg = Package(
            id="model-1",
            artifact_type="model",
            name="model",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={"url": "https://huggingface.co/test/model"},
        )
        dataset_pkg = Package(
            id="dataset-1",
            artifact_type="dataset",
            name="dataset",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={"url": "https://huggingface.co/datasets/test/dataset"},
        )
        code_pkg = Package(
            id="code-1",
            artifact_type="code",
            name="code",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={"url": "https://gitlab.com/test/repo"},
        )
        store.create_package(model_pkg)
        store.create_package(dataset_pkg)
        store.create_package(code_pkg)

        packages, count = store.get_artifacts_by_query(
            [{"name": "*"}], artifact_types=["model"]
        )
        assert count == 1
        assert packages[0].id == "model-1"

    def test_get_artifacts_by_query_exact_name_match(self) -> None:
        """Test exact name matching."""
        store = RegistryStorage()
        package = Package(
            id="test-1",
            artifact_type="model",
            name="exact-name",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={},
        )
        store.create_package(package)

        packages, count = store.get_artifacts_by_query([{"name": "exact-name"}])
        assert count == 1
        assert packages[0].name == "exact-name"

    def test_get_artifacts_by_query_exact_name_with_types(self) -> None:
        """Test exact name match with type filter."""
        store = RegistryStorage()
        model_pkg = Package(
            id="model-1",
            artifact_type="model",
            name="test",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={"url": "https://huggingface.co/test/model"},
        )
        code_pkg = Package(
            id="code-1",
            artifact_type="code",
            name="test",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={"url": "https://github.com/test/repo"},
        )
        dataset_pkg = Package(
            id="dataset-1",
            artifact_type="dataset",
            name="test",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={"url": "https://huggingface.co/datasets/test/dataset"},
        )
        store.create_package(model_pkg)
        store.create_package(code_pkg)
        store.create_package(dataset_pkg)

        packages, count = store.get_artifacts_by_query(
            [{"name": "test", "types": ["model"]}]
        )
        assert count == 1
        assert packages[0].id == "model-1"
        
        # Test that exact match with wrong type is skipped
        packages, count = store.get_artifacts_by_query(
            [{"name": "test", "types": ["dataset"]}]
        )
        assert count == 1
        assert packages[0].id == "dataset-1"
        
        # Test that exact match stops processing remaining queries
        # This tests the break at line 391, but line 359 might be unreachable
        # Line 359 would be hit if found_exact_match is True at start of next iteration
        other_pkg = Package(
            id="other-1",
            artifact_type="model",
            name="other",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={},
        )
        store.create_package(other_pkg)
        
        # First query finds exact match, should break before processing second query
        packages, count = store.get_artifacts_by_query(
            [{"name": "test", "types": ["model"]}, {"name": "other"}]
        )
        assert count == 1  # Should stop after first match, second query skipped
        assert packages[0].id == "model-1"  # First match, not "other"
        
        # Try to trigger line 359 by having found_exact_match set but not breaking at 391
        # This might require a scenario where we're in a different branch
        # Actually, line 359 appears to be unreachable based on the code flow
        # The break at 391 always happens after found_exact_match is set

    def test_get_artifacts_by_query_types_only(self) -> None:
        """Test filtering by types only (name is * or empty)."""
        store = RegistryStorage()
        model_pkg = Package(
            id="model-1",
            artifact_type="model",
            name="model",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={"url": "https://huggingface.co/test/model"},
        )
        dataset_pkg = Package(
            id="dataset-1",
            artifact_type="dataset",
            name="dataset",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={"url": "https://huggingface.co/datasets/test/dataset"},
        )
        code_pkg = Package(
            id="code-1",
            artifact_type="code",
            name="code",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={"url": "https://gitlab.com/test/repo"},
        )
        store.create_package(model_pkg)
        store.create_package(dataset_pkg)
        store.create_package(code_pkg)

        packages, count = store.get_artifacts_by_query([{"types": ["model"]}])
        assert count == 1
        assert packages[0].id == "model-1"
        
        # Test code type from gitlab
        packages, count = store.get_artifacts_by_query([{"types": ["code"]}])
        assert count == 1
        assert packages[0].id == "code-1"

    def test_get_artifacts_by_query_pagination(self) -> None:
        """Test pagination in get_artifacts_by_query."""
        store = RegistryStorage()
        for i in range(5):
            package = Package(
                id=f"test-{i}",
                artifact_type="model",
                name=f"test-{i}",
                version="1.0.0",
                uploaded_by="user",
                upload_timestamp=datetime.now(timezone.utc),
                size_bytes=100,
                metadata={},
            )
            store.create_package(package)

        packages, count = store.get_artifacts_by_query([{"name": "*"}], offset=2, limit=2)
        assert count == 5
        assert len(packages) == 2

    def test_get_artifacts_by_query_artifact_types_filter(self) -> None:
        """Test artifact_types filter when not enumerate_all."""
        store = RegistryStorage()
        model_pkg = Package(
            id="model-1",
            artifact_type="model",
            name="model-pkg",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={"url": "https://huggingface.co/test/model"},
        )
        dataset_pkg = Package(
            id="dataset-1",
            artifact_type="dataset",
            name="dataset-pkg",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={"url": "https://huggingface.co/datasets/test/dataset"},
        )
        code_pkg = Package(
            id="code-1",
            artifact_type="code",
            name="code-pkg",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={"url": "https://huggingface.co/spaces/test/space"},
        )
        store.create_package(model_pkg)
        store.create_package(dataset_pkg)
        store.create_package(code_pkg)

        # Query by types only, then filter by artifact_types
        packages, count = store.get_artifacts_by_query(
            [{"types": ["model", "code", "dataset"]}], artifact_types=["model", "code"]
        )
        assert count == 2
        assert any(p.id == "model-1" for p in packages)
        assert any(p.id == "code-1" for p in packages)

    def test_get_artifacts_by_query_invalid_query(self) -> None:
        """Test get_artifacts_by_query with invalid query."""
        store = RegistryStorage()
        packages, count = store.get_artifacts_by_query(["not-a-dict"])
        assert count == 0
        assert len(packages) == 0

    def test_get_artifacts_by_query_non_list_types(self) -> None:
        """Test get_artifacts_by_query with non-list types."""
        store = RegistryStorage()
        package = Package(
            id="test-1",
            artifact_type="model",
            name="test",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={},
        )
        store.create_package(package)

        packages, count = store.get_artifacts_by_query([{"name": "test", "types": "not-a-list"}])
        assert count == 1

    def test_get_artifact_by_type_and_id(self) -> None:
        """Test get_artifact_by_type_and_id."""
        store = RegistryStorage()
        package = Package(
            id="test-1",
            artifact_type="model",
            name="test",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={"url": "https://huggingface.co/test/model"},
        )
        store.create_package(package)

        result = store.get_artifact_by_type_and_id("model", "test-1")
        assert result == package

        result = store.get_artifact_by_type_and_id("dataset", "test-1")
        assert result is None

        result = store.get_artifact_by_type_and_id("model", "nonexistent")
        assert result is None

    def test_get_artifact_by_type_and_id_inferred_type(self) -> None:
        """Test get_artifact_by_type_and_id with inferred type from URL."""
        store = RegistryStorage()
        # Test that when artifact_type matches, it works
        package = Package(
            id="test-1",
            artifact_type="dataset",
            name="test",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={"url": "https://huggingface.co/datasets/test/dataset"},
        )
        store.create_package(package)

        result = store.get_artifact_by_type_and_id("dataset", "test-1")
        assert result == package
        
        # Test type mismatch
        result = store.get_artifact_by_type_and_id("model", "test-1")
        assert result is None

    def test_get_artifact_by_type_and_id_url_inference(self) -> None:
        """Test get_artifact_by_type_and_id with URL inference when artifact_type is empty."""
        store = RegistryStorage()
        # Create a package with empty artifact_type to test URL inference
        package = Package(
            id="test-1",
            artifact_type="",  # Empty string to trigger URL inference
            name="test",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={"url": "https://huggingface.co/datasets/test/dataset"},
        )
        store.create_package(package)

        # Should infer "dataset" from URL
        result = store.get_artifact_by_type_and_id("dataset", "test-1")
        assert result == package
        
        # Test code type inference
        code_pkg = Package(
            id="code-1",
            artifact_type="",  # Empty to trigger inference
            name="code",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={"url": "https://github.com/test/repo"},
        )
        store.create_package(code_pkg)
        result = store.get_artifact_by_type_and_id("code", "code-1")
        assert result == code_pkg

    def test_record_event(self) -> None:
        """Test recording events."""
        store = RegistryStorage()
        package = Package(
            id="test-1",
            artifact_type="model",
            name="test",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={},
        )

        store.record_event("package_uploaded", package=package, actor="user")
        assert len(store._activity_log) == 1
        assert len(store._log_entries) == 1

    def test_record_event_with_message(self) -> None:
        """Test recording event with custom message."""
        store = RegistryStorage()
        store.record_event("custom_event", message="Custom message", actor="user")
        assert len(store._activity_log) == 1
        event = store._activity_log[0]
        assert event["message"] == "Custom message"

    def test_get_activity_summary(self) -> None:
        """Test getting activity summary."""
        store = RegistryStorage()
        package = Package(
            id="test-1",
            artifact_type="model",
            name="test",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={},
        )

        store.record_event("package_uploaded", package=package)
        store.record_event("model_ingested", package=package)

        summary = store.get_activity_summary(window_minutes=60)
        assert summary["total_events"] == 2
        assert summary["counts"]["package_uploaded"] == 1
        assert summary["counts"]["model_ingested"] == 1

    def test_get_recent_logs(self) -> None:
        """Test getting recent logs."""
        store = RegistryStorage()
        store.record_event("package_uploaded", level="INFO")
        store.record_event("model_ingested", level="WARNING")

        logs = store.get_recent_logs(limit=10)
        assert len(logs) == 2

    def test_get_recent_logs_with_level_filter(self) -> None:
        """Test getting recent logs with level filter."""
        store = RegistryStorage()
        store.record_event("package_uploaded", level="INFO")
        store.record_event("model_ingested", level="WARNING")

        logs = store.get_recent_logs(limit=10, level="INFO")
        assert len(logs) == 1
        assert logs[0]["level"] == "INFO"

    def test_default_event_message_package_uploaded(self) -> None:
        """Test default message for package_uploaded."""
        store = RegistryStorage()
        package = Package(
            id="test-1",
            artifact_type="model",
            name="test-model",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={},
        )
        store.record_event("package_uploaded", package=package)
        event = store._activity_log[0]
        assert "Uploaded package" in event["message"]
        assert "test-model" in event["message"]

    def test_default_event_message_model_ingested(self) -> None:
        """Test default message for model_ingested."""
        store = RegistryStorage()
        package = Package(
            id="test-1",
            artifact_type="model",
            name="test-model",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={},
        )
        store.record_event("model_ingested", package=package)
        event = store._activity_log[0]
        assert "Ingested model package" in event["message"]

    def test_default_event_message_package_deleted(self) -> None:
        """Test default message for package_deleted."""
        store = RegistryStorage()
        package = Package(
            id="test-1",
            artifact_type="model",
            name="test-model",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={},
        )
        store.record_event("package_deleted", package=package)
        event = store._activity_log[0]
        assert "Deleted package" in event["message"]

    def test_default_event_message_metrics_evaluated(self) -> None:
        """Test default message for metrics_evaluated."""
        store = RegistryStorage()
        package = Package(
            id="test-1",
            artifact_type="model",
            name="test-model",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={},
        )
        store.record_event(
            "metrics_evaluated",
            package=package,
            details={"metrics": ["ramp_up_time", "bus_factor"]},
        )
        event = store._activity_log[0]
        assert "Computed metrics" in event["message"]
        assert "ramp_up_time" in event["message"]

    def test_default_event_message_registry_reset(self) -> None:
        """Test default message for registry_reset."""
        store = RegistryStorage()
        store.record_event("registry_reset", details={"initiator": "admin"})
        event = store._activity_log[0]
        assert "Registry reset initiated by admin" in event["message"]

    def test_default_event_message_unknown_event(self) -> None:
        """Test default message for unknown event type."""
        store = RegistryStorage()
        package = Package(
            id="test-1",
            artifact_type="model",
            name="test-model",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={},
        )
        store.record_event("unknown_event", package=package)
        event = store._activity_log[0]
        assert "Unknown Event" in event["message"]

    def test_format_package_message_with_source(self) -> None:
        """Test formatting message with source."""
        store = RegistryStorage()
        package = Package(
            id="test-1",
            artifact_type="model",
            name="test-model",
            version="1.0.0",
            uploaded_by="user",
            upload_timestamp=datetime.now(timezone.utc),
            size_bytes=100,
            metadata={},
        )
        store.record_event(
            "package_uploaded", package=package, details={"source": "api"}
        )
        event = store._activity_log[0]
        assert "(source: api)" in event["message"]

    def test_create_user(self) -> None:
        """Test creating a user."""
        store = RegistryStorage()
        user = User(
            user_id=str(uuid.uuid4()),
            username="testuser",
            password_hash="hash",
            permissions=["upload"],
        )
        result = store.create_user(user)
        assert result == user
        assert store.get_user("testuser") == user

    def test_get_user(self) -> None:
        """Test getting a user."""
        store = RegistryStorage()
        user = User(
            user_id=str(uuid.uuid4()),
            username="testuser",
            password_hash="hash",
            permissions=[],
        )
        store.create_user(user)
        assert store.get_user("testuser") == user
        assert store.get_user("nonexistent") is None

    def test_get_user_by_id(self) -> None:
        """Test getting user by ID."""
        store = RegistryStorage()
        user_id = str(uuid.uuid4())
        user = User(
            user_id=user_id,
            username="testuser",
            password_hash="hash",
            permissions=[],
        )
        store.create_user(user)
        assert store.get_user_by_id(user_id) == user
        assert store.get_user_by_id("nonexistent") is None

    def test_delete_user(self) -> None:
        """Test deleting a user and invalidating tokens."""
        store = RegistryStorage()
        user = User(
            user_id=str(uuid.uuid4()),
            username="testuser",
            password_hash="hash",
            permissions=[],
        )
        store.create_user(user)

        token_info = TokenInfo(
            token="test-token",
            user_id=user.user_id,
            username="testuser",
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        store.create_token(token_info)

        deleted = store.delete_user("testuser")
        assert deleted == user
        assert store.get_user("testuser") is None
        assert store.get_token("test-token") is None

    def test_list_users(self) -> None:
        """Test listing all users."""
        store = RegistryStorage()
        user1 = User(
            user_id=str(uuid.uuid4()),
            username="user1",
            password_hash="hash",
            permissions=[],
        )
        user2 = User(
            user_id=str(uuid.uuid4()),
            username="user2",
            password_hash="hash",
            permissions=[],
        )
        store.create_user(user1)
        store.create_user(user2)

        users = store.list_users()
        assert len(users) >= 2  # At least 2, plus default admin

    def test_create_token(self) -> None:
        """Test creating a token."""
        store = RegistryStorage()
        token_info = TokenInfo(
            token="test-token",
            user_id=str(uuid.uuid4()),
            username="testuser",
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        result = store.create_token(token_info)
        assert result == token_info
        assert store.get_token("test-token") == token_info

    def test_get_token_expired(self) -> None:
        """Test getting an expired token."""
        store = RegistryStorage()
        token_info = TokenInfo(
            token="expired-token",
            user_id=str(uuid.uuid4()),
            username="testuser",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        store.create_token(token_info)

        result = store.get_token("expired-token")
        assert result is None
        # Token should be removed
        assert store.get_token("expired-token") is None

    def test_get_token_not_expired(self) -> None:
        """Test getting a non-expired token."""
        store = RegistryStorage()
        token_info = TokenInfo(
            token="valid-token",
            user_id=str(uuid.uuid4()),
            username="testuser",
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        store.create_token(token_info)

        result = store.get_token("valid-token")
        assert result == token_info

    def test_increment_token_usage(self) -> None:
        """Test incrementing token usage."""
        store = RegistryStorage()
        token_info = TokenInfo(
            token="test-token",
            user_id=str(uuid.uuid4()),
            username="testuser",
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        store.create_token(token_info)

        success = store.increment_token_usage("test-token")
        assert success is True
        assert store.get_token("test-token").usage_count == 1

    def test_increment_token_usage_invalid_token(self) -> None:
        """Test incrementing usage for invalid token."""
        store = RegistryStorage()
        success = store.increment_token_usage("nonexistent")
        assert success is False

    def test_invalidate_token(self) -> None:
        """Test invalidating a token."""
        store = RegistryStorage()
        token_info = TokenInfo(
            token="test-token",
            user_id=str(uuid.uuid4()),
            username="testuser",
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        store.create_token(token_info)

        success = store.invalidate_token("test-token")
        assert success is True
        assert store.get_token("test-token") is None

    def test_invalidate_token_nonexistent(self) -> None:
        """Test invalidating a nonexistent token."""
        store = RegistryStorage()
        success = store.invalidate_token("nonexistent")
        assert success is False
