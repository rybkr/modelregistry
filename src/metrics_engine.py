"""Metrics computation engine for model evaluation.

This module provides the core functionality for computing all quality metrics
for a model. It orchestrates metric computation, handles errors gracefully,
and provides utilities for flattening metric results into dictionary format
for serialization (e.g., NDJSON output).
"""

import time
from typing import Any, Dict

from metrics.base_metric import Metric
from metrics.registry import ALL_METRICS
from models import Model


def _safe_run(metric: Metric, model: Model) -> Metric:
    """Execute metric computation with error handling.

    Runs the metric's compute() method and catches exceptions, setting
    default values on failure. For size_score metrics, returns a dict
    with zero scores for all deployment targets.

    Args:
        metric: The metric to compute
        model: The model to evaluate

    Returns:
        Metric: The metric with computed or error values
    """
    start = time.perf_counter()
    try:
        metric.compute(model)
        return metric
    except Exception as e:
        metric.value = 0.0
        metric.latency_ms = int((time.perf_counter() - start) * 1000.0)
        metric.details = {"error": str(e)}
        if metric.name == "size_score":
            metric.value = {
                "raspberry_pi": 0.0,
                "jetson_nano": 0.0,
                "desktop_pc": 0.0,
                "aws_server": 0.0,
            }
        return metric


def compute_all_metrics(
    model: Model, include: set[str] | None = None
) -> dict[str, Metric]:
    """Compute metrics for a model sequentially.

    Executes all registered metrics (or a subset if specified) for a given model.
    Metrics are computed sequentially to avoid threading/multiprocessing issues.
    Each metric computation is wrapped in error handling to prevent one failure
    from stopping the entire evaluation.

    Args:
        model: The model to evaluate with all metrics
        include: Optional set of metric names to compute. If None, computes all
            registered metrics from ALL_METRICS

    Returns:
        dict[str, Metric]: Dictionary mapping metric names to computed Metric
            objects. Each metric contains value, latency_ms, and details.
    """
    results: dict[str, Metric] = {}
    metrics = [m for m in ALL_METRICS if include is None or m.name in include]

    # Compute metrics sequentially to avoid threading/multiprocessing issues
    for metric in metrics:
        computed_metric = _safe_run(metric, model)
        results[computed_metric.name] = computed_metric

    return results


def flatten_to_ndjson(results: Dict[str, Metric]) -> Dict[str, Any]:
    """Flatten metric results to a simple dictionary for NDJSON output.

    Converts a dictionary of Metric objects into a flat dictionary suitable
    for serialization to NDJSON (newline-delimited JSON) format. Each metric's
    value and latency are extracted and stored with standardized naming.

    Args:
        results: Dictionary mapping metric names to Metric objects

    Returns:
        Dict[str, Any]: Flattened dictionary with keys like:
            - "{metric_name}": metric value
            - "{metric_name}_latency": computation latency in milliseconds
    """
    out: Dict[str, Any] = {}
    for metric in results.values():
        out[metric.name] = metric.value
        out[f"{metric.name}_latency"] = int(round(metric.latency_ms))
    return out
