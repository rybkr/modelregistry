from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Literal, Optional, Type
from unittest.mock import MagicMock

import pytest

from metrics.dataset_and_code import DatasetAndCode, try_readme
from models import Model
from resources.code_resource import CodeResource
from resources.model_resource import ModelResource


class DummyRepo:
    """A dummy repository context manager for testing."""

    def __init__(self) -> None:
        self.root = "/tmp/repo"

    def __enter__(self) -> DummyRepo:
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Any,
    ) -> Literal[False]:
        return False


class TestDatasetAndCode:
    """Test suite for the DatasetAndCode metric."""

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

    def test_compute_uses_keyword_minimums(self, monkeypatch: Any) -> None:
        """Use keyword-derived minimum scores when GenAI response is lower."""
        metric = DatasetAndCode()
        fake_model = Model(
            model=ModelResource("https://huggingface.co/org/model-one"),
            code=CodeResource("https://github.com/org/code-one"),
        )

        def fake_try_readme(resource):
            if isinstance(resource, ModelResource):
                return "Dataset description with splits and example code script."
            if isinstance(resource, CodeResource):
                return "Example notebook showing dataset loading and code walkthrough."
            return None

        responses = iter(
            [
                {"score": 0.5, "justification": "low model"},
                {"score": 0.5, "justification": "low code"},
            ]
        )

        monkeypatch.setattr("metrics.dataset_and_code.try_readme", fake_try_readme)
        monkeypatch.setattr(
            "metrics.dataset_and_code._query_genai", lambda prompt: next(responses)
        )

        metric.compute(fake_model)

        assert metric.details["model"]["score"] == 0.7
        assert metric.details["code"]["score"] == 0.7

    def test_compute_keyword_fallback_on_api_error(self, monkeypatch: Any) -> None:
        """Fallback to keyword-based minimum when the API call fails."""
        metric = DatasetAndCode()
        fake_model = Model(
            model=ModelResource("https://huggingface.co/org/model-two"),
            code=None,
        )

        monkeypatch.setattr(
            "metrics.dataset_and_code.try_readme",
            lambda resource: "Dataset overview detailing preprocessing steps and splits.",
        )
        monkeypatch.setattr(
            "metrics.dataset_and_code._query_genai",
            lambda prompt: (_ for _ in ()).throw(RuntimeError("API down")),
        )

        metric.compute(fake_model)

        assert "API failed" in metric.details["model"]["justification"]

    def test_compute_no_readmes_defaults_to_zero(self, monkeypatch: Any) -> None:
        """Return zero score when neither model nor code README can be fetched."""
        metric = DatasetAndCode()
        fake_model = Model(
            model=ModelResource("https://huggingface.co/org/empty"),
            code=CodeResource("https://github.com/org/empty"),
        )

        monkeypatch.setattr("metrics.dataset_and_code.try_readme", lambda resource: None)

        metric.compute(fake_model)

        assert metric.value == 0.0
        assert metric.details["model"]["justification"] == "README not found"
        assert metric.details["code"]["justification"] == "README not found"

