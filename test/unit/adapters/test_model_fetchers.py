from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from model_audit_cli.adapters.model_fetchers import HFModelFetcher


class TestHFModelFetcher:
    """Test cases for the HFModelFetcher."""

    @patch("model_audit_cli.adapters.model_fetchers.snapshot_download")
    def test_model_fetcher_minimal(
        self, snapshot_download_mock: MagicMock, tmp_path: Path
    ) -> None:
        """Test that the model fetcher correctly fetches and reads model files."""
        root = tmp_path / "model"
        root.mkdir()
        (root / "README.md").write_text("# model\n", encoding="utf-8")
        (root / "config.json").write_text('{"a": 1}', encoding="utf-8")
        snapshot_download_mock.return_value = str(root)

        with HFModelFetcher("org/name") as view:
            assert view.read_text("README.md").startswith("# model")
            assert view.read_json("config.json")["a"] == 1

        kwargs = snapshot_download_mock.call_args.kwargs
        assert kwargs["repo_type"] == "model"
        assert kwargs["repo_id"] == "org/name"
        assert "allow_patterns" in kwargs

    @patch("model_audit_cli.adapters.model_fetchers.snapshot_download")
    def test_base_snapshot_fetcher_removes_large_files(
        self, snapshot_download_mock: MagicMock, tmp_path: Path
    ) -> None:
        """Tests that _BaseSnapshotFetcher correctly removes files too large."""
        # NOTE: Uncomment when MAX_FILE_BYTES is moved to .env. Add monkeypath to args
        # # Force a small cap (1 KiB)
        # monkeypatch.setenv("MAC_MAX_FILE_BYTES", "1024")

        # Build a fake snapshot dir
        snap = tmp_path / "snap"
        snap.mkdir()
        # Small file (kept)
        (snap / "README.md").write_text("# ok\n", encoding="utf-8")
        # Large file (deleted)
        big = snap / "pytorch_model.bin"
        big.write_bytes(b"x" * (513 * 1024 * 1024))

        snapshot_download_mock.return_value = str(snap)

        with HFModelFetcher("org/model") as view:
            # Small file still present
            assert view.exists("README.md")
            assert view.read_text("README.md").startswith("# ok")
            # Large file should have been removed by the cleanup pass
            assert not (view.root / "pytorch_model.bin").exists()

        # Sanity: ensure snapshot_download was called for a model repo
        kwargs = snapshot_download_mock.call_args.kwargs
        assert kwargs["repo_type"] == "model"
