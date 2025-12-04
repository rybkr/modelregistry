from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Literal, Optional, Type
from unittest.mock import MagicMock

import pytest

from metrics.license import License, try_readme
from models import Model
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


class TestLicenseMetric:
    """Test suite for the License metric."""

    def test_try_readme_returns_contents(self) -> None:
        """Ensure try_readme fetches README contents when available."""
        repo = MagicMock()
        repo.exists.return_value = True
        repo.read_text.return_value = "# README\nMIT License"

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
        assert result == "# README\nMIT License"

    def test_try_readme_handles_exceptions(self) -> None:
        """Return None when resource.open_files raises an exception."""

        class FailingResource:
            def open_files(self, allow_patterns=None):
                raise RuntimeError("boom")

        assert try_readme(FailingResource()) is None

    def test_compute_adjusts_score_with_keywords(self, monkeypatch: Any) -> None:
        """Use keyword-derived minimum when API score is lower."""
        metric = License()
        fake_model = Model(model=ModelResource("https://huggingface.co/org/model"))

        monkeypatch.setattr(
            "metrics.license.try_readme",
            lambda resource: "This project is licensed under the MIT License.",
        )
        monkeypatch.setattr(
            "metrics.license._query_genai",
            lambda prompt: {"score": 0.5, "justification": "low confidence"},
        )

        metric.compute(fake_model)

        assert metric.value == 0.75
        assert metric.details["model"]["score"] == 0.75
        assert "Adjusted" in metric.details["model"]["justification"]

    def test_compute_falls_back_to_keywords_on_error(self, monkeypatch: Any) -> None:
        """Return keyword-based minimum when GenAI request fails."""
        metric = License()
        fake_model = Model(model=ModelResource("https://huggingface.co/org/model"))

        monkeypatch.setattr(
            "metrics.license.try_readme",
            lambda resource: "Licensed under Apache-2.0 terms.",
        )
        monkeypatch.setattr(
            "metrics.license._query_genai",
            lambda prompt: (_ for _ in ()).throw(RuntimeError("timeout")),
        )

        metric.compute(fake_model)

        assert metric.value == 0.75
        assert metric.details["model"]["score"] == 0.75
        assert "API evaluation failed" in metric.details["model"]["justification"]

    def test_compute_without_readme_returns_zero(self, monkeypatch: Any) -> None:
        """Return zero when README cannot be fetched."""
        metric = License()
        fake_model = Model(model=ModelResource("https://huggingface.co/org/missing"))

        monkeypatch.setattr("metrics.license.try_readme", lambda resource: None)

        metric.compute(fake_model)

        assert metric.value == 0.0
        assert metric.details["model"]["justification"] == "README not found"
