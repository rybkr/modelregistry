import time

from log import logger
from metrics.base_metric import Metric
from models import Model

# Device memory budgets in bytes
DEVICE_BUDGETS = {
    "raspberry_pi": 0.75 * 1e9,  # 750MB
    "jetson_nano": 2.5 * 1e9,  # 2.5GB
    "desktop_pc": 8.0 * 1e9,  # 8GB
    "aws_server": 16.0 * 1e9,  # 16GB
}

# File patterns to match model files
MODEL_PATTERNS = ["*.bin", "*.h5", "*.pt", "*.onnx", "*.tflite"]


class Size(Metric):
    """Metric for evaluating model size against device memory budgets.

    This metric calculates the total size of model files (binaries, weights, etc.)
    and scores them against predefined device memory budgets using a smoothstep
    function. The score indicates how well the model fits on different devices.
    """

    def __init__(self) -> None:
        """Initialize the Size metric.

        Sets up the metric with the name "size" for identification.
        """
        super().__init__(name="size_score")

    def compute(self, model: Model) -> None:
        """Compute the size metric for a given model.

        Args:
            model (Model): The model to evaluate. Must have a model resource
                with accessible files.

        Note:
            The method sets the following attributes on the instance:
            - size_score: SizeScore object with scores for each device
            - latency_ms: Computation time in milliseconds
        """
        logger.info("Computing Size metric...")
        t0 = time.time() * 1000
        try:
            with model.model.open_files() as repo:
                size_bytes = 0
                for pattern in MODEL_PATTERNS:
                    files = list(repo.glob(pattern))
                    for file in files:
                        relative_path = str(file.relative_to(repo.root))
                        size_bytes += repo.size_bytes(relative_path)
            scores = {
                dev: self.smoothstep_score(size_bytes, cap)
                for dev, cap in DEVICE_BUDGETS.items()
            }
            self.value = scores
            t1 = time.time() * 1000
            self.latency_ms = int(round(t1 - t0))
            logger.debug(f"Size bytes={size_bytes}, scores={scores}")
        except Exception as e:
            logger.error(f"Error computing Size metric: {e}")

    def smoothstep_score(
        self, size_bytes: float, cap_bytes: float, a: float = 0.25, b: float = 1.50
    ) -> float:
        """Calculate a smoothstep score for model size against device capacity.

        Uses a smoothstep function to create a smooth transition between
        acceptable and unacceptable model sizes. The score ranges from 0 to 1,
        where 1 indicates the model fits well on the device.

        Args:
            size_bytes (float): Size of the model in bytes.
            cap_bytes (float): Device capacity in bytes.
            a (float): Lower threshold ratio (default: 0.25). When size/cap < a,
                score is 1.0 (perfect fit).
            b (float): Upper threshold ratio (default: 1.50). When size/cap > b,
                score is 0.0 (doesn't fit).

        Returns:
            float: Score between 0.0 and 1.0, where:
                - 1.0: Model fits perfectly (size/cap < a)
                - 0.0: Model doesn't fit (size/cap > b)
                - Smooth transition between a and b ratios

        Note:
            The smoothstep function creates a smooth S-curve transition
            between the thresholds, avoiding sharp cutoffs.
        """
        r = size_bytes / cap_bytes
        t = (r - a) / (b - a)
        # clamp 0..1
        t = 0.0 if t < 0 else 1.0 if t > 1 else t
        s = t * t * (3 - 2 * t)  # smoothstep
        return 1.0 - s


if __name__ == "__main__":
    """Example usage of the Size metric."""
    from models import Model
    from resources.code_resource import CodeResource
    from resources.dataset_resource import DatasetResource
    from resources.model_resource import ModelResource

    # Create a model with resources
    model_res = ModelResource("https://huggingface.co/google-bert/bert-base-uncased")
    code_res = CodeResource("https://github.com/google-research/bert")
    dataset_res = DatasetResource(
        "https://huggingface.co/datasets/bookcorpus/bookcorpus"
    )
    model = Model(model=model_res, code=code_res, dataset=dataset_res)

    # Compute size metric
    size = Size()
    size.compute(model)
    print(size.value, size.latency_ms)
