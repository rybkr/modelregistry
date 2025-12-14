"""Unit tests for Reviewedness metric.

This module contains unit tests for the Reviewedness metric, which evaluates
code review coverage and quality in a repository. Tests cover GitHub URL
extraction, pull request analysis, code review detection, meaningful review
assessment, lines of code counting, and overall reviewedness scoring.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from metrics.reviewedness import (
    EXCLUDED_EXTENSIONS,
    Reviewedness,
    try_readme,
)
from models import Model
from resources.code_resource import CodeResource
from resources.model_resource import ModelResource


class TestTryReadme:
    """Test cases for the try_readme function."""

    def test_try_readme_returns_contents(self) -> None:
        """Ensure try_readme fetches README contents when available."""
        repo = MagicMock()
        repo.exists.return_value = True
        repo.read_text.return_value = "# README\ncontents"

        @contextmanager
        def fake_open_files(allow_patterns=None):
            assert allow_patterns == ["README.md"]
            yield repo

        class DummyResource:
            def open_files(self, allow_patterns=None):
                return fake_open_files(allow_patterns)

        result = try_readme(DummyResource())

        repo.exists.assert_called_once_with("README.md")
        repo.read_text.assert_called_once_with("README.md")
        assert result == "# README\ncontents"

    def test_try_readme_handles_missing_file(self) -> None:
        """Return None when README.md doesn't exist."""
        repo = MagicMock()
        repo.exists.return_value = False

        @contextmanager
        def fake_open_files(allow_patterns=None):
            yield repo

        class DummyResource:
            def open_files(self, allow_patterns=None):
                return fake_open_files(allow_patterns)

        result = try_readme(DummyResource())
        assert result is None

    def test_try_readme_handles_exceptions(self) -> None:
        """Return None when resource.open_files raises an exception."""

        class FailingResource:
            def open_files(self, allow_patterns=None):
                raise RuntimeError("boom")

        assert try_readme(FailingResource()) is None

    def test_try_readme_handles_read_exception(self) -> None:
        """Return None when read_text raises an exception."""
        repo = MagicMock()
        repo.exists.return_value = True
        repo.read_text.side_effect = IOError("read failed")

        @contextmanager
        def fake_open_files(allow_patterns=None):
            yield repo

        class DummyResource:
            def open_files(self, allow_patterns=None):
                return fake_open_files(allow_patterns)

        result = try_readme(DummyResource())
        assert result is None


