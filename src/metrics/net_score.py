"""Net Score metric for computing weighted aggregate quality scores.

This module implements the NetScore metric, which combines multiple quality
metrics into a single weighted score. The weights reflect the relative importance
of each metric, with core metrics (license, ramp-up time, bus factor) receiving
higher weights than optional metrics (dataset quality, code quality).
"""

from __future__ import annotations

import statistics
import time
from typing import Dict, Optional

from log import logger
from metrics.base_metric import Metric

# Metric weights - adjusted for more sensible scoring
# Core metrics (always available) get higher weights
# Optional metrics (may not exist) get lower weights and don't penalize when missing
METRIC_WEIGHTS: Dict[str, float] = {
    "license": 0.20,  # Core: Always should have license
    "ramp_up_time": 0.18,  # Core: Documentation quality
    "bus_factor": 0.15,  # Core: Project sustainability
    "performance_claims": 0.15,  # Core: Performance documentation
    "size": 0.12,  # Core: Model size compatibility
    "dataset_and_code_score": 0.10,  # Optional: Documentation of dataset/code
    "dataset_quality": 0.05,  # Optional: Only if dataset exists
    "code_quality": 0.05,  # Optional: Only if code exists
}


class NetScore(Metric):
    """Aggregate metric runner for computing weighted net score."""

    def __init__(self) -> None:
        """Initialize available metrics."""
        """Initialize metric with name."""
        super().__init__(name="net_score")

    def evaluate(self, metrics: list[Metric]) -> None:
        """Compute weighted net score from a list of metric results.

        Aggregates multiple metric scores into a single weighted average, where
        each metric's contribution is weighted according to METRIC_WEIGHTS.
        Handles special cases like size_score (dictionary of device scores) by
        averaging the device scores first.

        Args:
            metrics: List of Metric objects with computed values to include
                in the weighted score calculation

        Note:
            Sets self.value to the computed net score (0.0-1.0) and
            self.latency_ms to the computation time in milliseconds
        """
        logger.info("Computing NetScore...")
        start = time.perf_counter()
        try:
            self.value = 0.0
            total_weight = 0.0  # Track total weight of included metrics

            for metric in metrics:
                if metric.name == "size_score":
                    # Handle size_score which should be a dict of device scores
                    if isinstance(metric.value, dict) and len(metric.value) > 0:
                        avg_size = statistics.mean(metric.value.values())
                        weight = METRIC_WEIGHTS.get("size", 0.0)
                        contribution = weight * avg_size
                        self.value += contribution
                        total_weight += weight
                        logger.debug(
                            f"Including size_score: avg={avg_size:.3f}, "
                            f"weight={weight}, contribution={contribution:.3f}"
                        )
                    else:
                        # If size_score is 0 or invalid, skip it (don't penalize)
                        logger.warning(
                            f"size_score is not a valid dict: {metric.value}, skipping"
                        )
                elif isinstance(metric.value, (int, float)):
                    # Handle both int and float values
                    metric_value = float(metric.value)
                    weight = METRIC_WEIGHTS.get(metric.name, 0.0)

                    # For optional metrics (dataset_quality, code_quality), don't penalize if 0.0
                    # This means if they're missing, we just don't include them in the score
                    is_optional = metric.name in ["dataset_quality", "code_quality"]
                    if is_optional and metric_value == 0.0:
                        logger.debug(
                            f"Skipping optional metric {metric.name} with value 0.0 (not penalizing)"
                        )
                        continue

                    contribution = weight * metric_value
                    self.value += contribution
                    total_weight += weight
                    logger.debug(
                        f"Including {metric.name}: value={metric_value:.3f}, "
                        f"weight={weight}, contribution={contribution:.3f}"
                    )

            # Normalize by total weight to ensure score is in [0, 1] range
            # This prevents penalizing models that don't have optional features
            if total_weight > 0:
                # Scale to account for missing optional metrics
                # This gives fair scores even when optional metrics are missing
                max_possible_weight = sum(METRIC_WEIGHTS.values())
                if total_weight < max_possible_weight:
                    # Some optional metrics are missing, scale up to compensate
                    scale_factor = max_possible_weight / total_weight
                    self.value = min(1.0, self.value * scale_factor)
                    logger.debug(
                        f"Normalized net_score: total_weight={total_weight:.3f}, "
                        f"max_weight={max_possible_weight:.3f}, scale={scale_factor:.3f}, "
                        f"final_score={self.value:.3f}"
                    )

            self.value = self.value**0.5
            self.latency_ms = int(round((time.perf_counter() - start) * 1000))
            logger.debug(
                f"Final NetScore={self.value:.3f}, latency={self.latency_ms}ms"
            )
        except Exception as e:
            logger.error(f"Error computing NetScore: {e}")
            self.value = 0.0
            self.latency_ms = int(round((time.perf_counter() - start) * 1000))


if __name__ == "__main__":
    scorer = NetScore()
    urls: Dict[str, Optional[str]] = {
        "model": "https://huggingface.co/google-bert/bert-base-uncased",
        "code": "https://huggingface.co/google-bert/bert-base-uncased",
    }
