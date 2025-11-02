from __future__ import annotations

from unittest.mock import MagicMock, patch

from adapters.repo_view import RepoView
from resources.code_resource import CodeResource


class TestCodeResource:
    """Test cases for the CodeResource class."""

    @patch("resources.code_resource.HFClient.get_space_metadata")
    def test_fetch_metadata_hf_space(self, mock_space_meta: MagicMock) -> None:
        """Test successful retrieval of metadata for Hugging Face Spaces."""
        mock_space_meta.return_value = {"host": "hf_space", "name": "demo"}
        r = CodeResource("https://huggingface.co/spaces/acme/demo")

        meta = r.fetch_metadata()

        assert meta == {"host": "hf_space", "name": "demo"}
        # ensures _hf_id_from_url() was used (owner/name)
        mock_space_meta.assert_called_once_with("acme/demo")

    @patch("resources.code_resource.GitHubClient.get_metadata")
    def test_fetch_metadata_github(self, mock_meta: MagicMock) -> None:
        """Test successful retrieval of metadata for GitHub repositories."""
        mock_meta.return_value = {"host": "github", "default_branch": "main"}
        r = CodeResource("https://github.com/org/repo")

        meta = r.fetch_metadata()

        assert meta["host"] == "github"
        mock_meta.assert_called_once_with("https://github.com/org/repo")

    @patch("resources.code_resource.GitLabClient.get_metadata")
    def test_fetch_metadata_gitlab(self, mock_meta: MagicMock) -> None:
        """Test successful retrieval of metadata for GitLab repositories."""
        mock_meta.return_value = {"host": "gitlab", "default_branch": "main"}
        r = CodeResource("https://gitlab.com/group/sub/repo")

        meta = r.fetch_metadata()

        assert meta["host"] == "gitlab"
        mock_meta.assert_called_once_with("https://gitlab.com/group/sub/repo")

    @patch("resources.code_resource.GitHubClient.get_metadata")
    def test_fetch_metadata_cached_does_not_recall(self, mock_meta: MagicMock) -> None:
        """Test cached metadata is returned on subsequent calls without re-fetching."""
        mock_meta.return_value = {"host": "github"}
        r = CodeResource("https://github.com/org/repo")

        a = r.fetch_metadata()
        b = r.fetch_metadata()  # should use cached self.metadata

        assert a == b == {"host": "github"}
        mock_meta.assert_called_once_with("https://github.com/org/repo")

    @patch("resources.code_resource.open_codebase")
    def test_open_files_returns_context_manager(
        self, mock_open_codebase: MagicMock
    ) -> None:
        """Test that open_files returns a context manager for RepoView."""
        mock_context_manager = MagicMock()
        mock_open_codebase.return_value = mock_context_manager

        r = CodeResource("https://github.com/org/repo")
        result = r.open_files()

        assert result is mock_context_manager
        mock_open_codebase.assert_called_once_with(
            "https://github.com/org/repo", allow_patterns=None
        )

    @patch("resources.code_resource.open_codebase")
    def test_open_files_with_context_manager_usage(
        self, mock_open_codebase: MagicMock
    ) -> None:
        """Test open_files context manager can be used to access repository files."""
        # Create a mock RepoView
        mock_repo_view = MagicMock(spec=RepoView)
        mock_repo_view.exists.return_value = True
        mock_repo_view.read_text.return_value = "# code readme\n"
        mock_repo_view.read_json.return_value = {"tool": "gradio", "version": "4.x"}

        # Setup context manager
        mock_context_manager = MagicMock()
        mock_context_manager.__enter__.return_value = mock_repo_view
        mock_context_manager.__exit__.return_value = None
        mock_open_codebase.return_value = mock_context_manager

        r = CodeResource("https://huggingface.co/spaces/acme/demo")

        with r.open_files() as repo_view:
            # Test file existence check
            exists = repo_view.exists("README.md")
            assert exists is True

            # Test reading text file
            content = repo_view.read_text("README.md")
            assert content == "# code readme\n"

            # Test reading JSON file
            json_data = repo_view.read_json("space_config.json")
            assert json_data == {"tool": "gradio", "version": "4.x"}

        mock_open_codebase.assert_called_once_with(
            "https://huggingface.co/spaces/acme/demo", allow_patterns=None
        )
        mock_context_manager.__enter__.assert_called_once()
        mock_context_manager.__exit__.assert_called_once_with(None, None, None)