class TestReviewedness:
    """Test cases for the Reviewedness metric."""

    def test_init(self) -> None:
        """Test Reviewedness initialization."""
        metric = Reviewedness()
        assert metric.name == "reviewedness"
        assert metric.github_token is None or isinstance(metric.github_token, str)

    def test_is_github_url(self) -> None:
        """Test _is_github_url method."""
        metric = Reviewedness()
        assert metric._is_github_url("https://github.com/owner/repo")
        assert metric._is_github_url("https://GITHUB.COM/owner/repo")
        assert metric._is_github_url("http://github.com/owner/repo")
        assert not metric._is_github_url("https://gitlab.com/owner/repo")
        assert not metric._is_github_url("https://example.com")

    def test_normalize_github_url(self) -> None:
        """Test _normalize_github_url method."""
        metric = Reviewedness()
        assert metric._normalize_github_url("https://github.com/owner/repo") == [
            "https://github.com/owner/repo"
        ]
        assert metric._normalize_github_url(
            "https://github.com/owner/repo/tree/main"
        ) == ["https://github.com/owner/repo"]
        assert metric._normalize_github_url(
            "https://github.com/owner/repo?query=test"
        ) == ["https://github.com/owner/repo"]
        assert metric._normalize_github_url(
            "https://github.com/owner/repo#section"
        ) == ["https://github.com/owner/repo"]
        assert metric._normalize_github_url("") == []
        assert metric._normalize_github_url("not-a-url") == []

    def test_extract_github_urls_from_text_markdown_link(self) -> None:
        """Test extracting GitHub URLs from markdown links."""
        metric = Reviewedness()
        text = "Check out [the repo](https://github.com/owner/repo)"
        urls = metric._extract_github_urls_from_text(text)
        assert "https://github.com/owner/repo" in urls

    def test_extract_github_urls_from_text_html_link(self) -> None:
        """Test extracting GitHub URLs from HTML links."""
        metric = Reviewedness()
        text = '<a href="https://github.com/owner/repo">Link</a>'
        urls = metric._extract_github_urls_from_text(text)
        assert "https://github.com/owner/repo" in urls

    def test_extract_github_urls_from_text_plain_url(self) -> None:
        """Test extracting plain GitHub URLs."""
        metric = Reviewedness()
        text = "Visit https://github.com/owner/repo for more info"
        urls = metric._extract_github_urls_from_text(text)
        assert "https://github.com/owner/repo" in urls

    def test_extract_github_urls_from_text_no_protocol(self) -> None:
        """Test extracting GitHub URLs without protocol."""
        metric = Reviewedness()
        text = "Check github.com/owner/repo"
        urls = metric._extract_github_urls_from_text(text)
        assert "https://github.com/owner/repo" in urls

    def test_extract_github_urls_from_text_paren_url(self) -> None:
        """Test extracting GitHub URLs in parentheses."""
        metric = Reviewedness()
        text = "(https://github.com/owner/repo)"
        urls = metric._extract_github_urls_from_text(text)
        assert "https://github.com/owner/repo" in urls

    def test_extract_github_urls_from_text_deduplicates(self) -> None:
        """Test that duplicate URLs are deduplicated."""
        metric = Reviewedness()
        text = "https://github.com/owner/repo and https://github.com/owner/repo"
        urls = metric._extract_github_urls_from_text(text)
        assert urls == ["https://github.com/owner/repo"]

    def test_extract_owner_repo(self) -> None:
        """Test _extract_owner_repo method."""
        metric = Reviewedness()
        assert metric._extract_owner_repo("https://github.com/owner/repo") == (
            "owner",
            "repo",
        )
        assert metric._extract_owner_repo("https://github.com/org/sub/repo") == (
            "org",
            "sub",
        )
        assert metric._extract_owner_repo("invalid-url") is None
        assert metric._extract_owner_repo("https://github.com/owner") is None

    def test_has_code_review(self) -> None:
        """Test _has_code_review method."""
        metric = Reviewedness()
        assert metric._has_code_review([{"state": "APPROVED"}])
        assert metric._has_code_review([{"state": "CHANGES_REQUESTED"}])
        assert not metric._has_code_review([{"state": "COMMENTED"}])
        assert not metric._has_code_review([])
        assert not metric._has_code_review([{"state": "DISMISSED"}])

    def test_has_meaningful_review(self) -> None:
        """Test _has_meaningful_review method."""
        metric = Reviewedness()
        # Approved review
        assert metric._has_meaningful_review([{"state": "APPROVED"}])
        # Changes requested
        assert metric._has_meaningful_review([{"state": "CHANGES_REQUESTED"}])
        # Dismissed review
        assert metric._has_meaningful_review([{"state": "DISMISSED"}])
        # Commented review (at least one)
        assert metric._has_meaningful_review([{"state": "COMMENTED"}])
        # Multiple comments
        assert metric._has_meaningful_review(
            [{"state": "COMMENTED"}, {"state": "COMMENTED"}]
        )
        # No reviews
        assert not metric._has_meaningful_review([])
        # Case insensitive
        assert metric._has_meaningful_review([{"state": "approved"}])
        assert metric._has_meaningful_review([{"state": "changes_requested"}])

    def test_should_exclude_file(self, tmp_path: Path) -> None:
        """Test _should_exclude_file method."""
        metric = Reviewedness()
        # Test excluded extensions
        for ext in EXCLUDED_EXTENSIONS:
            file_path = tmp_path / f"test{ext}"
            file_path.touch()
            assert metric._should_exclude_file(file_path)

        # Test large file
        large_file = tmp_path / "large.txt"
        large_file.write_bytes(b"x" * (11 * 1024 * 1024))  # 11MB
        assert metric._should_exclude_file(large_file)

        # Test normal file
        normal_file = tmp_path / "normal.py"
        normal_file.write_text("print('hello')")
        assert not metric._should_exclude_file(normal_file)

        # Test file that doesn't exist (should handle gracefully)
        missing_file = tmp_path / "missing.txt"
        assert not metric._should_exclude_file(missing_file)

    def test_count_loc_in_repo(self, tmp_path: Path) -> None:
        """Test _count_loc_in_repo method."""
        metric = Reviewedness()
        # Create test files
        (tmp_path / "file1.py").write_text("line1\nline2\nline3")
        (tmp_path / "file2.py").write_text("line1\nline2")
        (tmp_path / ".git").mkdir()  # Should be skipped
        (tmp_path / ".git" / "config").write_text("config")
        (tmp_path / "node_modules").mkdir()  # Should be skipped
        (tmp_path / "node_modules" / "lib.js").write_text("code")
        (tmp_path / ".hidden").write_text("hidden")  # Should be skipped

        loc = metric._count_loc_in_repo(tmp_path)
        assert loc == 5  # 3 + 2 lines

    def test_count_loc_in_repo_excludes_binaries(self, tmp_path: Path) -> None:
        """Test that binary files are excluded from LOC counting."""
        metric = Reviewedness()
        (tmp_path / "file.py").write_text("line1\nline2")
        (tmp_path / "file.bin").write_bytes(b"binary data")
        (tmp_path / "file.pt").write_bytes(b"pytorch model")

        loc = metric._count_loc_in_repo(tmp_path)
        assert loc == 2  # Only .py file counted

    def test_find_github_url_in_model_card_from_readme(self) -> None:
        """Test finding GitHub URL in model card README."""
        metric = Reviewedness()
        readme_content = "Code available at https://github.com/owner/repo"

        model_resource = MagicMock()
        model_resource.open_files = MagicMock(
            return_value=contextmanager(lambda: MagicMock(
                exists=lambda x: x == "README.md",
                read_text=lambda x: readme_content if x == "README.md" else ""
            ))()
        )

        model = MagicMock()
        model.model = model_resource

        with patch("metrics.reviewedness.try_readme", return_value=readme_content):
            url = metric._find_github_url_in_model_card(model)
            assert url == "https://github.com/owner/repo"

    def test_find_github_url_in_model_card_from_metadata(self) -> None:
        """Test finding GitHub URL in model metadata."""
        metric = Reviewedness()
        metadata = {
            "description": "Model code at https://github.com/owner/repo",
        }

        model_resource = MagicMock()
        model_resource.fetch_metadata.return_value = metadata

        model = MagicMock()
        model.model = model_resource

        with patch("metrics.reviewedness.try_readme", return_value=None):
            url = metric._find_github_url_in_model_card(model)
            assert url == "https://github.com/owner/repo"

    def test_find_github_url_in_model_card_from_card_data(self) -> None:
        """Test finding GitHub URL in card_data field."""
        metric = Reviewedness()
        metadata = {
            "card_data": {
                "content": "See https://github.com/owner/repo for code",
            },
        }

        model_resource = MagicMock()
        model_resource.fetch_metadata.return_value = metadata

        model = MagicMock()
        model.model = model_resource

        with patch("metrics.reviewedness.try_readme", return_value=None):
            url = metric._find_github_url_in_model_card(model)
            assert url == "https://github.com/owner/repo"

    def test_find_github_url_in_model_card_not_found(self) -> None:
        """Test when no GitHub URL is found."""
        metric = Reviewedness()
        model_resource = MagicMock()
        model_resource.fetch_metadata.return_value = {}

        model = MagicMock()
        model.model = model_resource

        with patch("metrics.reviewedness.try_readme", return_value=None):
            url = metric._find_github_url_in_model_card(model)
            assert url is None

    def test_find_github_url_in_model_card_metadata_exception(self) -> None:
        """Test handling exception when fetching metadata."""
        metric = Reviewedness()
        model_resource = MagicMock()
        model_resource.fetch_metadata.side_effect = Exception("API error")

        model = MagicMock()
        model.model = model_resource

        with patch("metrics.reviewedness.try_readme", return_value=None):
            url = metric._find_github_url_in_model_card(model)
            assert url is None

    def test_compute_no_github_url(self) -> None:
        """Test compute when no GitHub URL is found."""
        metric = Reviewedness()
        model = Model(
            model=ModelResource("https://huggingface.co/org/model"),
            code=None,
        )

        with patch.object(metric, "_find_github_url_in_model_card", return_value=None):
            metric.compute(model)

        assert metric.value == 0.0
        assert "error" in metric.details
        assert "No GitHub repository found" in metric.details["error"]

    def test_compute_invalid_github_url(self) -> None:
        """Test compute with invalid GitHub URL."""
        metric = Reviewedness()
        model = Model(
            model=ModelResource("https://huggingface.co/org/model"),
            code=CodeResource("https://github.com/invalid"),
        )

        metric.compute(model)

        assert metric.value == 0.0
        assert "error" in metric.details
        assert "Could not parse GitHub URL" in metric.details["error"]

    def test_compute_repository_not_found(self) -> None:
        """Test compute when repository is not found (404)."""
        metric = Reviewedness()
        model = Model(
            model=ModelResource("https://huggingface.co/org/model"),
            code=CodeResource("https://github.com/owner/repo"),
        )

        github_client = MagicMock()
        github_client.get_pull_requests.side_effect = Exception(
            "404 Repository not found"
        )

        with patch("metrics.reviewedness.GitHubClient", return_value=github_client):
            metric.compute(model)

        assert metric.value == 0.0
        assert "error" in metric.details
        assert "Repository not found" in metric.details["error"]

    def test_compute_rate_limit_error(self) -> None:
        """Test compute when GitHub API rate limit is exceeded."""
        metric = Reviewedness()
        model = Model(
            model=ModelResource("https://huggingface.co/org/model"),
            code=CodeResource("https://github.com/owner/repo"),
        )

        github_client = MagicMock()
        github_client.get_pull_requests.side_effect = Exception(
            "403 Rate limit exceeded"
        )

        with patch("metrics.reviewedness.GitHubClient", return_value=github_client):
            metric.compute(model)

        assert metric.value == 0.0
        assert "error" in metric.details
        assert "rate limit" in metric.details["error"].lower()
        assert metric.details.get("rate_limited") is True

    def test_compute_no_merged_prs(self) -> None:
        """Test compute when there are no merged PRs."""
        metric = Reviewedness()
        model = Model(
            model=ModelResource("https://huggingface.co/org/model"),
            code=CodeResource("https://github.com/owner/repo"),
        )

        github_client = MagicMock()
        github_client.get_pull_requests.return_value = [
            {"number": 1, "merged_at": None},
            {"number": 2, "merged_at": None},
        ]

        with patch("metrics.reviewedness.GitHubClient", return_value=github_client):
            metric.compute(model)

        assert metric.value == 0.0
        assert metric.details["merged_prs"] == 0
        assert "No merged pull requests found" in metric.details["reason"]

    def test_compute_all_prs_reviewed(self) -> None:
        """Test compute when all merged PRs have reviews."""
        metric = Reviewedness()
        model = Model(
            model=ModelResource("https://huggingface.co/org/model"),
            code=CodeResource("https://github.com/owner/repo"),
        )

        github_client = MagicMock()
        github_client.get_pull_requests.return_value = [
            {"number": 1, "merged_at": "2024-01-01T00:00:00Z", "title": "PR 1"},
            {"number": 2, "merged_at": "2024-01-02T00:00:00Z", "title": "PR 2"},
        ]
        github_client.get_pull_request_reviews.return_value = [
            {"state": "APPROVED"}
        ]

        with patch("metrics.reviewedness.GitHubClient", return_value=github_client):
            metric.compute(model)

        assert metric.value == 1.0
        assert metric.details["merged_prs"] == 2
        assert metric.details["reviewed_prs"] == 2
        assert metric.details["reviewedness"] == 1.0

    def test_compute_some_prs_reviewed(self) -> None:
        """Test compute when some merged PRs have reviews."""
        metric = Reviewedness()
        model = Model(
            model=ModelResource("https://huggingface.co/org/model"),
            code=CodeResource("https://github.com/owner/repo"),
        )

        github_client = MagicMock()
        github_client.get_pull_requests.return_value = [
            {"number": 1, "merged_at": "2024-01-01T00:00:00Z", "title": "PR 1"},
            {"number": 2, "merged_at": "2024-01-02T00:00:00Z", "title": "PR 2"},
            {"number": 3, "merged_at": "2024-01-03T00:00:00Z", "title": "PR 3"},
        ]

        def get_reviews(owner, repo, pr_number, **kwargs):
            if pr_number == 1:
                return [{"state": "APPROVED"}]
            elif pr_number == 2:
                return []
            else:
                return [{"state": "COMMENTED"}]

        github_client.get_pull_request_reviews.side_effect = get_reviews

        with patch("metrics.reviewedness.GitHubClient", return_value=github_client):
            metric.compute(model)

        assert metric.value == pytest.approx(2.0 / 3.0, abs=0.01)
        assert metric.details["merged_prs"] == 3
        assert metric.details["reviewed_prs"] == 2

    def test_compute_no_prs_reviewed(self) -> None:
        """Test compute when no merged PRs have reviews."""
        metric = Reviewedness()
        model = Model(
            model=ModelResource("https://huggingface.co/org/model"),
            code=CodeResource("https://github.com/owner/repo"),
        )

        github_client = MagicMock()
        github_client.get_pull_requests.return_value = [
            {"number": 1, "merged_at": "2024-01-01T00:00:00Z", "title": "PR 1"},
            {"number": 2, "merged_at": "2024-01-02T00:00:00Z", "title": "PR 2"},
        ]
        github_client.get_pull_request_reviews.return_value = []

        with patch("metrics.reviewedness.GitHubClient", return_value=github_client):
            metric.compute(model)

        assert metric.value == 0.0
        assert metric.details["merged_prs"] == 2
        assert metric.details["reviewed_prs"] == 0

    def test_compute_pr_without_number(self) -> None:
        """Test compute when PR doesn't have a number field."""
        metric = Reviewedness()
        model = Model(
            model=ModelResource("https://huggingface.co/org/model"),
            code=CodeResource("https://github.com/owner/repo"),
        )

        github_client = MagicMock()
        github_client.get_pull_requests.return_value = [
            {"merged_at": "2024-01-01T00:00:00Z", "title": "PR 1"},
        ]

        with patch("metrics.reviewedness.GitHubClient", return_value=github_client):
            metric.compute(model)

        # PR without number should be skipped in review check, but still counted in merged_prs
        assert metric.details["merged_prs"] == 1
        assert metric.details["reviewed_prs"] == 0

    def test_compute_review_fetch_error(self) -> None:
        """Test compute when fetching reviews fails for a PR."""
        metric = Reviewedness()
        model = Model(
            model=ModelResource("https://huggingface.co/org/model"),
            code=CodeResource("https://github.com/owner/repo"),
        )

        github_client = MagicMock()
        github_client.get_pull_requests.return_value = [
            {"number": 1, "merged_at": "2024-01-01T00:00:00Z", "title": "PR 1"},
            {"number": 2, "merged_at": "2024-01-02T00:00:00Z", "title": "PR 2"},
        ]

        def get_reviews(owner, repo, pr_number, **kwargs):
            if pr_number == 1:
                raise Exception("API error")
            return [{"state": "APPROVED"}]

        github_client.get_pull_request_reviews.side_effect = get_reviews

        with patch("metrics.reviewedness.GitHubClient", return_value=github_client):
            metric.compute(model)

        # PR with review error should be treated as unreviewed
        assert metric.details["merged_prs"] == 2
        assert metric.details["reviewed_prs"] == 1
        assert metric.details["failed_review_checks"] == 1

    def test_compute_general_exception(self) -> None:
        """Test compute when a general exception occurs."""
        metric = Reviewedness()
        model = Model(
            model=ModelResource("https://huggingface.co/org/model"),
            code=CodeResource("https://github.com/owner/repo"),
        )

        with patch.object(
            metric, "_extract_owner_repo", side_effect=Exception("Unexpected error")
        ):
            metric.compute(model)

        assert metric.value == 0.0
        assert "error" in metric.details

    def test_compute_uses_code_url_first(self) -> None:
        """Test that code URL is used before searching model card."""
        metric = Reviewedness()
        model = Model(
            model=ModelResource("https://huggingface.co/org/model"),
            code=CodeResource("https://github.com/owner/repo"),
        )

        github_client = MagicMock()
        github_client.get_pull_requests.return_value = []
        github_client.get_pull_request_reviews.return_value = []

        with patch("metrics.reviewedness.GitHubClient", return_value=github_client):
            metric.compute(model)

        # Should use code URL, not search model card
        github_client.get_pull_requests.assert_called_once()
        assert metric.details["url"] == "https://github.com/owner/repo"

    def test_compute_uses_model_card_when_no_code_url(self) -> None:
        """Test that model card is searched when no code URL."""
        metric = Reviewedness()
        model = Model(
            model=ModelResource("https://huggingface.co/org/model"),
            code=None,
        )

        github_client = MagicMock()
        github_client.get_pull_requests.return_value = []
        github_client.get_pull_request_reviews.return_value = []

        with patch("metrics.reviewedness.GitHubClient", return_value=github_client):
            with patch.object(
                metric,
                "_find_github_url_in_model_card",
                return_value="https://github.com/owner/repo",
            ):
                metric.compute(model)

        assert metric.details["url"] == "https://github.com/owner/repo"

    def test_compute_handles_non_github_code_url(self) -> None:
        """Test that non-GitHub code URLs are ignored."""
        metric = Reviewedness()
        model = Model(
            model=ModelResource("https://huggingface.co/org/model"),
            code=CodeResource("https://gitlab.com/owner/repo"),
        )

        with patch.object(metric, "_find_github_url_in_model_card", return_value=None):
            metric.compute(model)

        assert metric.value == 0.0
        assert "No GitHub repository found" in metric.details["error"]

    def test_extract_owner_repo_handles_exception(self) -> None:
        """Test _extract_owner_repo handles exceptions during parsing."""
        metric = Reviewedness()

        # Mock urlparse to raise an exception
        with patch("metrics.reviewedness.urlparse", side_effect=Exception("Parse error")):
            result = metric._extract_owner_repo("https://github.com/owner/repo")
            assert result is None

    def test_count_loc_in_repo_handles_file_read_errors(self, tmp_path: Path) -> None:
        """Test _count_loc_in_repo handles file read errors gracefully."""
        metric = Reviewedness()
        # Create a file that will cause a read error
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2")

        # Mock open to raise an exception
        with patch("builtins.open", side_effect=PermissionError("Access denied")):
            loc = metric._count_loc_in_repo(tmp_path)
            # Should handle the error and continue
            assert loc == 0

    def test_compute_handles_general_pr_fetch_error(self) -> None:
        """Test compute handles general error when fetching PRs (not 404 or rate limit)."""
        metric = Reviewedness()
        model = Model(
            model=ModelResource("https://huggingface.co/org/model"),
            code=CodeResource("https://github.com/owner/repo"),
        )

        github_client = MagicMock()
        github_client.get_pull_requests.side_effect = Exception("500 Internal Server Error")

        with patch("metrics.reviewedness.GitHubClient", return_value=github_client):
            metric.compute(model)

        assert metric.value == 0.0
        assert "error" in metric.details
        assert "Could not fetch pull requests" in metric.details["error"]
        assert "url" in metric.details
