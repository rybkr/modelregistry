from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from adapters.client import GitHubClient
from adapters.code_fetchers import open_codebase
from log import logger
from metrics.base_metric import Metric
from models import Model


# File patterns to exclude from LOC counting (weight files, binaries, data, large artifacts)
EXCLUDED_PATTERNS = [
    "*.bin", "*.h5", "*.pt", "*.pth", "*.onnx", "*.tflite", "*.safetensors",
    "*.pb", "*.ckpt", "*.pkl", "*.pickle", "*.pyc", "*.pyo", "*.pyd",
    "*.so", "*.dylib", "*.dll", "*.exe", "*.o", "*.a", "*.lib",
    "*.zip", "*.tar", "*.tar.gz", "*.tgz", "*.rar", "*.7z",
    "*.pdf", "*.doc", "*.docx", "*.xls", "*.xlsx",
    "*.mp4", "*.avi", "*.mov", "*.mp3", "*.wav",
    "*.jpg", "*.jpeg", "*.png", "*.gif", "*.bmp", "*.tiff",
    "*.npy", "*.npz", "*.hdf5", "*.h5",
]

# Extensions to exclude (for binary detection)
EXCLUDED_EXTENSIONS = {
    ".bin", ".h5", ".pt", ".pth", ".onnx", ".tflite", ".safetensors",
    ".pb", ".ckpt", ".pkl", ".pickle", ".pyc", ".pyo", ".pyd",
    ".so", ".dylib", ".dll", ".exe", ".o", ".a", ".lib",
    ".zip", ".tar", ".gz", ".tgz", ".rar", ".7z",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".mp4", ".avi", ".mov", ".mp3", ".wav",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff",
    ".npy", ".npz", ".hdf5",
}


