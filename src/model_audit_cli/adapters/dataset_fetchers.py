from __future__ import annotations

from typing import Iterable, Optional

from model_audit_cli.adapters.model_fetchers import _BaseSnapshotFetcher

DATASET_ALLOW = [
    "README.md",
    "README.*",
    "dataset_info.json",  # primary structured metadata
    "data/*",  # optional: small samples/processed shards if needed
]

# NOTE: Move MAX_FILE_BYTES to .env
MAX_FILE_BYTES = 512 * 1024


class HFDatasetFetcher(_BaseSnapshotFetcher):
    """Fetcher for Hugging Face dataset repositories."""

    def __init__(
        self,
        repo_id: str,
        revision: Optional[str] = None,
        allow_patterns: Optional[Iterable[str]] = None,
        use_shared_cache: bool = True,
    ) -> None:
        """Initialize the dataset fetcher with repository details.

        Args:
            repo_id (str): The ID of the dataset repository to fetch.
            revision (Optional[str]):
                The specific revision of the dataset repository to fetch.
            allow_patterns (Optional[Iterable[str]]): Patterns of files to allow
                during fetching. Defaults to DATASET_ALLOW.
            use_shared_cache (bool): Whether to use a shared cache for the snapshot.
                Defaults to True.
        """
        allow_patterns = allow_patterns or DATASET_ALLOW
        super().__init__(repo_id, "dataset", revision, allow_patterns, use_shared_cache)
