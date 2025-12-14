"""Code resource for accessing code repositories from multiple platforms.

This module provides the CodeResource class, which represents a code repository
associated with a machine learning model. It supports multiple platforms including
HuggingFace Spaces, GitHub, and GitLab. It handles fetching metadata and provides
access to repository files through a unified RepoView interface.
"""

from typing import Any, ContextManager, Iterable, Optional

from adapters.client import GitHubClient, GitLabClient, HFClient
from adapters.code_fetchers import open_codebase
from adapters.repo_view import RepoView
from resources.base_resource import _BaseResource


class CodeResource(_BaseResource):
    """Represents a code resource for a machine learning model.

    Handles code repositories from multiple platforms (HuggingFace Spaces,
    GitHub, GitLab) and provides unified access to code metadata and files.
    Automatically detects the platform from the URL and initializes the
    appropriate client.
    """

    def __init__(self, url: str) -> None:
        """Initialize the code resource.

        Extracts the repository ID from the URL and initializes the appropriate
        client (HFClient for Spaces, GitHubClient for GitHub, etc.) based on
        the URL platform.

        Args:
            url: Code repository URL (HuggingFace Space, GitHub, or GitLab)
        """
        super().__init__(url=url)
        if self._is_hf_space_url():
            self._repo_id = self._hf_id_from_url()
            self._client = HFClient()
        if self.is_gh_url():
            self._repo_id = self._gh_id_from_url()
            self._client = GitHubClient()

    def _is_hf_space_url(self) -> bool:
        """Check if the URL corresponds to a HuggingFace Space.

        Args:
            self: CodeResource instance

        Returns:
            bool: True if the URL is a HuggingFace Space URL, False otherwise
        """
        return "huggingface.co/spaces/" in self.url

    def is_gh_url(self) -> bool:
        """Check if the URL corresponds to a GitHub repository.

        Returns:
            bool: True if the URL is a GitHub repository URL, False otherwise
        """
        return "github.com" in self.url

    def fetch_metadata(self) -> Any:
        """Retrieves metadata associated with the resource.

        Returns:
            Any: The metadata of the resource. The exact type and structure
            of the metadata depend on the specific implementation.
        """
        if self.metadata is None:
            if self._is_hf_space_url():
                self.metadata = self._client.get_space_metadata(self._repo_id)
            elif "github.com" in self.url:
                self.metadata = GitHubClient().get_metadata(self.url)
            elif "gitlab.com" in self.url:
                self.metadata = GitLabClient().get_metadata(self.url)

        return self.metadata

    def open_files(
        self, allow_patterns: Optional[Iterable[str]] = None
    ) -> ContextManager[RepoView]:
        """Open and provide access to files from the code repository.

        Returns a context manager that allows reading files from the code
        repository. Works with HuggingFace Spaces, GitHub, and GitLab repositories.
        Files can be filtered by patterns if specified.

        Args:
            allow_patterns: Optional iterable of file patterns to allow access to
                (e.g., ["*.py", "*.md", "requirements.txt"])

        Returns:
            ContextManager[RepoView]: A context manager that provides access to the
                repository files through a RepoView interface
        """
        return open_codebase(self.url, allow_patterns=allow_patterns)
