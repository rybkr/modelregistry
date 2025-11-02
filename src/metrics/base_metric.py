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
        """Subclasses must override this with their calculation."""
        raise NotImplementedError
