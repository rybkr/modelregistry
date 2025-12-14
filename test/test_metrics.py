"""Tests for metrics validation and golden file compliance.

This module validates that the Metrics Pydantic model correctly validates
test data from the golden file, ensuring schema compliance and data integrity.
"""

import json
import pathlib

import pytest

from models import Metrics

GOLDEN_FILE = pathlib.Path(__file__).parent / "fixtures" / "golden" / "metrics.ndjson"


def test_golden_file_validates() -> None:
    """Function that validates models against golden test case."""
    with GOLDEN_FILE.open() as f:
        for i, line in enumerate(f, start=1):
            data = json.loads(line)
            try:
                Metrics(**data)  # validate with Pydantic
            except Exception as e:
                pytest.fail(f"Line {i} failed validation: {e}")
