from typing import Any, ContextManager, Iterable, Optional

from model_audit_cli.adapters.client import GitHubClient, GitLabClient, HFClient
from model_audit_cli.adapters.code_fetchers import open_codebase
from model_audit_cli.adapters.repo_view import RepoView
from model_audit_cli.resources.base_resource import _BaseResource


class CodeResource(_BaseResource):
    """Represents a code resource for a machine learning model."""

    def __init__(self, url: str):
        super().__init__(url=url)
        if self._is_hf_space_url():
            self._repo_id = self._hf_id_from_url()
            self._client = HFClient()

    def _is_hf_space_url(self) -> bool:
        """Check if the URL corresponds to a Hugging Face dataset.

        Returns:
            bool: True if the URL is a Hugging Face dataset URL, False otherwise.
        """
        return "huggingface.co/spaces/" in self.url

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
        """Opens and provides access to files from the code repository.

        Returns:
            ContextManager[RepoView]: A context manager that provides access to the
                repository files through a RepoView interface.
        """
        return open_codebase(self.url, allow_patterns=allow_patterns)
