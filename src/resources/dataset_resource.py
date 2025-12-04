from typing import Any, ContextManager, Iterable, Optional

from adapters.client import HFClient, GitHubClient, KaggleClient
from adapters.dataset_fetchers import HFDatasetFetcher
from adapters.repo_view import RepoView
from resources.base_resource import _BaseResource
from urllib.parse import quote_plus, urlparse


class DatasetResource(_BaseResource):
    """Represents a dataset resource for a machine learning model."""

    def __init__(self, url: str) -> None:
        """Initialize the dataset resource.

        If the URL is a Hugging Face dataset, the repository ID is extracted.
        """
        super().__init__(url=url)
        if self._is_hf_dataset_url():
            self._repo_id = self._hf_id_from_url()
            self._dataset_type = "hf"
            self._client = HFClient()
        elif self._is_gh_dataset_url():
            path = urlparse(url)
            parts = [x for x in path.path.strip("/").split("/") if x]
            self._repo_id = parts[0] + "/" + parts[1]
            self._dataset_type = "gh"
            self._client = GitHubClient()
        elif self._is_kaggle_dataset_url():
           self._repo_id = self._hf_id_from_url() # Works for kaggle as well
           self._dataset_type = "kaggle"
           self._client = KaggleClient()

    def _is_hf_dataset_url(self) -> bool:
        """Check if the URL corresponds to a Hugging Face dataset.

        Returns:
            bool: True if the URL is a Hugging Face dataset URL, False otherwise.
        """
        return "huggingface.co/datasets/" in self.url

    def _is_gh_dataset_url(self) -> bool:
        """Check if the URL corresponds to a Github dataset.

        Returns:
            bool: True if the URL is a Github dataset URL, False otherwise.
        """
        return "github.com/" in self.url

    def _is_kaggle_dataset_url(self) -> bool:
        """Check if the URL corresponds to a Kaggle dataset.

        Returns:
            bool: True if the URL is a Kaggle dataset URL, False otherwise.
        """
        return "kaggle.com/datasets" in self.url

    def fetch_metadata(self) -> Any:
        """Retrieve metadata associated with the dataset resource.

        Returns:
            Any: JSON object with models metadata.
        """
        if self.metadata is None:
            self.metadata = self._client.get_dataset_metadata(self._repo_id)

        return self.metadata

    def open_files(
        self, allow_patterns: Optional[Iterable[str]] = None
    ) -> ContextManager[RepoView]:
        """Opens and provides access to files from the dataset repository.

        Returns:
            ContextManager[RepoView]: A context manager that provides access to the
                repository files through a RepoView interface.
        """
        return HFDatasetFetcher(self._repo_id, allow_patterns=allow_patterns)
