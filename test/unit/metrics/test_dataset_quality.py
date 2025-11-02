from __future__ import annotations

from typing import Any, Dict, cast
from unittest.mock import MagicMock

from metrics.dataset_quality import DatasetQuality


class TestDatasetQuality:
    """Test cases for the DatasetQuality metric."""

    def test_no_dataset(self) -> None:
        """If model has no dataset, value should be 0 and error recorded."""
        dq = DatasetQuality()
        model = MagicMock()
        model.dataset = None  # simulate no dataset

        dq.compute(model)

        assert cast(float, dq.value) == 0.0
        assert "error" in dq.details

    def test_perfect_dataset(self) -> None:
        """Dataset with all fields and strong community should get a high score."""
        metadata: Dict[str, Any] = {
            "description": "Test dataset",
            "license": {"name": "MIT"},
            "homepage": "https://example.com",
            "updated_at": "2025-09-01T00:00:00Z",
            "stargazers_count": 200,
            "forks_count": 50,
            "watchers_count": 200,
            "subscribers_count": 25,
            "topics": ["example", "tutorial"],
        }
        dataset = MagicMock()
        dataset.fetch_metadata.return_value = metadata

        model = MagicMock()
        model.dataset = dataset

        dq = DatasetQuality()
        dq.compute(model)

        val = cast(float, dq.value)
        assert 0.8 <= val <= 1.0
        assert dq.details["documentation"] == 1.0
        assert dq.details["license"] == 1.0
        assert dq.details["example_code"] == 1.0

    def test_partial_dataset(self) -> None:
        """Missing fields and low community numbers should reduce score."""
        metadata: Dict[str, Any] = {
            "description": "Only desc",
            "license": None,
            "homepage": "",
            "updated_at": "2022-01-01T00:00:00Z",
            "stargazers_count": 2,
            "forks_count": 0,
            "watchers_count": 1,
            "subscribers_count": 0,
            "topics": [],
        }
        dataset = MagicMock()
        dataset.fetch_metadata.return_value = metadata

        model = MagicMock()
        model.dataset = dataset

        dq = DatasetQuality()
        dq.compute(model)

        val = cast(float, dq.value)
        assert val < 0.5
        assert dq.details["documentation"] < 1.0
        assert dq.details["license"] == 0.0
        assert dq.details["community"] < 0.5

    def test_invalid_updated_at(self) -> None:
        """Invalid date string should fall back to neutral freshness score (0.5)."""
        metadata: Dict[str, Any] = {
            "description": "X",
            "license": {"name": "MIT"},
            "homepage": "Y",
            "updated_at": "not-a-date",
        }
        dataset = MagicMock()
        dataset.fetch_metadata.return_value = metadata

        model = MagicMock()
        model.dataset = dataset

        dq = DatasetQuality()
        dq.compute(model)

        assert dq.details["freshness"] == 0.5
