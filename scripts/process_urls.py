#!/usr/bin/env python3

import json
import sys
import time
from pathlib import Path

from model_audit_cli.metrics.net_score import NetScore
from model_audit_cli.metrics_engine import compute_all_metrics, flatten_to_ndjson
from model_audit_cli.url_handler import URLHandler
from model_audit_cli.utils import reorder_top_level_like_json


def main():
    if len(sys.argv) != 2:
        print("Usage: process_urls.py <url_file>", file=sys.stderr)
        sys.exit(2)

    url_file = sys.argv[1]
    p = Path(url_file)

    if not p.exists():
        print(f"File not found: {url_file}", file=sys.stderr)
        sys.exit(2)

    url_handler = URLHandler()
    models = url_handler.get_models(url_file)

    for i, model in enumerate(models):
        if i > 0 and not model.dataset:
            model.dataset = url_handler.check_for_shared_dataset(model, models[i - 1])

        t0 = time.time()
        results = compute_all_metrics(model)
        t1 = time.time()

        net_score = NetScore()
        net_score.evaluate(list(results.values()))
        net_score.latency_ms = int(round(t1 - t0) * 1000)
        results[net_score.name] = net_score

        ndjson = flatten_to_ndjson(results)
        ndjson["name"] = model.model._repo_id.split("/")[1]
        ndjson["category"] = "MODEL"
        ndjson = reorder_top_level_like_json(ndjson, "test/fixtures/golden/metrics.ndjson")

        print(json.dumps(ndjson))

    return 0


if __name__ == "__main__":
    sys.exit(main())
