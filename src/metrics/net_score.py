from __future__ import annotations

import statistics
import time
from typing import Dict, Optional

from log import logger
from metrics.base_metric import Metric

# Metric weights based on Sarah's priorities
METRIC_WEIGHTS: Dict[str, float] = {
    "license": 0.20,
    "ramp_up_time": 0.15,
    "bus_factor": 0.15,
    "dataset_and_code_score": 0.10,
    "dataset_quality": 0.10,
    "code_quality": 0.10,
    "performance_claims": 0.10,
    "size": 0.10,
}


class NetScore(Metric):
    """Aggregate metric runner for computing weighted net score."""

    def __init__(self) -> None:
        """Initialize available metrics."""
        """Initialize metric with name."""
        super().__init__(name="net_score")

    def evaluate(self, metrics: list[Metric]) -> None:
        """Run all metrics, aggregate results, and compute weighted net score.

        Args:
            metrics: List of Metric objects to include in the weighted score.

        Returns:
            None
        """
        logger.info("Computing NetScore...")
        start = time.perf_counter()
        try:
            self.value = 0.0
            for metric in metrics:
                if metric.name == "size_score":
                    # Handle size_score which should be a dict of device scores
                    if isinstance(metric.value, dict) and len(metric.value) > 0:
                        avg_size = statistics.mean(metric.value.values())
                        self.value += METRIC_WEIGHTS.get("size", 0.0) * avg_size
                        logger.debug(
                            f"Including size_score: avg={avg_size:.3f}, "
                            f"weight={METRIC_WEIGHTS.get('size', 0.0)}"
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
                    contribution = weight * metric_value
                    self.value += contribution
                    logger.debug(
                        f"Including {metric.name}: value={metric_value:.3f}, "
                        f"weight={weight}, contribution={contribution:.3f}"
                    )

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
