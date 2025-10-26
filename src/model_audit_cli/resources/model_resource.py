from typing import Any, ContextManager, Iterable, Optional

from model_audit_cli.adapters.client import HFClient
from model_audit_cli.adapters.model_fetchers import HFModelFetcher
from model_audit_cli.adapters.repo_view import RepoView
from model_audit_cli.resources.base_resource import _BaseResource


class ModelResource(_BaseResource):
    """Represents a model resource for a machine learning model."""

    def __init__(self, url: str) -> None:
        """Initialize the model resource.

        Extracts the repository ID from the URL.
        """
        super().__init__(url=url)
        self._repo_id = self._hf_id_from_url()
        self._client = HFClient()

    def fetch_metadata(self) -> Any:
        """Get model metadata from Huggingface API.

        Returns:
            Any: JSON object with models metadata.
        """
        if self.metadata is None:
            self.metadata = self._client.get_model_metadata(self._repo_id)

        return self.metadata

    def open_files(
        self, allow_patterns: Optional[Iterable[str]] = None
    ) -> ContextManager[RepoView]:
        """Opens and provides access to files from the model repository.

        Returns:
            ContextManager[RepoView]: A context manager that provides access to the
                repository files through a RepoView interface.
        """
        return HFModelFetcher(self._repo_id, allow_patterns=allow_patterns)
