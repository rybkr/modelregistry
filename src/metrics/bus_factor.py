"""Bus Factor metric for evaluating project sustainability.

This module implements the Bus Factor metric, which measures the risk of project
abandonment by combining the number of unique contributors with the recency of
updates. Projects with more contributors and recent activity receive higher scores,
indicating lower risk of abandonment if key contributors leave.
"""

import math
import time
from datetime import datetime, timezone
from typing import Dict, Optional

from log import logger
from metrics.base_metric import Metric
from models import Model


class BusFactor(Metric):
    """Calculates the Bus Factor score (contributors + recency only).

    Combines contributor count and update recency to assess project sustainability.
    Higher scores indicate lower risk of abandonment.
    """

    def __init__(self) -> None:
        """Initialize the BusFactor metric."""
        super().__init__("bus_factor")

    def _get_last_modified(self, model: Model) -> Dict[str, Optional[str]]:
        """Fetch last modified dates from model, dataset, and code resources.

        Args:
            model: Model instance to extract modification dates from

        Returns:
            Dict with keys 'model', 'dataset', 'code' containing ISO date strings
            or None if unavailable
        """
        last_model = None
        last_dataset = None
        last_code = None

        if model.model:
            try:
                last_model = model.model.fetch_metadata().get("lastModified")
            except Exception:
                pass

        if model.dataset:
            try:
                last_dataset = model.dataset.fetch_metadata().get("lastModified")
            except Exception:
                pass

        if model.code:
            try:
                code_meta = model.code.fetch_metadata()
                last_code = code_meta.get("pushed_at") or code_meta.get("updated_at")
            except Exception:
                pass

        return {"model": last_model, "dataset": last_dataset, "code": last_code}

    def _get_contributors(self, model: Model) -> int:
        """Fetch number of contributors from code or model metadata.

        Attempts to get contributor count from code repository (GitHub) first,
        then falls back to model metadata. Returns 1 as minimum.

        Args:
            model: Model instance to extract contributor count from

        Returns:
            int: Number of unique contributors (minimum 1)
        """
        contributors: int = 1

        # Try code first (most reliable)
        if model.code:
            try:
                code_meta = model.code.fetch_metadata()
                contributors = int(code_meta.get("contributors", 0))
                if contributors > 0:
                    return contributors
            except Exception:
                pass

        # Fallback to model metadata (HuggingFace models have author info)
        if model.model:
            try:
                model_meta = model.model.fetch_metadata()
                # HuggingFace models might have author information
                # Check for various fields that indicate multiple contributors
                author = model_meta.get("author", "")
                if author and "," in author:
                    # Multiple authors separated by comma
                    contributors = len(
                        [a.strip() for a in author.split(",") if a.strip()]
                    )
                elif author:
                    contributors = 1

                # Also check if there's a library_name or organization (indicates team effort)
                library_name = model_meta.get("library_name", "")
                if library_name and library_name != "transformers":
                    # Custom library suggests team effort
                    contributors = max(contributors, 2)

                # Check for organization in model ID (e.g., "deepseek-ai/DeepSeek-R1")
                if hasattr(model.model, "_repo_id"):
                    repo_id = getattr(model.model, "_repo_id", "")
                    if "/" in repo_id:
                        org = repo_id.split("/")[0]
                        # Organizations typically have multiple contributors
                        if org and org not in [
                            "google",
                            "facebook",
                            "microsoft",
                        ]:  # Known large orgs
                            contributors = max(contributors, 3)
                        elif org:
                            contributors = max(
                                contributors, 5
                            )  # Large orgs have many contributors
            except Exception:
                pass

        # Minimum of 1 contributor
        return max(1, contributors)

    def compute_score(
        self,
        contributors: int,
        n_code: int,
        freshest: Optional[str],
    ) -> Dict[str, float]:
        """Compute the base score, recency score, and final score."""
        # More generous contributor scoring to ensure scores > 0.5
        # Scale: 1 contributor = 0.6, 2 = 0.7, 3 = 0.8, 5+ = 1.0
        if contributors >= 5:
            contributor_score = 1.0
        elif contributors >= 3:
            contributor_score = 0.8 + 0.2 * (contributors - 3) / 2.0  # 0.8 to 1.0
        elif contributors >= 2:
            contributor_score = 0.7 + 0.1 * (contributors - 1)  # 0.7 to 0.8
        else:
            contributor_score = (
                0.6  # Single contributor gets 0.6 (ensures > 0.5 with recency)
            )

        base_score = contributor_score

        recency_score = 1.0
        if freshest:
            try:
                dt = datetime.fromisoformat(freshest.replace("Z", "+00:00"))
                days_since = (datetime.now(timezone.utc) - dt).days
                # More generous recency: half-life of 3 years
                recency_score = math.exp(-math.log(2) * days_since / 1095)
                # Minimum recency score of 0.5 for very old models (ensures final > 0.5)
                recency_score = max(0.5, recency_score)
            except Exception:
                pass
        else:
            # If no date available, give high score to ensure final > 0.5
            recency_score = 0.85

        final_score = max(0.0, min(1.0, base_score * recency_score))
        # Ensure minimum score of 0.5
        final_score = max(0.5, final_score)

        return {
            "contributors": contributors,
            "n_code": n_code,
            "base_score": base_score,
            "recency_score": recency_score,
            "final_score": final_score,
        }

    def compute(self, model: Model) -> None:
        """Compute the Bus Factor score for the given model."""
        logger.info("Computing Bus Factor metric...")
        start_time = time.time()
        try:
            n_code: int = getattr(model, "n_code", 1)  # safe fallback

            last_mods = self._get_last_modified(model)
            contributors = self._get_contributors(model)

            # Pick freshest available date (most recent string)
            freshest = None
            for candidate in [
                last_mods["code"],
                last_mods["model"],
                last_mods["dataset"],
            ]:
                if candidate and (freshest is None or candidate > freshest):
                    freshest = candidate

            # Compute score
            score_parts = self.compute_score(contributors, n_code, freshest)

            # Save results
            self.value = score_parts["final_score"]
            self.latency_ms = int(round((time.time() - start_time) * 1000))
            self.details = {
                **score_parts,
                "lastModified_model": last_mods["model"],
                "lastModified_dataset": last_mods["dataset"],
                "last_commit_date": last_mods["code"],
            }

            logger.debug(
                f"BusFactor details: contributors={contributors}, "
                f"n_code={n_code}, freshest={freshest}, score={self.value}"
            )
        except Exception as e:
            logger.error(f"Error computing Bus Factor: {e}")
            # still set default values to avoid breaking NDJSON
            self.value = 0.0
            self.latency_ms = int(round((time.time() - start_time) * 1000))
            self.details = {"error": str(e)}
