import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict

from models import Model

from metrics.base_metric import Metric
from metrics.registry import ALL_METRICS

FORCE_SEQUENTIAL = os.environ.get("FORCE_SEQUENTIAL") == "1"


def _safe_run(metric: Metric, model: Model) -> Metric:
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
        # raise e
        return metric


def compute_all_metrics(
    model: Model, include: set[str] | None = None
) -> dict[str, Metric]:
    """Compute all metrics for the given model."""
    results: dict[str, Metric] = {}
    metrics = [m for m in ALL_METRICS if include is None or m.name in include]

    if FORCE_SEQUENTIAL:
        for metric in metrics:
            results[metric.name] = _safe_run(metric, model)
    else:
        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(_safe_run, metric, model): metric.name
                for metric in metrics
            }
            for future in as_completed(futures):
                metric = future.result()  # already Metric, no cast needed
                results[metric.name] = metric

    return results


def flatten_to_ndjson(results: Dict[str, Metric]) -> Dict[str, Any]:
    """Convert Metric objects into NDJSON-style flat dict."""
    out: Dict[str, Any] = {}
    for metric in results.values():
        out[metric.name] = metric.value
        out[f"{metric.name}_latency"] = int(round(metric.latency_ms))

    return out
