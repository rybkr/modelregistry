from __future__ import annotations

from unittest.mock import MagicMock, patch

from model_audit_cli.adapters.repo_view import RepoView
from model_audit_cli.resources.model_resource import ModelResource


class TestModelResource:
    """Test cases for the ModelResource class."""

    @patch("model_audit_cli.resources.model_resource.HFClient.get_model_metadata")
    def test_metadata_calls_hfclient(self, mock_get: MagicMock) -> None:
        """Test fetch_metadata calls HFClient.get_model_metadata with right params."""
        mock_get.return_value = {"name": "bert-base-uncased"}
        r = ModelResource("https://huggingface.co/google-bert/bert-base-uncased")

        meta = r.fetch_metadata()

        assert meta["name"] == "bert-base-uncased"
        mock_get.assert_called_once_with("google-bert/bert-base-uncased")

    @patch("model_audit_cli.resources.model_resource.HFModelFetcher")
    def test_open_files_returns_context_manager(self, mock_fetcher: MagicMock) -> None:
        """Test that open_files returns a context manager for RepoView."""
        mock_context_manager = MagicMock()
        mock_fetcher.return_value = mock_context_manager

        r = ModelResource("https://huggingface.co/google-bert/bert-base-uncased")
        result = r.open_files()

        assert result is mock_context_manager
        mock_fetcher.assert_called_once_with(
            "google-bert/bert-base-uncased", allow_patterns=None
        )

    @patch("model_audit_cli.resources.model_resource.HFClient.get_model_metadata")
    def test_fetch_metadata_cached(self, mock_get: MagicMock) -> None:
        """Test cached metadata is returned on subsequent calls without re-fetching."""
        mock_get.return_value = {"once": True}
        r = ModelResource("google-bert/bert-base-uncased")

        a = r.fetch_metadata()
        b = r.fetch_metadata()  # should not call client again

        assert a == b == {"once": True}
        mock_get.assert_called_once_with("google-bert/bert-base-uncased")

    @patch("model_audit_cli.resources.model_resource.HFModelFetcher")
    def test_open_files_with_context_manager_usage(
        self, mock_fetcher: MagicMock
    ) -> None:
        """Test open_files context manager can be used to access repository files."""
        # Create a mock RepoView
        mock_repo_view = MagicMock(spec=RepoView)
        mock_repo_view.exists.return_value = True
        mock_repo_view.read_text.return_value = "# model readme\n"
        mock_repo_view.read_json.return_value = {"a": 1, "b": [2, 3]}

        # Setup context manager
        mock_context_manager = MagicMock()
        mock_context_manager.__enter__.return_value = mock_repo_view
        mock_context_manager.__exit__.return_value = None
        mock_fetcher.return_value = mock_context_manager

        r = ModelResource("https://huggingface.co/google-bert/bert-base-uncased")

        with r.open_files() as repo_view:
            # Test file existence check
            exists = repo_view.exists("README.md")
            assert exists is True

            # Test reading text file
            content = repo_view.read_text("README.md")
            assert content == "# model readme\n"

            # Test reading JSON file
            json_data = repo_view.read_json("config.json")
            assert json_data == {"a": 1, "b": [2, 3]}

        mock_fetcher.assert_called_once_with(
            "google-bert/bert-base-uncased", allow_patterns=None
        )
        mock_context_manager.__enter__.assert_called_once()
        mock_context_manager.__exit__.assert_called_once_with(None, None, None)
