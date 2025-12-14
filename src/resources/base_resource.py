"""Base resource class for model, dataset, and code resources.

This module provides the base class for all resource types (models, datasets, code)
in the Model Registry. It defines the common interface for fetching metadata
and accessing repository files, with support for both HuggingFace and GitHub URLs.
"""

from typing import Any, ContextManager, Iterable, Optional
from urllib.parse import urlparse

from pydantic import BaseModel

from adapters.repo_view import RepoView
from errors import UNSUPPORTED_URL, AppError


class _BaseResource(BaseModel):
    """Base class for all resource types (models, datasets, code).

    Provides common functionality for parsing URLs and extracting repository
    identifiers from HuggingFace and GitHub URLs. Subclasses must implement
    fetch_metadata() and open_files() methods.

    Attributes:
        url: The resource URL (HuggingFace or GitHub)
        metadata: Optional cached metadata dictionary
    """

    url: str
    metadata: Optional[dict[str, Any]] = None

    def _hf_id_from_url(self) -> str:
        """Extract HuggingFace repository ID from URL.

        Parses HuggingFace URLs to extract organization/repository identifiers,
        handling models, datasets, and spaces.

        Returns:
            str: Repository ID in format "org/repo" or single model name

        Raises:
            AppError: If URL format is not supported
        """
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
        """Extract GitHub repository ID from URL.

        Parses GitHub URLs to extract owner/repository identifiers.

        Returns:
            str: Repository ID in format "owner/repo"
        """
        path = urlparse(self.url)
        return path.path[0] + "/" + path.path[1]

    def fetch_metadata(self) -> dict[str, Any]:
        """Fetch metadata for this resource.

        Subclasses must implement this method to retrieve resource metadata
        from the appropriate API (HuggingFace, GitHub, etc.).

        Returns:
            dict[str, Any]: Resource metadata dictionary

        Raises:
            NotImplementedError: Must be implemented by subclasses
        """
        raise NotImplementedError

    def open_files(
        self, allow_patterns: Optional[Iterable[str]] = None
    ) -> ContextManager[RepoView]:
        """Open repository files for reading.

        Returns a context manager that provides access to repository files
        matching the specified patterns.

        Args:
            allow_patterns: Optional iterable of file patterns to allow access to

        Returns:
            ContextManager[RepoView]: Context manager for file access

        Raises:
            NotImplementedError: Must be implemented by subclasses
        """
        raise NotImplementedError
