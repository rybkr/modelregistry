from __future__ import annotations

import time
from typing import Any, Dict, Optional

from log import logger
from metrics.base_metric import Metric
from models import Model


class DatasetQuality(Metric):
    """Metric for evaluating dataset quality using metadata and repository info."""

    def __init__(self) -> None:
        super().__init__(name="dataset_quality")

    # --- Sub-metrics ---
    def _documentation_score(self, dataset: Dict[str, Any]) -> float:
        """Check for dataset card fields like description, license, homepage."""
        required_fields = ["description", "license", "homepage"]
        present = sum(1 for field in required_fields if dataset.get(field))
        return present / len(required_fields)

    def _license_and_citation_score(self, dataset: Dict[str, Any]) -> float:
        """Score license clarity (GitHub API provides license.name)."""
        if dataset.get("license") and dataset["license"].get("name"):
            return 1.0
        return 0.0

    def _freshness_score(self, dataset: Dict[str, Any]) -> float:
        """Score based on updated_at field (ISO date string)."""
        updated_at: Optional[str] = dataset.get("updated_at")
        if not updated_at:
            return 0.5

        try:
            from datetime import datetime, timezone

            updated = datetime.strptime(updated_at, "%Y-%m-%dT%H:%M:%SZ")
            age_days = (datetime.now(timezone.utc) - updated).days
            if age_days <= 183:
                return 1.0
            if age_days <= 548:
                return 0.5
            return 0.2
        except Exception:
            return 0.5

    def _community_score(self, dataset: Dict[str, Any]) -> float:
        """Score based on GitHub stars, forks, watchers, subscribers."""
        stars = dataset.get("stargazers_count", 0)
        forks = dataset.get("forks_count", 0)
        watchers = dataset.get("watchers_count", 0)
        subs = dataset.get("subscribers_count", 0)

        star_score = min(stars / 100.0, 1.0)
        fork_score = min(forks / 50.0, 1.0)
        watch_score = min(watchers / 100.0, 1.0)
        sub_score = min(subs / 20.0, 1.0)

        return float(
            0.5 * star_score + 0.2 * fork_score + 0.2 * watch_score + 0.1 * sub_score
        )

    def _example_code_score(self, dataset: Dict[str, Any]) -> float:
        """Check topics for 'example' or 'tutorial'."""
        topics = dataset.get("topics", [])
        if any(t for t in topics if "example" in t or "tutorial" in t):
            return 1.0
        return 0.0

    # --- Main compute ---
    def compute(self, model: Model) -> None:
        """Compute dataset quality for a given model and update fields."""
        logger.info("Computing DatasetQuality metric...")
        start = time.time()
        try:
            if model.dataset is None:
                self.value = 0.0
                self.details = {"error": "No dataset provided"}
                self.latency_ms = int(round((time.time() - start) * 1000))
                logger.warning("No dataset provided for DatasetQuality metric")
                return

            dataset_meta: Dict[str, Any] = model.dataset.fetch_metadata()

            doc_score = self._documentation_score(dataset_meta)
            lic_score = self._license_and_citation_score(dataset_meta)
            fresh_score = self._freshness_score(dataset_meta)
            comm_score = self._community_score(dataset_meta)
            ex_score = self._example_code_score(dataset_meta)

            total_score = (
                0.3 * doc_score
                + 0.2 * lic_score
                + 0.2 * fresh_score
                + 0.2 * comm_score
                + 0.1 * ex_score
            )

            self.value = round(total_score, 3)
            self.details = {
                "documentation": doc_score,
                "license": lic_score,
                "freshness": fresh_score,
                "community": comm_score,
                "example_code": ex_score,
            }
            self.latency_ms = int(round((time.time() - start) * 1000))

            logger.debug(
                f"DatasetQuality scores: doc={doc_score}, license={lic_score}, "
                f"freshness={fresh_score}, community={comm_score}, "
                f"example_code={ex_score}, final={self.value}"
            )
        except Exception as e:
            logger.error(f"Error computing DatasetQuality metric: {e}")
            self.value = 0.0
            self.latency_ms = int(round((time.time() - start) * 1000))
            self.details = {"error": str(e)}
