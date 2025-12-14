"""Model resource for accessing HuggingFace model information and files.

This module provides the ModelResource class, which represents a machine learning
model hosted on HuggingFace. It handles fetching model metadata (model card,
config, etc.) and provides access to model repository files including weights,
configurations, and documentation through a RepoView interface.
"""

from typing import Any, ContextManager, Iterable, Optional
from adapters.client import HFClient
from adapters.model_fetchers import HFModelFetcher
from adapters.repo_view import RepoView
from resources.base_resource import _BaseResource


class ModelResource(_BaseResource):
    """Resource for accessing HuggingFace model information and files.

    Provides methods to fetch model metadata and access repository files
    from HuggingFace.
    """

    def __init__(self, url: str) -> None:
        """Initialize model resource from a HuggingFace URL.

        Args:
            url: HuggingFace model URL (e.g., https://huggingface.co/bert-base-uncased)
        """
        super().__init__(url=url)
        self._repo_id = self._hf_id_from_url()
        self._client = HFClient()

    def fetch_metadata(self) -> Any:
        """Fetch and cache model metadata from HuggingFace.

        Retrieves metadata on first call and caches it for subsequent calls.

        Returns:
            Any: Model metadata from HuggingFace API
        """
        if self.metadata is None:
            self.metadata = self._client.get_model_metadata(self._repo_id)
        return self.metadata

    def open_files(
        self, allow_patterns: Optional[Iterable[str]] = None
    ) -> ContextManager[RepoView]:
        """Open a context manager for accessing model repository files.

        Args:
            allow_patterns: Optional file patterns to filter (e.g., ["*.py", "*.md"])

        Returns:
            ContextManager[RepoView]: Context manager providing file access
        """
        return HFModelFetcher(self._repo_id, allow_patterns=allow_patterns)
