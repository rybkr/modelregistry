"""Model evaluator for batch processing of model URLs.

This module provides a command-line interface for evaluating multiple models
from a file containing URLs. It processes each URL, computes quality metrics,
and outputs results in NDJSON (newline-delimited JSON) format for easy
streaming and processing.
"""

import json
import sys
from pathlib import Path
from typing import Any

from metrics_engine import compute_all_metrics, flatten_to_ndjson
from models import Model
from resources.model_resource import ModelResource


def main(path: str) -> None:
    """Evaluate models from a file of URLs and output results as NDJSON.

    Reads a file containing model URLs (one per line), evaluates each model
    using the metrics engine, and outputs the results as newline-delimited
    JSON (NDJSON) to stdout. Each line of output represents one model's
    evaluation results.

    Args:
        path: Path to file containing model URLs, one per line.
            Lines starting with '#' or empty lines are skipped.

    Output:
        Prints NDJSON to stdout, where each line is a JSON object containing:
        - name: The model URL
        - category: "MODEL"
        - All metric results from compute_all_metrics()
    """
    urls = Path(path).read_text().splitlines()
    for url in urls:
        if not url.strip() or url.startswith("#"):
            continue

        record: dict[str, Any] = {"name": url, "category": "MODEL"}

        model = Model(model=ModelResource(url=url))
        results = compute_all_metrics(model)
        record.update(flatten_to_ndjson(results))

        print(json.dumps(record))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m src.evaluator <url_file>", file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1])
