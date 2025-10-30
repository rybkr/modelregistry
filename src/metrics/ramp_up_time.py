import time
from typing import Dict

from log import logger
from models import Model

from .base_metric import Metric

MODEL_EXTENSIONS: list[str] = ["*.bin", "*.h5", "*.pt", "*.onnx", "*.tflite"]


class RampUpTime(Metric):
    """Calculate the ramp-up time score for a model."""

    def __init__(self) -> None:
        """Initialize the RampUpTime metric."""
        super().__init__(name="ramp_up_time")

    def _open_readme(self, model: Model) -> str:
        """Return the README contents if it exists, otherwise an empty string."""
        readme: str = ""
        with model.model.open_files() as files:
            if files.exists("README.md"):
                readme = files.read_text("README.md")
        return readme

    def _count_models(self, model: Model) -> int:
        """Return the number of model files found in the repo."""
        num_models: int = 0
        with model.model.open_files() as files:
            for ext in MODEL_EXTENSIONS:
                found_model_files = list(files.glob(ext))
                num_models += len(found_model_files)
        return num_models

    def calculate_score(self, readme: str, num_models: int) -> Dict[str, float]:
        """Calculate subscores for README and model files."""
        readme_score: float = min(len(readme) / 5000.0, 1.0)
        models_score: float = min(num_models / 10.0, 1.0)
        return {"readme_score": readme_score, "models_score": models_score}

    def compute(self, model: Model) -> None:
        """Compute the ramp-up time score."""
        logger.info("Computing RampUpTime metric...")
        t0: float = time.perf_counter()
        try:
            readme: str = self._open_readme(model)
            num_models: int = self._count_models(model)
            scores: Dict[str, float] = self.calculate_score(readme, num_models)

            # weighted score
            self.value = float(
                0.6 * scores["readme_score"] + 0.4 * scores["models_score"]
            )
            self.latency_ms = int(round((time.perf_counter() - t0) * 1000.0))
            self.details = {
                "readme_length": len(readme),
                "num_models": num_models,
                **scores,
            }

            logger.debug(
                f"RampUpTime details: readme_len={len(readme)}, "
                f"num_models={num_models}, scores={scores}, final={self.value}"
            )
        except Exception as e:
            logger.error(f"Error computing RampUpTime metric: {e}")
            self.value = 0.0
            self.latency_ms = int(round((time.perf_counter() - t0) * 1000.0))
            self.details = {"error": str(e)}


def ramp_up_time(model: Model) -> None:
    """Compatibility wrapper so tests calling ramp_up_time still work."""
    RampUpTime().compute(model)
