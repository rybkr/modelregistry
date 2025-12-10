from typing import Any, ContextManager, Iterable, Optional
from urllib.parse import urlparse

from pydantic import BaseModel

from adapters.repo_view import RepoView
from errors import UNSUPPORTED_URL, AppError


class _BaseResource(BaseModel):
    url: str
    metadata: Optional[dict[str, Any]] = None

    def _hf_id_from_url(self) -> str:
        path = urlparse(self.url)
        parts = [x for x in path.path.strip("/").split("/") if x]

        # Handle model URLs: https://huggingface.co/org/model
        if len(parts) >= 2 and parts[0] not in {"datasets", "spaces"}:
            return f"{parts[0]}/{parts[1]}"
        # Handle model URLs with single part: https://huggingface.co/model (fallback)
        elif len(parts) == 1 and parts[0] not in {"datasets", "spaces"}:
            # Single part model URL - return as-is (e.g., "bert-base-uncased")
            return parts[0]
        # Handle datasets/spaces URLs
        elif len(parts) > 2 and parts[0] in {"datasets", "spaces"}:
            return f"{parts[1]}/{parts[2]}"
        # Handle datasets/spaces with 2 parts
        elif len(parts) == 2 and parts[0] in {"datasets", "spaces"}:
            return parts[1]

        raise AppError(
            UNSUPPORTED_URL,
            "The specified url is not supported yet.",
            context={"url": self.url},
        )

    def _gh_id_from_url(self) -> str:
        path = urlparse(self.url)
        return path.path[0] + "/" + path.path[1]

    def fetch_metadata(self) -> dict[str, Any]:
        raise NotImplementedError

    def open_files(
        self, allow_patterns: Optional[Iterable[str]] = None
    ) -> ContextManager[RepoView]:
        raise NotImplementedError
