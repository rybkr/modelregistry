from typing import Any, Dict, Union

from models import Model


class Metric:
    """Base class for all metrics."""

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
