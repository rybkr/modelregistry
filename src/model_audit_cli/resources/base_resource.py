from typing import Any, ContextManager, Iterable, Optional
from urllib.parse import urlparse

from pydantic import BaseModel

from model_audit_cli.adapters.repo_view import RepoView
from model_audit_cli.errors import UNSUPPORTED_URL, AppError


class _BaseResource(BaseModel):
    url: str
    metadata: Optional[dict[str, Any]] = None

    def _hf_id_from_url(self) -> str:
        path = urlparse(self.url)
        parts = [x for x in path.path.strip("/").split("/") if x]
        if parts[0] not in {"datasets", "spaces"}:
            return f"{parts[0]}/{parts[1]}"
        elif len(parts) > 2:
            return f"{parts[1]}/{parts[2]}"
        raise AppError(
            UNSUPPORTED_URL,
            "The specified url is not supported yet.",
            context={"url": self.url},
        )

    def fetch_metadata(self) -> dict[str, Any]:
        raise NotImplementedError

    def open_files(
        self, allow_patterns: Optional[Iterable[str]] = None
    ) -> ContextManager[RepoView]:
        raise NotImplementedError
