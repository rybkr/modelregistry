import json
import sys
from pathlib import Path
from typing import Any

from model_audit_cli.metrics_engine import compute_all_metrics, flatten_to_ndjson
from model_audit_cli.models import Model
from model_audit_cli.resources.model_resource import ModelResource


def main(path: str) -> None:
    """Dummy CLI that runs metrics on each URL in a file and prints NDJSON output."""
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
