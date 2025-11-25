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
        pass
    return None

# Extensions to exclude from LOC counting
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
        self.github_token: Optional[str] = os.getenv("GITHUB_TOKEN")

    def _is_github_url(self, url: str) -> bool:
        """Check if URL is a GitHub repository URL."""
        return "github.com" in url.lower()

    def _extract_github_urls_from_text(self, text: str) -> list[str]:
        """Extract GitHub repository URLs from text.
        
        Handles markdown links, HTML links, plain URLs, and text references.
        
        Args:
            text: Text content to search for GitHub URLs
            
        Returns:
            List of unique GitHub repository URLs found
        """
        cleaned_urls = []
        
        # Match markdown links: [text](url)
        markdown_link_pattern = r'\[[^\]]*?\]\(\s*(https?://(?:www\.)?github\.com/[\w\.-]+/[\w\.-]+[^\s\)]*?)(?:\s+["\'][^"\']*["\'])?\s*\)'
        for match in re.finditer(markdown_link_pattern, text, re.IGNORECASE):
            cleaned_urls.extend(self._normalize_github_url(match.group(1).strip()))
        
        # Match HTML links: <a href="url">
        html_link_pattern = r'<a\s+[^>]*href\s*=\s*["\'](https?://(?:www\.)?github\.com/[\w\.-]+/[\w\.-]+[^\s"\'>]*)["\']'
        for match in re.finditer(html_link_pattern, text, re.IGNORECASE):
            cleaned_urls.extend(self._normalize_github_url(match.group(1).strip()))
        
        # Match URLs in parentheses
        paren_url_pattern = r'\((\s*https?://(?:www\.)?github\.com/[\w\.-]+/[\w\.-]+[^\s\)]*)\)'
        for match in re.finditer(paren_url_pattern, text, re.IGNORECASE):
            cleaned_urls.extend(self._normalize_github_url(match.group(1).strip()))
        
        # Match standalone GitHub URLs
        github_url_pattern = r'https?://(?:www\.)?github\.com/[\w\.-]+/[\w\.-]+(?:/tree/[\w\.-]+)?(?:/blob/[\w\.-]+)?(?:/[\w\.-]+)*(?:\?[^\s\)\]\}<>]*)?(?:#[^\s\)\]\}<>]*)?'
        for match in re.finditer(github_url_pattern, text, re.IGNORECASE):
            cleaned_urls.extend(self._normalize_github_url(match.group(0)))
        
        # Match github.com URLs without protocol
        no_protocol_pattern = r'(?:^|[\s\(\[\{<>])github\.com/[\w\.-]+/[\w\.-]+(?:/tree/[\w\.-]+)?(?:/blob/[\w\.-]+)?(?:/[\w\.-]+)*(?:\?[^\s\)\]\}<>]*)?(?:#[^\s\)\]\}<>]*)?'
        for match in re.finditer(no_protocol_pattern, text, re.IGNORECASE | re.MULTILINE):
            url = match.group(0).strip().lstrip('([').lstrip('<>')
            if not url.startswith('http'):
                url = f"https://{url}"
            cleaned_urls.extend(self._normalize_github_url(url))
        
        return list(dict.fromkeys(cleaned_urls))
    
    def _normalize_github_url(self, url: str) -> list[str]:
        """Normalize GitHub URL to clean owner/repo format."""
        if not url:
            return []
        
        url = url.strip().rstrip('/)').rstrip(']').rstrip('}').rstrip('.')
        url = url.split('?')[0].split('#')[0]
        
        match = re.search(r'github\.com/([\w\.-]+/[\w\.-]+)', url, re.IGNORECASE)
        if match:
            return [f"https://github.com/{match.group(1)}"]
        return []

    def _find_github_url_in_model_card(self, model: Model) -> Optional[str]:
        """Find GitHub repository URL in model card README or metadata."""
        all_text_sources: list[str] = []
        
        # Get README from model repository
        if model.model:
            readme = try_readme(model.model)
            if readme:
                all_text_sources.append(readme)
        
        # Get model metadata description
        if model.model:
            try:
                metadata = model.model.fetch_metadata()
                if metadata and isinstance(metadata, dict):
                    description_fields = ["description", "model_summary", "summary", "card_data"]
                    for field in description_fields:
                        if field in metadata:
                            field_value = metadata[field]
                            if isinstance(field_value, str) and field_value.strip():
                                all_text_sources.append(field_value)
                            elif isinstance(field_value, dict) and "content" in field_value:
                                if isinstance(field_value["content"], str):
                                    all_text_sources.append(field_value["content"])
            except Exception as e:
                logger.debug(f"Could not fetch model metadata: {e}")
        
        # Search all text sources for GitHub URLs
        for text in all_text_sources:
            if text:
                github_urls = self._extract_github_urls_from_text(text)
                if github_urls:
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
        """Check if PR has at least one APPROVED or CHANGES_REQUESTED review."""
        if not reviews:
            return False
        
        for review in reviews:
            state = review.get("state", "").upper()
            if state in ("APPROVED", "CHANGES_REQUESTED"):
                return True
        return False

    def _should_exclude_file(self, file_path: Path) -> bool:
        """Check if file should be excluded from LOC counting."""
        if file_path.suffix.lower() in EXCLUDED_EXTENSIONS:
            return True
        
        # Exclude files larger than 10MB
        try:
            if file_path.stat().st_size > 10 * 1024 * 1024:
                return True
        except (OSError, AttributeError):
            pass
        
        return False

    def _count_loc_in_repo(self, repo_path: Path) -> int:
        """Count total lines of code in repository, excluding binaries and weight files."""
        total_loc = 0
        skip_dirs = {".git", ".svn", ".hg", "__pycache__", "node_modules", 
                     ".pytest_cache", ".mypy_cache", ".venv", "venv", "env",
                     "dist", "build", ".egg-info", ".tox", ".coverage", "htmlcov"}
        
        for file_path in repo_path.rglob("*"):
            if not file_path.is_file():
                continue
            
            if any(part in skip_dirs for part in file_path.parts):
                continue
            
            if file_path.name.startswith("."):
                continue
            
            if self._should_exclude_file(file_path):
                continue
            
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    total_loc += sum(1 for _ in f)
            except (UnicodeDecodeError, IOError, PermissionError):
                continue
        
        return total_loc

    def compute(self, model: Model) -> None:
        """Compute reviewedness metric: LOC_reviewed / LOC_total.
        
        Returns -1 if no GitHub repository, 0.0 if LOC_total = 0.
        """
        logger.info("Computing Reviewedness metric...")
        start: float = time.perf_counter()
        
        try:
            # Try explicit code URL first, then search model card
            url: str | None = None
            code_url: str | None = model.code.url if model.code else None
            if code_url and self._is_github_url(code_url):
                url = code_url
                logger.info(f"Using GitHub URL from code field: {url}")
            
            if not url:
                url = self._find_github_url_in_model_card(model)
                if url:
                    logger.info(f"Found GitHub URL in model card: {url}")
            
            if not url:
                self.value = -1.0
                self.latency_ms = int(round((time.perf_counter() - start) * 1000))
                self.details = {"error": "No GitHub repository found in model card or code URL"}
                logger.warning("No GitHub repository found in model card or code URL")
                return
            
            logger.info(f"Using GitHub URL for reviewedness evaluation: {url}")

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

            # Get total LOC in repository
            loc_total = 0
            try:
                with open_codebase(url, token=self.github_token) as repo_view:
                    loc_total = self._count_loc_in_repo(repo_view.root)
                    logger.info(f"Total LOC in repository: {loc_total}")
            except Exception as e:
                logger.error(f"Error fetching/counting LOC in repository {url}: {e}")
                import traceback
                logger.debug(f"Traceback: {traceback.format_exc()}")
                
                error_str = str(e).lower()
                if any(keyword in error_str for keyword in ['404', 'not found', 'does not exist', 'could not find']):
                    self.value = -1.0
                    self.latency_ms = int(round((time.perf_counter() - start) * 1000))
                    self.details = {"error": f"Repository not found: {str(e)}", "url": url}
                    logger.warning(f"Repository {url} not found, returning -1")
                    return
                
                if any(keyword in error_str for keyword in ['rate limit', '403', '429', 'too many requests']):
                    self.value = -1.0
                    self.latency_ms = int(round((time.perf_counter() - start) * 1000))
                    self.details = {
                        "error": f"GitHub API rate limit exceeded: {str(e)}. Consider using a GitHub token.",
                        "url": url,
                        "rate_limited": True
                    }
                    logger.warning(f"Rate limit exceeded for {url}, returning -1")
                    return
                
                self.value = -1.0
                self.latency_ms = int(round((time.perf_counter() - start) * 1000))
                self.details = {"error": f"Could not access repository: {str(e)}", "url": url}
                logger.warning(f"Could not access repository {url}, returning -1")
                return

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

            # Get all merged pull requests and sum additions from reviewed PRs
            github_client = GitHubClient()
            logger.info(f"Fetching pull requests for {owner}/{repo}...")
            try:
                all_prs = github_client.get_pull_requests(
                    owner, repo, state="all", retries=1, token=self.github_token
                )
                logger.info(f"Found {len(all_prs)} total pull requests")
            except Exception as e:
                logger.error(f"Error fetching pull requests: {e}")
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
            reviewed_pr_details = []

            for pr in all_prs:
                if pr.get("state") != "closed" or not pr.get("merged_at"):
                    continue

                total_merged_prs += 1
                pr_number = pr.get("number")
                if not pr_number:
                    continue

                additions = pr.get("additions")
                deletions = pr.get("deletions")
                
                if additions is None or deletions is None:
                    logger.debug(f"PR #{pr_number}: fetching details...")
                    try:
                        pr_detail = github_client.get_pull_request(
                            owner, repo, pr_number, retries=1, token=self.github_token
                        )
                        if pr_detail:
                            additions = pr_detail.get("additions", 0)
                            deletions = pr_detail.get("deletions", 0)
                        else:
                            additions = deletions = 0
                    except Exception as e:
                        logger.warning(f"PR #{pr_number}: Error fetching details: {e}")
                        additions = deletions = 0
                
                additions = int(additions) if additions is not None else 0
                deletions = int(deletions) if deletions is not None else 0

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
                        logger.info(f"PR #{pr_number}: {additions} additions, reviewed=True")
                except Exception as e:
                    logger.warning(f"Could not fetch reviews for PR #{pr_number}: {e}")
                    continue
            
            logger.info(f"Processed PRs: {total_merged_prs} merged, {reviewed_prs} reviewed, {loc_reviewed} LOC from reviewed PRs")
            
            if reviewed_prs > 0 and loc_reviewed == 0:
                logger.warning(f"Found {reviewed_prs} reviewed PRs but 0 additions total. Reviewed PRs:")
                for pr_detail in reviewed_pr_details:
                    logger.warning(f"  PR #{pr_detail['pr_number']}: {pr_detail['additions']} additions")

            # Calculate reviewedness (cap at 1.0)
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
