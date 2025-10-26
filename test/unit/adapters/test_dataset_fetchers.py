from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from model_audit_cli.adapters.dataset_fetchers import HFDatasetFetcher


class TestHFDatasetFetcher:
    """Test cases for HFDatasetFetcher."""

    @patch("model_audit_cli.adapters.model_fetchers.snapshot_download")
    def test_dataset_fetcher_minimal(
        self, snapshot_download_mock: MagicMock, tmp_path: Path
    ) -> None:
        """Test that the dataset fetcher correctly fetches and reads dataset files."""
        root = tmp_path / "dataset"
        root.mkdir()
        (root / "README.md").write_text("# dataset\n", encoding="utf-8")
        (root / "dataset_info.json").write_text(
            '{"splits":{"train":{"num_examples": 10}}}', encoding="utf-8"
        )
        snapshot_download_mock.return_value = str(root)

        with HFDatasetFetcher("ns/ds") as view:
            assert view.read_text("README.md").startswith("# dataset")
            assert "splits" in view.read_json("dataset_info.json")

        kwargs = snapshot_download_mock.call_args.kwargs
        assert kwargs["repo_type"] == "dataset"
        assert kwargs["repo_id"] == "ns/ds"
        assert "allow_patterns" in kwargs