class Reviewedness(Metric):
    """Metric for reviewedness: fraction of code introduced through reviewed PRs.

    Calculates the fraction of all code (not weights) in the associated GitHub
    repository that was introduced through pull requests with a code review.
    Returns -1 if there is no linked GitHub repository.
    """

    def __init__(self) -> None:
        super().__init__(name="reviewedness")

    def _is_github_url(self, url: str) -> bool:
        """Check if URL is a GitHub repository URL."""
        return "github.com" in url.lower()

    def _extract_owner_repo(self, url: str) -> tuple[str, str] | None:
        """Extract owner and repo from GitHub URL."""
        try:
            parsed = urlparse(url)
            parts = [p for p in parsed.path.strip("/").split("/") if p]
            if len(parts) >= 2:
                return parts[0], parts[1]
        except Exception:
            pass
        return None

    def _has_code_review(self, reviews: list[dict[str, Any]]) -> bool:
        """Check if a PR has at least one reviewer approval.

        Args:
            reviews: List of review dictionaries from GitHub API

        Returns:
            True if PR has at least one APPROVED review, False otherwise
        """
        if not reviews:
            return False
        
        # A review is considered valid if it has state APPROVED
        # (CHANGES_REQUESTED and COMMENTED are reviews but not approvals)
        for review in reviews:
            state = review.get("state", "").upper()
            if state == "APPROVED":
                return True
        
        return False

    def _should_exclude_file(self, file_path: Path) -> bool:
        """Check if a file should be excluded from LOC counting.

        Args:
            file_path: Path to the file

        Returns:
            True if file should be excluded, False otherwise
        """
        # Check by extension
        if file_path.suffix.lower() in EXCLUDED_EXTENSIONS:
            return True
        
        # Check by name patterns (for files without extensions or special cases)
        file_str = str(file_path).lower()
        for pattern in EXCLUDED_PATTERNS:
            # Simple pattern matching (e.g., "*.bin" matches files ending in .bin)
            if pattern.startswith("*."):
                ext = pattern[1:]  # Remove "*"
                if file_str.endswith(ext):
                    return True
        
        # Exclude very large files (likely data/artifacts)
        try:
            if file_path.stat().st_size > 10 * 1024 * 1024:  # 10MB
                return True
        except (OSError, AttributeError):
            pass
        
        return False

    def _count_loc_in_repo(self, repo_path: Path) -> int:
        """Count total lines of code in repository, excluding weight files, binaries, etc.

        Args:
            repo_path: Root path of the repository

        Returns:
            Total number of lines of code
        """
        total_loc = 0
        
        # Directories to skip (non-code directories)
        skip_dirs = {".git", ".svn", ".hg", "__pycache__", "node_modules", 
                     ".pytest_cache", ".mypy_cache", ".venv", "venv", "env",
                     "dist", "build", ".egg-info", ".tox", ".coverage", "htmlcov"}
        
        # Walk through all files in the repository
        for file_path in repo_path.rglob("*"):
            if not file_path.is_file():
                continue
            
            # Skip files in excluded directories
            if any(part in skip_dirs for part in file_path.parts):
                continue
            
            # Skip hidden files (starting with .)
            if file_path.name.startswith("."):
                continue
            
            # Skip excluded files (weight files, binaries, etc.)
            if self._should_exclude_file(file_path):
                continue
            
            # Try to count lines in text files
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    # Count all lines (including empty lines) for LOC
                    loc = sum(1 for _ in f)
                    total_loc += loc
            except (UnicodeDecodeError, IOError, PermissionError):
                # Skip binary files or files we can't read
                continue
        
        return total_loc

    def compute(self, model: Model) -> None:
        """Compute reviewedness metric for the model's code repository.

        Formula: LOC_reviewed / LOC_total
        - LOC_total: total lines of code in the repository (excluding weight files, binaries, etc.)
        - LOC_reviewed: lines of code contributed via PRs with at least one reviewer approval
        - Returns -1 if no GitHub repository, 0.0 if LOC_total = 0
        """
        logger.info("Computing Reviewedness metric...")
        start: float = time.perf_counter()
        
        try:
            # Get code URL from model
            url: str | None = model.code.url if model.code else None
            
            if not url:
                self.value = -1.0
                self.latency_ms = int(round((time.perf_counter() - start) * 1000))
                self.details = {"error": "No code URL provided"}
                logger.warning("No code URL provided for Reviewedness metric")
                return

            # Check if it's a GitHub repository
            if not self._is_github_url(url):
                self.value = -1.0
                self.latency_ms = int(round((time.perf_counter() - start) * 1000))
                self.details = {"error": "Not a GitHub repository", "url": url}
                logger.info(f"Not a GitHub repository: {url}, returning -1")
                return

            # Extract owner and repo
            owner_repo = self._extract_owner_repo(url)
            if not owner_repo:
                self.value = -1.0
                self.latency_ms = int(round((time.perf_counter() - start) * 1000))
                self.details = {"error": "Could not parse GitHub URL", "url": url}
                logger.warning(f"Could not parse GitHub URL: {url}")
                return

            owner, repo = owner_repo
            logger.info(f"Computing reviewedness for {owner}/{repo}")

            # Step 1: Get total LOC in the repository
            loc_total = 0
            try:
                with open_codebase(url) as repo_view:
                    loc_total = self._count_loc_in_repo(repo_view.root)
                    logger.info(f"Total LOC in repository: {loc_total}")
            except Exception as e:
                logger.warning(f"Could not count LOC in repository: {e}")
                # If we can't count LOC, we can't compute the metric properly
                # Return 0.0 as per spec (if LOC_total = 0, return 0)
                self.value = 0.0
                self.latency_ms = int(round((time.perf_counter() - start) * 1000))
                self.details = {"error": f"Could not count LOC: {str(e)}", "loc_total": 0}
                return

            # If LOC_total = 0, return 0 as per spec
            if loc_total == 0:
                self.value = 0.0
                self.latency_ms = int(round((time.perf_counter() - start) * 1000))
                self.details = {
                    "loc_total": 0,
                    "loc_reviewed": 0,
                    "reason": "No code found in repository"
                }
                logger.info(f"No code found in repository {owner}/{repo}")
                return

            # Step 2: Get all merged pull requests and sum additions from reviewed PRs
            github_client = GitHubClient()
            all_prs = github_client.get_pull_requests(owner, repo, state="all", retries=1)
            
            loc_reviewed = 0
            reviewed_prs = 0
            total_merged_prs = 0

            for pr in all_prs:
                # Only consider merged PRs (they're the ones that actually introduced code)
                if pr.get("state") != "closed" or not pr.get("merged_at"):
                    continue

                total_merged_prs += 1
                additions = pr.get("additions", 0) or 0

                # Check if PR has reviews (specifically approvals)
                pr_number = pr.get("number")
                if pr_number:
                    try:
                        reviews = github_client.get_pull_request_reviews(
                            owner, repo, pr_number, retries=1
                        )
                        if self._has_code_review(reviews):
                            loc_reviewed += additions
                            reviewed_prs += 1
                    except Exception as e:
                        # If we can't fetch reviews (e.g., rate limit), skip this PR
                        logger.warning(f"Could not fetch reviews for PR #{pr_number}: {e}")
                        continue

            # Step 3: Calculate reviewedness = LOC_reviewed / LOC_total
            # Cap at 1.0 since LOC_reviewed might exceed LOC_total due to multiple PRs modifying same files
            reviewedness = min(loc_reviewed / loc_total, 1.0) if loc_total > 0 else 0.0

            self.value = reviewedness
            self.latency_ms = int(round((time.perf_counter() - start) * 1000))
            self.details = {
                "loc_total": loc_total,
                "loc_reviewed": loc_reviewed,
                "total_merged_prs": total_merged_prs,
                "reviewed_prs": reviewed_prs,
                "reviewedness": reviewedness
            }

            logger.info(
                f"Reviewedness for {owner}/{repo}: {reviewed_prs}/{total_merged_prs} PRs reviewed, "
                f"{loc_reviewed}/{loc_total} LOC from reviewed PRs, reviewedness={reviewedness:.3f}"
            )

        except Exception as e:
            logger.error(f"Error computing Reviewedness: {e}")
            self.value = -1.0
            self.latency_ms = int(round((time.perf_counter() - start) * 1000))
            self.details = {"error": str(e)}

