from typing import Any, ContextManager, Iterable, Optional

from adapters.client import HFClient
from adapters.model_fetchers import HFModelFetcher
from adapters.repo_view import RepoView
from resources.base_resource import _BaseResource


class ModelResource(_BaseResource):
    def __init__(self, url: str) -> None:
        super().__init__(url=url)
        self._repo_id = self._hf_id_from_url()
        self._client = HFClient()

    def fetch_metadata(self) -> Any:
        if self.metadata is None:
            self.metadata = self._client.get_model_metadata(self._repo_id)
        return self.metadata

    def open_files(
        self, allow_patterns: Optional[Iterable[str]] = None
    ) -> ContextManager[RepoView]:
        return HFModelFetcher(self._repo_id, allow_patterns=allow_patterns)
