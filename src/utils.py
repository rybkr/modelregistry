"""Utility functions for the Model Registry.

This module provides helper functions for data manipulation and formatting,
including JSON reordering utilities for maintaining consistent output formats.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def reorder_top_level_like_json(
    data: Mapping[str, Any],
    json_path: str | Path,
    *,
    drop_extras: bool = False,
) -> dict[str, Any]:
    """Reorder `data` keys to match the top-level key order in `json_path`.

    This function ensures consistent JSON output format by reordering dictionary
    keys to match a template JSON file. Keys present in the template are ordered
    according to the template, while extra keys are appended in their original order.

    Args:
        data: Dictionary to reorder
        json_path: Path to template JSON file
        drop_extras: If True, keys not in template are dropped; if False, they are
            appended at the end

    Returns:
        dict: Reordered dictionary with keys matching template order

    Raises:
        ValueError: If template JSON is not an object at the top level
    """
    template = json.loads(Path(json_path).read_text(encoding="utf-8"))
    if not isinstance(template, dict):
        raise ValueError("Template JSON must be an object at the top level.")

    ordered: dict[str, Any] = {}

    # 1) keys that exist in the template, in template order
    for k in template.keys():
        if k in data:
            ordered[k] = data[k]

    # 2) any extra keys from `data` (not in template)
    if not drop_extras:
        for k in data.keys():
            if k not in template:
                ordered[k] = data[k]

    return ordered
