from urllib.parse import urlparse
from registry_models import Package
from typing import Optional, List


def extract_hf_id(url: str) -> Optional[str]:
    if not url or "huggingface.co" not in url.lower():
        return None
    parsed = urlparse(url)
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if parts and parts[0] in {"datasets", "spaces"}:
        parts = parts[1:]
    return f"{parts[0]}/{parts[1]}" if len(parts) >= 2 else None


def build_lineage_graph(
    root_id: str,
    all_packages: list[Package],
    load_config_fn,
):
    nodes = {}
    edges = set()
    visited = set()

    pkg_index = {p.id: p for p in all_packages}
    hf_index = {
        extract_hf_id(p.metadata.get("url", "")): p.id
        for p in all_packages
        if extract_hf_id(p.metadata.get("url", ""))
    }

    def walk(model_id: str):
        if model_id in visited:
            return
        visited.add(model_id)

        pkg = pkg_index.get(model_id)
        if not pkg:
            return

        nodes[model_id] = {
            "artifact_id": pkg.id,
            "name": pkg.name,
            "source": "registry",
        }

        cfg = load_config_fn(pkg)
        if not cfg:
            return

        base_path = cfg.get("_name_or_path") or cfg.get("base_model")
        dataset_name = cfg.get("dataset") or cfg.get("train_dataset")

        if base_path:
            parent_uuid = hf_index.get(base_path) or hf_index.get(
                extract_hf_id(base_path)
            )
            if parent_uuid:
                edges.add((parent_uuid, model_id, "base_model"))
                walk(parent_uuid)

        if dataset_name:
            ds_uuid = hf_index.get(dataset_name) or hf_index.get(
                extract_hf_id(dataset_name)
            )
            if ds_uuid:
                edges.add((ds_uuid, model_id, "fine_tuning_dataset"))

    walk(root_id)

    return {
        "nodes": list(nodes.values()),
        "edges": [
            {
                "from_node_artifact_id": f,
                "to_node_artifact_id": t,
                "relationship": r,
            }
            for f, t, r in edges
        ],
    }


def compute_tree_score(root_id: str, lineage_graph: dict, score_lookup_fn):
    parent_scores = []
    for edge in lineage_graph["edges"]:
        if edge["to_node_artifact_id"] == root_id:
            parent_score = score_lookup_fn(edge["from_node_artifact_id"])
            if parent_score is not None:
                parent_scores.append(parent_score)

    if not parent_scores:
        return 0.0

    return round(sum(parent_scores) / len(parent_scores), 4)
