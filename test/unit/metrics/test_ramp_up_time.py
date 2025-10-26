from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable
from unittest.mock import MagicMock, patch

import pytest

from model_audit_cli.metrics.ramp_up_time import MODEL_EXTENSIONS, RampUpTime

# --- helpers -----------------------------------------------------------------


def make_repo(
    *,
    readme_exists: bool,
    readme_text: str = "",
    models_by_ext: Dict[str, Iterable[Path]] | None = None,
) -> MagicMock:
    """Create a mock repository with specified README and model files.

    Args:
        readme_exists (bool): Whether the README file exists.
        readme_text (str, optional): Content of the README file. Defaults to "".
        models_by_ext (Dict[str, Iterable[Path]] | None, optional): Dictionary
            mapping file extensions to lists of model file paths. Defaults to None.

    Returns:
        MagicMock: Mock repository object.
    """
    repo = MagicMock()

    # README existence + content
    repo.exists.side_effect = lambda p: (p == "README.md" and readme_exists)
    repo.read_text.return_value = readme_text

    # Glob results for model extensions
    models_by_ext = models_by_ext or {}

    def _glob(pattern: str) -> list[Path]:
        return list(models_by_ext.get(pattern, []))

    repo.glob.side_effect = _glob

    return repo


def make_model_with_repo(repo: MagicMock) -> MagicMock:
    """Create a mock model with an associated repository.

    Args:
        repo (MagicMock): Mock repository object.

    Returns:
        MagicMock: Mock model object.
    """
    cm = MagicMock()
    cm.__enter__.return_value = repo
    cm.__exit__.return_value = None

    model = MagicMock()
    model.model.open_files.return_value = cm
    return model


# --- unit tests for helpers inside RampUpTime --------------------------------


@patch("time.perf_counter", side_effect=[10.0, 10.050])  # 50ms
def test_compute_happy_path(mock_perf: MagicMock) -> None:
    """Test compute with a typical scenario.

    This test verifies that the `compute` method calculates the final score
    and details correctly using a typical scenario with a README and model files.

    Args:
        mock_perf (MagicMock): Mocked `perf_counter` method.
    """
    repo = make_repo(
        readme_exists=True,
        readme_text="x" * 3000,
        models_by_ext={
            "*.bin": [Path("a.bin"), Path("b.bin")],  # 2 files
            # other extensions empty by default
        },
    )
    mdl = make_model_with_repo(repo)

    metric = RampUpTime()
    metric.compute(mdl)

    assert pytest.approx(metric.value, rel=1e-9) == 0.44
    assert metric.latency_ms == 50  # from patched perf_counter
    assert metric.details["readme_length"] == 3000
    assert metric.details["num_models"] == 2
    assert pytest.approx(metric.details["readme_score"]) == 0.6
    assert pytest.approx(metric.details["models_score"]) == 0.2


@patch("time.perf_counter", side_effect=[1.0, 1.0])  # zero duration
def test_compute_caps_at_one(mock_perf: MagicMock) -> None:
    """Test compute with very long README and many models.

    This test verifies that the `compute` method caps the scores and value at 1.0
    when the README is very long and there are many models.

    Args:
        mock_perf (MagicMock): Mocked `perf_counter` method.
    """
    repo = make_repo(
        readme_exists=True,
        readme_text="x" * 10_000,  # longer than 5000
        models_by_ext={
            ext: [Path(f"f{i}{ext.replace('*', '')}") for i in range(5)]
            for ext in MODEL_EXTENSIONS
        },
        # total models >= 10 (because multiple extensions) → models_score=1.0
    )
    mdl = make_model_with_repo(repo)

    metric = RampUpTime()
    metric.compute(mdl)

    assert metric.value == 1.0
    assert metric.details["readme_length"] == 10_000
    assert metric.details["num_models"] >= 10
    assert metric.details["readme_score"] == 1.0
    assert metric.details["models_score"] == 1.0


@patch("time.perf_counter", side_effect=[5.0, 5.002])  # 2ms
def test_compute_no_readme_no_models_yields_zero(mock_perf: MagicMock) -> None:
    """Test compute with no README and no models.

    This test verifies that the `compute` method returns a score of 0.0 when
    there is no README and no models.

    Args:
        mock_perf (MagicMock): Mocked `perf_counter` method.
    """
    repo = make_repo(
        readme_exists=False,
        readme_text="",  # ignored because exists=False
        models_by_ext={},  # no matches
    )
    mdl = make_model_with_repo(repo)

    metric = RampUpTime()
    metric.compute(mdl)

    assert metric.value == 0.0
    assert metric.details["readme_length"] == 0
    assert metric.details["num_models"] == 0
    assert metric.details["readme_score"] == 0.0
    assert metric.details["models_score"] == 0.0
    assert metric.latency_ms == 2


def test_calculate_score_math() -> None:
    """Test calculate_score with various inputs.

    This test verifies that the `calculate_score` method correctly computes
    the `readme_score` and `models_score` based on different inputs.
    """
    m = RampUpTime()
    # readme: 2500 chars -> 0.5, models: 5 -> 0.5
    out = m.calculate_score("x" * 2500, 5)
    assert out == {"readme_score": 0.5, "models_score": 0.5}

    # caps
    out2 = m.calculate_score("x" * 10000, 123)
    assert out2["readme_score"] == 1.0
    assert out2["models_score"] == 1.0


def test_open_readme_returns_text_when_exists() -> None:
    """Test _open_readme with an existing README file.

    This test verifies that the `_open_readme` method correctly reads the
    content of an existing README file.
    """
    repo = make_repo(readme_exists=True, readme_text="# hello\n")
    mdl = make_model_with_repo(repo)

    m = RampUpTime()
    txt = m._open_readme(mdl)
    assert txt == "# hello\n"


def test_open_readme_returns_empty_when_missing() -> None:
    """Test _open_readme with a missing README file.

    This test verifies that the `_open_readme` method returns an empty string
    when the README file does not exist.
    """
    repo = make_repo(readme_exists=False)
    mdl = make_model_with_repo(repo)

    m = RampUpTime()
    txt = m._open_readme(mdl)
    assert txt == ""


def test_count_models_sums_across_extensions() -> None:
    """Test _count_models with multiple model extensions.

    This test verifies that the `_count_models` method correctly counts the
    number of model files across multiple extensions.
    """
    repo = make_repo(
        readme_exists=False,
        models_by_ext={
            "*.bin": [Path("a.bin")],
            "*.onnx": [Path("b.onnx"), Path("c.onnx")],
            "*.pt": [],
            "*.h5": [Path("d.h5")],
            "*.tflite": [Path("e.tflite"), Path("f.tflite"), Path("g.tflite")],
        },
    )
    mdl = make_model_with_repo(repo)

    m = RampUpTime()
    total = m._count_models(mdl)

    # 1 + 2 + 0 + 1 + 3 = 7
    assert total == 7
