"""Dataset resource for accessing HuggingFace dataset information and files.

This module provides the DatasetResource class, which represents a dataset
resource associated with a machine learning model. It handles fetching
metadata from HuggingFace datasets and provides access to dataset repository
files through a RepoView interface.
"""

from typing import Any, ContextManager, Iterable, Optional

from adapters.client import HFClient
from adapters.dataset_fetchers import HFDatasetFetcher
from adapters.repo_view import RepoView
from resources.base_resource import _BaseResource


class DatasetResource(_BaseResource):
    """Represents a dataset resource for a machine learning model."""

    def __init__(self, url: str) -> None:
        """Initialize the dataset resource.

        If the URL is a Hugging Face dataset, the repository ID is extracted.
        """
        super().__init__(url=url)
        if self._is_hf_dataset_url():
            self._repo_id = self._hf_id_from_url()
            self._client = HFClient()

    def _is_hf_dataset_url(self) -> bool:
        """Check if the URL corresponds to a Hugging Face dataset.

        Returns:
            bool: True if the URL is a Hugging Face dataset URL, False otherwise.
        """
        return "huggingface.co/datasets/" in self.url

    def fetch_metadata(self) -> Any:
        """Retrieve metadata associated with the dataset resource.

        Fetches dataset metadata from HuggingFace API on first call and caches
        it for subsequent calls. Metadata includes dataset description, license,
        size, and other dataset card information.

        Returns:
            Any: Dictionary containing dataset metadata from HuggingFace API
        """
        if self.metadata is None:
            self.metadata = self._client.get_dataset_metadata(self._repo_id)

        return self.metadata

    def open_files(
        self, allow_patterns: Optional[Iterable[str]] = None
    ) -> ContextManager[RepoView]:
        """Opens and provides access to files from the dataset repository.

        Returns a context manager that allows reading files from the HuggingFace
        dataset repository. Files can be filtered by patterns if specified.

        Args:
            allow_patterns: Optional iterable of file patterns to allow access to
                (e.g., ["*.csv", "*.json", "README.md"])

        Returns:
            ContextManager[RepoView]: A context manager that provides access to the
                repository files through a RepoView interface
        """
        return HFDatasetFetcher(self._repo_id, allow_patterns=allow_patterns)
