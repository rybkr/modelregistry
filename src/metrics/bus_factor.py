import math
import time
from datetime import datetime, timezone
from typing import Dict, Optional

from log import logger
from metrics.base_metric import Metric
from models import Model


class BusFactor(Metric):
    """Calculates the Bus Factor score (contributors + recency only)."""

    def __init__(self) -> None:
        super().__init__("bus_factor")

    def _get_last_modified(self, model: Model) -> Dict[str, Optional[str]]:
        """Fetch last modified dates from model, dataset, and code."""
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
        """Fetch number of contributors from code metadata (if available)."""
        contributors: int = 1
        if model.code:
            try:
                code_meta = model.code.fetch_metadata()
                contributors = int(code_meta.get("contributors", contributors))
            except Exception:
                pass
        return contributors

    def compute_score(
        self,
        contributors: int,
        n_code: int,
        freshest: Optional[str],
    ) -> Dict[str, float]:
        """Compute the base score, recency score, and final score."""
        contributor_score = min(1.0, contributors / 10.0)
        base_score = contributor_score / max(1, n_code)

        recency_score = 1.0
        if freshest:
            try:
                dt = datetime.fromisoformat(freshest.replace("Z", "+00:00"))
                days_since = (datetime.now(timezone.utc) - dt).days
                recency_score = math.exp(-math.log(2) * days_since / 365)
            except Exception:
                pass

        final_score = max(0.0, min(1.0, base_score * recency_score))

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
