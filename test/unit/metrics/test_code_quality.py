"""Unit tests for CodeQuality metric.

This module contains unit tests for the CodeQuality metric, which evaluates
code quality through static analysis (flake8, mypy) and repository popularity
signals. Tests cover linting execution, error counting, popularity scoring,
and overall metric computation.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal, Optional, Type
from unittest.mock import MagicMock, patch

from metrics.code_quality import CodeQuality, try_readme
from models import Model
from resources.code_resource import CodeResource
from resources.model_resource import ModelResource


class DummyRepo:
    """A dummy repository class for testing purposes.

    This class simulates a repository context manager, allowing tests to
    mock repository operations without accessing real repositories.

    Attributes:
        root (Path): The root directory of the dummy repository.
    """

    def __init__(self, root: Path) -> None:
        """Initialize the DummyRepo with a root directory.

        Args:
            root (Path): The root directory of the dummy repository.
        """
        self.root = root

    def __enter__(self) -> DummyRepo:
        """Enter the context of the dummy repository.

        Returns:
            DummyRepo: The current instance of the dummy repository.
        """
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Any,
    ) -> Literal[False]:
        """Exit the context of the dummy repository.

        Args:
            exc_type (Optional[Type[BaseException]]): The exception type, if any.
            exc (Optional[BaseException]): The exception instance, if any.
            tb (Any): The traceback object, if any.

        Returns:
            Literal[False]: Returns False to indicate exceptions are not suppressed.
        """
        return False


class TestCodeQuality:
    """Test cases for the CodeQuality metric."""

    def test_code_quality_computes_scores(
        self, monkeypatch: Any, tmp_path: Path
    ) -> None:
        """Test CodeQuality computes combined score with patched linters and stars."""

        def fake_open_codebase(url: str) -> DummyRepo:
            return DummyRepo(tmp_path)

        # Patch open_codebase so we don’t actually fetch anything
        monkeypatch.setattr("metrics.code_quality.open_codebase", fake_open_codebase)

        # Patch linters to fixed values
        monkeypatch.setattr(CodeQuality, "_flake8_score", lambda self, repo: 0.8)
        monkeypatch.setattr(CodeQuality, "_mypy_score", lambda self, repo: 0.6)

        # Patch CodeResource metadata to simulate GitHub stars
        with patch(
            "metrics.code_quality.CodeResource.fetch_metadata",
            return_value={"stargazers_count": 24},
        ):
            metric = CodeQuality()
            fake_model = Model(
                code=CodeResource("https://github.com/some/repo"),
                model=ModelResource("https://huggingface.co/some/model"),
            )

            # Act
            metric.compute(fake_model)

        # Assert
        assert isinstance(metric.value, float)
        assert 0.0 <= metric.value <= 1.0
        assert metric.details["flake8"] == 0.8
        assert metric.details["mypy"] == 0.6
        assert metric.details["stars"] == 0.5  # 24 stars → normalized to 0.5

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

    def test_try_readme_handles_exceptions(self) -> None:
        """Return None when resource.open_files raises an exception."""

        class FailingResource:
            def open_files(self, allow_patterns=None):
                raise RuntimeError("boom")

        assert try_readme(FailingResource()) is None

    def test_compute_partial_credit_when_readme_mentions_code(
        self, monkeypatch: Any
    ) -> None:
        """Assign partial credit if README references code but no URL is provided."""
        metric = CodeQuality()
        fake_model = Model(
            model=ModelResource("https://huggingface.co/org/model"),
            code=None,
        )

        monkeypatch.setattr(
            "metrics.code_quality.try_readme",
            lambda resource: "The code is available on GitHub at repo link.",
        )

        metric.compute(fake_model)

        assert metric.value == 0.6
        assert metric.details == {
            "partial_credit": True,
            "reason": "Code mentioned in README but no code URL provided",
        }

    def test_compute_returns_zero_without_code_or_readme(
        self, monkeypatch: Any
    ) -> None:
        """Return zero score when no code URL or README mention is found."""
        metric = CodeQuality()
        fake_model = Model(
            model=ModelResource("https://huggingface.co/org/model"),
            code=None,
        )

        monkeypatch.setattr("metrics.code_quality.try_readme", lambda resource: None)

        metric.compute(fake_model)

        assert metric.value == 0.0
        assert metric.details == {"error": "No code URL provided"}

    def test_compute_handles_exceptions_during_analysis(self, monkeypatch: Any) -> None:
        """Gracefully handle exceptions thrown while opening the codebase."""
        metric = CodeQuality()
        fake_model = Model(
            code=CodeResource("https://github.com/org/repo"),
            model=ModelResource("https://huggingface.co/org/model"),
        )

        @contextmanager
        def failing_open_codebase(url: str):
            raise RuntimeError("boom")
            yield  # pragma: no cover

        monkeypatch.setattr("metrics.code_quality.open_codebase", failing_open_codebase)

        metric.compute(fake_model)

        assert metric.value == 0.0
        assert metric.details == {"error": "boom"}
