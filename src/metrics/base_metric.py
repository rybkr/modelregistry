"""Base metric class for quality evaluation metrics.

This module defines the abstract base class for all quality metrics in the
Model Registry. It provides a standard interface for metric computation with
support for both single numerical scores and multi-component scores (dictionaries).
All metrics track their computed value, computation latency, and additional details.
"""

from typing import Any, Dict, Union

from models import Model


class Metric:
    """Provides a standard interface for calculating various metrics.

    Each metric tracks its computed value, computation latency, and additional details.
    Subclasses must implement the compute() method to define their specific
    metric calculation logic. The class supports both single numerical scores
    and multi-component scores (dictionary of scores).

    Attributes:
        name (str): The identifier for this metric (e.g., "license", "bus_factor")
        value (Union[float, Dict[str, float]]): The computed metric score.
            Can be a single float (0.0-1.0 typically) or a dictionary of
            sub-scores for complex metrics
        latency_ms (int): The time taken to compute this metric in milliseconds
        details (Dict[str, Any]): Additional contextual information about the
            metric computation, such as intermediate values, data sources, or
            explanations
    """

    name: str
    value: Union[float, Dict[str, float]]
    latency_ms: int
    details: Dict[str, Any]

    def __init__(self, name: str) -> None:
        self.name = name
        self.value = 0
        self.latency_ms = 0
        self.details = {}

    def compute(self, model: Model) -> None:
        """Compute the metric for the given model.

        Subclasses must override this method to implement their specific
        metric calculation logic. The method should set self.value, self.latency_ms,
        and self.details with the computation results.

        Args:
            model: The Model instance to evaluate

        Raises:
            NotImplementedError: Must be implemented by subclasses
        """
        raise NotImplementedError
