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

    Extras (keys not in the template) are appended in their original order,
    unless drop_extras=True.
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
