"""Ramp-Up Time metric for evaluating ease of getting started.

This module implements the RampUpTime metric, which measures how quickly a new
user can start using a model repository. It evaluates documentation quality,
presence of code examples, installation instructions, and available model files
to determine the learning curve and setup complexity.
"""

import time
from typing import Dict

from log import logger
from models import Model

from .base_metric import Metric

MODEL_EXTENSIONS: list[str] = ["*.bin", "*.h5", "*.pt", "*.onnx", "*.tflite"]


class RampUpTime(Metric):
    """Calculate the ramp-up time score for a model.

    Measures how easy it is for a new user to get started by checking for:
    - Clear usage examples with code
    - Installation/setup instructions
    - Available model files to download
    - Dependency documentation

    Lower barriers = higher score = faster ramp-up time.
    """

    def __init__(self) -> None:
        """Initialize the RampUpTime metric."""
        super().__init__(name="ramp_up_time")

    def _open_readme(self, model: Model) -> str:
        """Return the README contents if it exists, otherwise an empty string.

        Args:
            model: Model instance to read README from

        Returns:
            str: README content or empty string if not found/readable
        """
        readme: str = ""
        try:
            with model.model.open_files() as files:
                if files.exists("README.md"):
                    readme = files.read_text("README.md")
        except Exception as e:
            logger.warning(f"Could not read README: {e}")
        return readme

    def _check_for_example_code(self, readme: str) -> bool:
        """Check if README contains actual code examples.

        Looks for code blocks (```) and import statements to determine if
        the README includes executable code examples.

        Args:
            readme: README content to analyze

        Returns:
            bool: True if code blocks and import statements are found
        """
        has_code_blocks = "```" in readme

        readme_lower = readme.lower()
        has_import_statements = any(
            keyword in readme
            for keyword in ["import ", "from ", "require(", "#include"]
        )

        return has_code_blocks and has_import_statements

    def _check_setup_files(self, model: Model) -> Dict[str, bool]:
        """Check for presence of common setup/dependency files."""
        setup_files = {
            "requirements.txt": False,
            "setup.py": False,
            "pyproject.toml": False,
            "environment.yml": False,
            "package.json": False,
        }

        try:
            with model.model.open_files() as files:
                for filename in setup_files.keys():
                    if files.exists(filename):
                        setup_files[filename] = True
        except Exception as e:
            logger.warning(f"Could not check setup files: {e}")

        return setup_files

    def _analyze_readme_content(self, readme: str) -> Dict[str, bool]:
        """Analyze README for key content that helps users get started quickly."""
        if not readme:
            return {
                "has_readme": False,
                "has_installation": False,
                "has_usage_section": False,
                "has_code_example": False,
                "has_quick_start": False,
            }

        readme_lower = readme.lower()

        return {
            "has_readme": True,
            "has_installation": any(
                keyword in readme_lower
                for keyword in [
                    "installation",
                    "install",
                    "setup",
                ]
            ),
            "has_usage_section": any(
                keyword in readme_lower
                for keyword in [
                    "usage",
                    "how to",
                    "example",
                    "quick start",
                    "quickstart",
                ]
            ),
            "has_code_example": self._check_for_example_code(readme),
            "has_quick_start": any(
                keyword in readme_lower
                for keyword in [
                    "quick start",
                    "quickstart",
                ]
            ),
        }

    def _count_models(self, model: Model) -> int:
        """Return the number of model files found in the repo."""
        num_models: int = 0
        try:
            with model.model.open_files() as files:
                for ext in MODEL_EXTENSIONS:
                    found_model_files = list(files.glob(ext))
                    num_models += len(found_model_files)
        except Exception as e:
            logger.warning(f"Could not count models: {e}")
        return num_models

    def calculate_score(
        self,
        num_models: int,
        setup_files: Dict[str, bool],
        readme_content: Dict[str, bool],
    ) -> Dict[str, float]:
        """Calculate subscores based on ramp-up barriers."""
        code_example_score = 0.0
        if readme_content.get("has_code_example"):
            code_example_score = 1.0
        elif readme_content.get("has_usage_section"):
            code_example_score = 0.3

        installation_score = 0.0
        if readme_content.get("has_quick_start"):
            installation_score = 1.0
        elif readme_content.get("has_installation"):
            installation_score = 0.7
        elif readme_content.get("has_readme"):
            installation_score = 0.2

        if num_models == 0:
            models_score = 0.0
        elif num_models == 1:
            models_score = 0.8
        else:
            models_score = 1.0

        setup_count = sum(setup_files.values())
        if setup_count == 0:
            dependencies_score = 0.0
        elif setup_count == 1:
            dependencies_score = 0.8
        else:
            dependencies_score = 1.0

        return {
            "code_example_score": code_example_score,
            "installation_score": installation_score,
            "models_score": models_score,
            "dependencies_score": dependencies_score,
        }

    def compute(self, model: Model) -> None:
        """Compute the ramp-up time score."""
        logger.info("Computing RampUpTime metric...")
        t0: float = time.perf_counter()

        try:
            readme: str = self._open_readme(model)
            num_models: int = self._count_models(model)
            setup_files: Dict[str, bool] = self._check_setup_files(model)
            readme_content: Dict[str, bool] = self._analyze_readme_content(readme)

            scores: Dict[str, float] = self.calculate_score(
                num_models, setup_files, readme_content
            )

            self.value = float(
                0.65 * scores["code_example_score"]
                + 0.55 * scores["installation_score"]
                + 0.50 * scores["models_score"]
                + 0.30 * scores["dependencies_score"]
            )
            # Normalize the value in accordance with variable weights.
            self.value = min(self.value**0.5, 1.0)

            self.latency_ms = int(round((time.perf_counter() - t0) * 1000.0))
            self.details = {
                "readme_exists": readme_content.get("has_readme", False),
                "readme_length": len(readme),
                "num_models": num_models,
                "setup_files_found": [k for k, v in setup_files.items() if v],
                "readme_features": readme_content,
                **scores,
            }

            logger.info(
                f"RampUpTime: score={self.value:.3f}, "
                f"models={num_models}, "
                f"has_code_example={readme_content.get('has_code_example', False)}, "
                f"has_install={readme_content.get('has_installation', False)}"
            )

        except Exception as e:
            logger.error(f"Error computing RampUpTime metric: {e}")
            self.value = 0.0
            self.latency_ms = int(round((time.perf_counter() - t0) * 1000.0))
            self.details = {"error": str(e)}


def ramp_up_time(model: Model) -> None:
    """Compatibility wrapper so tests calling ramp_up_time still work."""
    RampUpTime().compute(model)
