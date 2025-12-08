from __future__ import annotations

import subprocess
import time
from typing import Any, Optional

from adapters.code_fetchers import open_codebase
from adapters.repo_view import RepoView
from log import logger
from metrics.base_metric import Metric
from models import Model
from resources.base_resource import _BaseResource
from resources.code_resource import CodeResource


def try_readme(resource: _BaseResource, filename: str = "README.md") -> Optional[str]:
    """Attempt to fetch README.md via the resource's RepoView."""
    try:
        with resource.open_files(allow_patterns=[filename]) as repo:
            if repo.exists(filename):
                return repo.read_text(filename)
    except Exception:
        return None
    return None


class CodeQuality(Metric):
    """Metric for code quality: flake8 + mypy + stars/likes."""

    def __init__(self) -> None:
        super().__init__(name="code_quality")

    def _run_linter(self, repo: RepoView, cmd: list[str]) -> float:
        """Run a linter command in the given repository and compute a score."""
        proc: subprocess.CompletedProcess[str] = subprocess.run(
            cmd,
            cwd=repo.root,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            return 1.0

        errors: int = proc.stdout.count("\n") + proc.stderr.count("\n")

        if errors == 0:
            return 1.0
        if errors < 10:
            return 0.8
        if errors < 50:
            return 0.6
        return 0.4

    def _flake8_score(self, repo: RepoView) -> float:
        return self._run_linter(repo, ["flake8", "."])

    def _mypy_score(self, repo: RepoView) -> float:
        return self._run_linter(repo, ["mypy", "--strict", "."])

    def _stars_score(self, url: str) -> float:
        """Fetch metadata for repo and convert stars/likes count to a score."""
        meta: dict[str, Any] = CodeResource(url).fetch_metadata() or {}

        if "stargazers_count" in meta:  # GitHub
            raw: int = int(meta.get("stargazers_count", 0))
        elif "star_count" in meta:  # GitLab
            raw = int(meta.get("star_count", 0))
        elif "likes" in meta:  # Hugging Face
            raw = int(meta.get("likes", 0))
        else:
            raw = 0

        if raw <= 0:
            return 0.0
        if raw < 50:
            return 0.5
        return 1.0

    def compute(self, model: Model) -> None:
        """Run code quality analysis on the model's code URL."""
        logger.info("Computing Code Quality metric...")
        start: float = time.perf_counter()
        try:
            # If your Model is a dict-like, .get() is valid.
            url: str | None = model.code.url if model.code else None
            if not url:
                # Check if README mentions code - give partial credit
                readme: Optional[str] = None
                if model.model:
                    readme = try_readme(model.model)
                
                if readme:
                    readme_lower = readme.lower()
                    code_keywords = [
                        "code", "github", "repository", "repo", "open-source", "open source",
                        "source code", "open-sourced", "open sourced", "available", "download",
                        "checkpoint", "implementation", "example", "script", "notebook"
                    ]
                    has_code_mention = any(keyword in readme_lower for keyword in code_keywords)
                    
                    if has_code_mention:
                        # Give partial credit for mentioning code in README
                        self.value = 0.6
                        self.latency_ms = int(round((time.perf_counter() - start) * 1000))
                        self.details = {
                            "partial_credit": True,
                            "reason": "Code mentioned in README but no code URL provided"
                        }
                        logger.info("Code mentioned in README, giving partial credit 0.6")
                        return None
                
                self.value = 0.0
                self.latency_ms = int(round((time.perf_counter() - start) * 1000))
                self.details = {"error": "No code URL provided"}
                logger.warning("No code URL provided for Code Quality metric")
                return None

            with open_codebase(url) as repo:
                flake8: float = self._flake8_score(repo)
                mypy: float = self._mypy_score(repo)

            stars: float = self._stars_score(url)
            score: float = (flake8 + mypy + stars) / 3.0

            self.value = score
            self.latency_ms = int(round((time.perf_counter() - start) * 1000))
            self.details = {
                "flake8": flake8,
                "mypy": mypy,
                "stars": stars,
            }

            logger.debug(
                f"Code Quality scores for {url}: flake8={flake8}, "
                f"mypy={mypy}, stars={stars}, final={score}"
            )
        except Exception as e:
            logger.error(f"Error computing Code Quality: {e}")
            self.value = 0.0
            self.latency_ms = int(round((time.perf_counter() - start) * 1000))
            self.details = {"error": str(e)}
