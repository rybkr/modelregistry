from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

from adapters.client import GitHubClient
from log import logger
from metrics.base_metric import Metric
from models import Model
from resources.code_resource import CodeResource


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
        """Check if a PR has at least one code review (approved, changes_requested, or commented).

        Args:
            reviews: List of review dictionaries from GitHub API

        Returns:
            True if PR has at least one review, False otherwise
        """
        if not reviews:
            return False
        
        # A review is considered valid if it has a state (APPROVED, CHANGES_REQUESTED, COMMENTED)
        # and is not a PENDING review
        for review in reviews:
            state = review.get("state", "").upper()
            if state in ("APPROVED", "CHANGES_REQUESTED", "COMMENTED"):
                return True
        
        return False

    def compute(self, model: Model) -> None:
        """Compute reviewedness metric for the model's code repository."""
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
            logger.info(f"Fetching pull requests for {owner}/{repo}")

            # Get all merged pull requests
            github_client = GitHubClient()
            all_prs = github_client.get_pull_requests(owner, repo, state="all", retries=1)
            
            if not all_prs:
                # No PRs found - could mean no code was introduced via PRs
                # Return 0.0 to indicate no reviewed code
                self.value = 0.0
                self.latency_ms = int(round((time.perf_counter() - start) * 1000))
                self.details = {
                    "total_prs": 0,
                    "reviewed_prs": 0,
                    "total_additions": 0,
                    "reviewed_additions": 0,
                    "reason": "No pull requests found"
                }
                logger.info(f"No pull requests found for {owner}/{repo}")
                return

            # Calculate total code additions and reviewed code additions
            total_additions = 0
            reviewed_additions = 0
            reviewed_prs = 0
            total_merged_prs = 0

            for pr in all_prs:
                # Only consider merged PRs (they're the ones that actually introduced code)
                if pr.get("state") != "closed" or not pr.get("merged_at"):
                    continue

                total_merged_prs += 1
                additions = pr.get("additions", 0) or 0
                deletions = pr.get("deletions", 0) or 0
                # Count all additions as code introduced (not net, since we're measuring code introduced)
                total_additions += additions

                # Check if PR has reviews
                pr_number = pr.get("number")
                if pr_number:
                    try:
                        reviews = github_client.get_pull_request_reviews(
                            owner, repo, pr_number, retries=1
                        )
                        if self._has_code_review(reviews):
                            reviewed_additions += additions
                            reviewed_prs += 1
                    except Exception as e:
                        # If we can't fetch reviews (e.g., rate limit), skip this PR
                        logger.warning(f"Could not fetch reviews for PR #{pr_number}: {e}")
                        continue

            # Calculate fraction
            if total_additions == 0:
                # No code was added via PRs
                self.value = 0.0
                self.latency_ms = int(round((time.perf_counter() - start) * 1000))
                self.details = {
                    "total_prs": total_merged_prs,
                    "reviewed_prs": reviewed_prs,
                    "total_additions": total_additions,
                    "reviewed_additions": reviewed_additions,
                    "reason": "No code additions found in PRs"
                }
                logger.info(f"No code additions found in PRs for {owner}/{repo}")
                return

            fraction = reviewed_additions / total_additions
            self.value = fraction
            self.latency_ms = int(round((time.perf_counter() - start) * 1000))
            self.details = {
                "total_prs": total_merged_prs,
                "reviewed_prs": reviewed_prs,
                "total_additions": total_additions,
                "reviewed_additions": reviewed_additions,
                "fraction": fraction
            }

            logger.info(
                f"Reviewedness for {owner}/{repo}: {reviewed_prs}/{total_merged_prs} PRs reviewed, "
                f"{reviewed_additions}/{total_additions} additions reviewed, fraction={fraction:.3f}"
            )

        except Exception as e:
            logger.error(f"Error computing Reviewedness: {e}")
            self.value = -1.0
            self.latency_ms = int(round((time.perf_counter() - start) * 1000))
            self.details = {"error": str(e)}

