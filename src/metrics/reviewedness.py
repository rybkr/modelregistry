from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv

from adapters.client import GitHubClient
from adapters.code_fetchers import open_codebase
from log import logger
from metrics.base_metric import Metric
from models import Model
from resources.base_resource import _BaseResource

# Load environment variables from config.env if it exists
load_dotenv("config.env")


def try_readme(resource: _BaseResource, filename: str = "README.md") -> Optional[str]:
    """Attempt to fetch README.md via the resource's RepoView."""
    try:
        with resource.open_files(allow_patterns=[filename]) as repo:
            if repo.exists(filename):
                return repo.read_text(filename)
    except Exception:
        return None
    return None

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
        # Get GitHub token from environment variable
        self.github_token: Optional[str] = os.getenv("GITHUB_TOKEN")

    def _is_github_url(self, url: str) -> bool:
        """Check if URL is a GitHub repository URL."""
        return "github.com" in url.lower()

    def _extract_github_urls_from_text(self, text: str) -> list[str]:
        """Extract GitHub repository URLs from text (README, description, etc.).
        
        Handles various formats including:
        - Markdown links: [text](https://github.com/owner/repo)
        - HTML links: <a href="https://github.com/owner/repo">text</a>
        - Plain URLs in parentheses or brackets
        - Standalone URLs
        - Plain text references
        
        Args:
            text: Text content to search for GitHub URLs
            
        Returns:
            List of GitHub repository URLs found in the text
        """
        cleaned_urls = []
        
        # Pattern 1: Match markdown links: [text](https://github.com/owner/repo)
        # Also handles: [text](https://github.com/owner/repo "title") or [text](https://github.com/owner/repo 'title')
        markdown_link_pattern = r'\[[^\]]*?\]\(\s*(https?://(?:www\.)?github\.com/[\w\.-]+/[\w\.-]+[^\s\)]*?)(?:\s+["\'][^"\']*["\'])?\s*\)'
        markdown_matches = re.finditer(markdown_link_pattern, text, re.IGNORECASE)
        for match in markdown_matches:
            url = match.group(1).strip()
            cleaned_urls.extend(self._normalize_github_url(url))
        
        # Pattern 2: Match HTML links: <a href="https://github.com/owner/repo"> or <a href='...'>
        html_link_pattern = r'<a\s+[^>]*href\s*=\s*["\'](https?://(?:www\.)?github\.com/[\w\.-]+/[\w\.-]+[^\s"\'>]*)["\']'
        html_matches = re.finditer(html_link_pattern, text, re.IGNORECASE)
        for match in html_matches:
            url = match.group(1).strip()
            cleaned_urls.extend(self._normalize_github_url(url))
        
        # Pattern 3: Match GitHub URLs in parentheses: (https://github.com/owner/repo)
        # But skip if already matched as markdown link
        paren_url_pattern = r'\((\s*https?://(?:www\.)?github\.com/[\w\.-]+/[\w\.-]+[^\s\)]*)\)'
        paren_matches = re.finditer(paren_url_pattern, text, re.IGNORECASE)
        for match in paren_matches:
            url = match.group(1).strip()
            cleaned_urls.extend(self._normalize_github_url(url))
        
        # Pattern 3: Match standalone GitHub URLs
        # Matches: https://github.com/owner/repo, http://github.com/owner/repo,
        # github.com/owner/repo (without protocol), etc.
        github_url_pattern = r'https?://(?:www\.)?github\.com/[\w\.-]+/[\w\.-]+(?:/tree/[\w\.-]+)?(?:/blob/[\w\.-]+)?(?:/[\w\.-]+)*(?:\?[^\s\)\]\}<>]*)?(?:#[^\s\)\]\}<>]*)?'
        standalone_matches = re.finditer(github_url_pattern, text, re.IGNORECASE)
        for match in standalone_matches:
            url = match.group(0)
            cleaned_urls.extend(self._normalize_github_url(url))
        
        # Pattern 4: Match github.com URLs without protocol
        no_protocol_pattern = r'(?:^|[\s\(\[\{<>])github\.com/[\w\.-]+/[\w\.-]+(?:/tree/[\w\.-]+)?(?:/blob/[\w\.-]+)?(?:/[\w\.-]+)*(?:\?[^\s\)\]\}<>]*)?(?:#[^\s\)\]\}<>]*)?'
        no_protocol_matches = re.finditer(no_protocol_pattern, text, re.IGNORECASE | re.MULTILINE)
        for match in no_protocol_matches:
            url = match.group(0).strip().lstrip('([').lstrip('<>')
            if not url.startswith('http'):
                url = f"https://{url}"
            cleaned_urls.extend(self._normalize_github_url(url))
        
        # Remove duplicates while preserving order
        seen = set()
        unique_urls = []
        for url in cleaned_urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)
        
        return unique_urls
    
    def _normalize_github_url(self, url: str) -> list[str]:
        """Normalize a GitHub URL to clean owner/repo format.
        
        Args:
            url: GitHub URL string
            
        Returns:
            List with normalized URL (empty list if invalid)
        """
        if not url:
            return []
        
        # Remove trailing slash and punctuation
        url = url.strip().rstrip('/').rstrip(')').rstrip(']').rstrip('}').rstrip('.')
        
        # Remove query params and fragments (keep tree/blob paths for now)
        if '?' in url and '/tree/' not in url and '/blob/' not in url:
            url = url.split('?')[0]
        if '#' in url and '/tree/' not in url and '/blob/' not in url:
            url = url.split('#')[0]
        
        # Extract base repo URL (owner/repo)
        match = re.search(r'github\.com/([\w\.-]+/[\w\.-]+)', url, re.IGNORECASE)
        if match:
            owner_repo = match.group(1)
            # Reconstruct clean URL
            clean_url = f"https://github.com/{owner_repo}"
            return [clean_url]
        
        return []

    def _find_github_url_in_model_card(self, model: Model) -> Optional[str]:
        """Try to find a GitHub repository URL in the model card/README.
        
        Searches in:
        1. README.md file in the model repository
        2. Model metadata description field
        
        Handles links in various formats including markdown links like [text](url).
        
        Args:
            model: The model object
            
        Returns:
            GitHub repository URL if found, None otherwise
        """
        all_text_sources: list[str] = []
        
        # Source 1: Get README from model repository
        if model.model:
            readme = try_readme(model.model)
            if readme:
                all_text_sources.append(readme)
                logger.debug("Scanning README.md for GitHub repository links...")
        
        # Source 2: Get model metadata description (if available)
        if model.model:
            try:
                metadata = model.model.fetch_metadata()
                if metadata and isinstance(metadata, dict):
                    # Check various description fields that might contain GitHub links
                    description_fields = ["description", "model_summary", "summary", "card_data"]
                    for field in description_fields:
                        if field in metadata:
                            field_value = metadata[field]
                            if isinstance(field_value, str) and field_value.strip():
                                all_text_sources.append(field_value)
                                logger.debug(f"Scanning metadata field '{field}' for GitHub repository links...")
                            elif isinstance(field_value, dict):
                                # Sometimes description is nested in card_data
                                if "content" in field_value and isinstance(field_value["content"], str):
                                    all_text_sources.append(field_value["content"])
            except Exception as e:
                logger.debug(f"Could not fetch model metadata for description search: {e}")
        
        # Search all text sources for GitHub URLs
        for text in all_text_sources:
            if text:
                github_urls = self._extract_github_urls_from_text(text)
                if github_urls:
                    # Return the first GitHub URL found
                    logger.info(f"Found GitHub URL in model card: {github_urls[0]}")
                    return github_urls[0]
        
        return None

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
        """Check if a PR has at least one code review (approval or change request).
        
        Args:
            reviews: List of review dictionaries from GitHub API
            
        Returns:
            True if PR has at least one APPROVED or CHANGES_REQUESTED review, False otherwise
        """
        if not reviews:
            return False
        
        # A review is considered valid if it has state APPROVED or CHANGES_REQUESTED
        # Both indicate that the PR was actually reviewed by someone
        # COMMENTED reviews are not sufficient (just comments without actionable feedback)
        for review in reviews:
            state = review.get("state", "").upper()
            if state in ("APPROVED", "CHANGES_REQUESTED"):
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
            # First, check if code URL is explicitly provided and is a GitHub URL
            # This takes precedence over searching the model card
            url: str | None = None
            code_url: str | None = model.code.url if model.code else None
            if code_url and self._is_github_url(code_url):
                url = code_url
                logger.info(f"Using GitHub URL from code field: {url}")
            
            # If no code URL provided, search for GitHub repository link in the model card/README
            if not url:
                logger.info("No GitHub URL in code field, searching model card for GitHub repository link...")
                url = self._find_github_url_in_model_card(model)
                if url:
                    logger.info(f"Found GitHub URL in model card: {url}")
            
            # If still no GitHub URL found, return -1
            if not url:
                self.value = -1.0
                self.latency_ms = int(round((time.perf_counter() - start) * 1000))
                self.details = {"error": "No GitHub repository found in model card or code URL"}
                logger.warning("No GitHub repository found in model card or code URL")
                return
            
            logger.info(f"Using GitHub URL for reviewedness evaluation: {url}")

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
                logger.info(f"Attempting to fetch repository: {url}")
                # Pass GitHub token if available
                with open_codebase(url, token=self.github_token) as repo_view:
                    loc_total = self._count_loc_in_repo(repo_view.root)
                    logger.info(f"Total LOC in repository: {loc_total}")
            except Exception as e:
                logger.error(f"Error fetching/counting LOC in repository {url}: {e}")
                import traceback
                logger.debug(f"Traceback: {traceback.format_exc()}")
                # Check if this is a "repository not found" error - should return -1
                error_str = str(e).lower()
                if any(keyword in error_str for keyword in ['404', 'not found', 'does not exist', 'could not find']):
                    self.value = -1.0
                    self.latency_ms = int(round((time.perf_counter() - start) * 1000))
                    self.details = {"error": f"Repository not found: {str(e)}", "url": url}
                    logger.warning(f"Repository {url} not found, returning -1")
                    return
                # Check for rate limiting - provide helpful message
                if any(keyword in error_str for keyword in ['rate limit', '403', '429', 'too many requests']):
                    self.value = -1.0
                    self.latency_ms = int(round((time.perf_counter() - start) * 1000))
                    self.details = {
                        "error": f"GitHub API rate limit exceeded: {str(e)}. Consider using a GitHub token for higher limits.",
                        "url": url,
                        "rate_limited": True
                    }
                    logger.warning(f"Rate limit exceeded for {url}, returning -1")
                    return
                # For other errors (network, permissions, etc.), return -1 rather than 0
                # to distinguish from "repository exists but has no code"
                self.value = -1.0
                self.latency_ms = int(round((time.perf_counter() - start) * 1000))
                self.details = {"error": f"Could not access repository: {str(e)}", "url": url}
                logger.warning(f"Could not access repository {url}, returning -1")
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
            logger.info(f"Fetching pull requests for {owner}/{repo}...")
            if self.github_token:
                logger.info("Using GitHub token for authenticated API requests (higher rate limits)")
            try:
                all_prs = github_client.get_pull_requests(
                    owner, repo, state="all", retries=1, token=self.github_token
                )
                logger.info(f"Found {len(all_prs)} total pull requests")
            except Exception as e:
                logger.error(f"Error fetching pull requests: {e}")
                # If we can't fetch PRs, we can't compute reviewedness
                # This might be due to rate limiting, permissions, or API errors
                self.value = -1.0
                self.latency_ms = int(round((time.perf_counter() - start) * 1000))
                self.details = {
                    "error": f"Could not fetch pull requests: {str(e)}",
                    "loc_total": loc_total,
                    "url": url
                }
                return
            
            loc_reviewed = 0
            reviewed_prs = 0
            total_merged_prs = 0
            reviewed_pr_details = []  # Track which PRs were reviewed and their additions

            for pr in all_prs:
                # Only consider merged PRs (they're the ones that actually introduced code)
                if pr.get("state") != "closed" or not pr.get("merged_at"):
                    continue

                total_merged_prs += 1
                pr_number = pr.get("number")
                if not pr_number:
                    logger.debug("PR without number, skipping")
                    continue

                # Get additions and deletions from PR list response
                additions = pr.get("additions")
                deletions = pr.get("deletions")
                
                # If additions/deletions are missing from list response, fetch individual PR details
                if additions is None or deletions is None:
                    logger.debug(f"PR #{pr_number}: additions/deletions missing from list, fetching individual PR details...")
                    try:
                        pr_detail = github_client.get_pull_request(
                            owner, repo, pr_number, retries=1, token=self.github_token
                        )
                        if pr_detail:
                            additions = pr_detail.get("additions", 0)
                            deletions = pr_detail.get("deletions", 0)
                            logger.debug(f"PR #{pr_number}: Fetched from detail - {additions} additions, {deletions} deletions")
                        else:
                            logger.warning(f"PR #{pr_number}: Could not fetch PR details, defaulting to 0")
                            additions = 0
                            deletions = 0
                    except Exception as e:
                        logger.warning(f"PR #{pr_number}: Error fetching PR details: {e}, defaulting to 0")
                        additions = 0
                        deletions = 0
                
                # Ensure we have valid integers
                additions = int(additions) if additions is not None else 0
                deletions = int(deletions) if deletions is not None else 0

                # Check if PR has reviews (specifically approvals or change requests)
                try:
                    reviews = github_client.get_pull_request_reviews(
                        owner, repo, pr_number, retries=1, token=self.github_token
                    )
                    if self._has_code_review(reviews):
                        loc_reviewed += additions
                        reviewed_prs += 1
                        reviewed_pr_details.append({
                            "pr_number": pr_number,
                            "additions": additions,
                            "deletions": deletions
                        })
                        logger.info(f"PR #{pr_number}: {additions} additions, {deletions} deletions, reviewed=True")
                    else:
                        logger.debug(f"PR #{pr_number}: {additions} additions, reviewed=False")
                except Exception as e:
                    # If we can't fetch reviews (e.g., rate limit), skip this PR
                    logger.warning(f"Could not fetch reviews for PR #{pr_number}: {e}")
                    continue
            
            logger.info(f"Processed PRs: {total_merged_prs} merged, {reviewed_prs} reviewed, {loc_reviewed} LOC from reviewed PRs")
            
            # Log details about reviewed PRs if they have 0 additions
            if reviewed_prs > 0 and loc_reviewed == 0:
                logger.warning(f"Found {reviewed_prs} reviewed PRs but 0 additions total. Reviewed PRs:")
                for pr_detail in reviewed_pr_details:
                    logger.warning(f"  PR #{pr_detail['pr_number']}: {pr_detail['additions']} additions, {pr_detail['deletions']} deletions")

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
                "reviewed_pr_details": reviewed_pr_details if reviewed_prs > 0 else [],
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

