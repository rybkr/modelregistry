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

    # Index by id
    pkg_index = {p.id: p for p in all_packages}

    # Map HuggingFace IDs → local package IDs
    hf_index = {
        extract_hf_id(p.metadata.get("url", "")): p.id
        for p in all_packages
        if extract_hf_id(p.metadata.get("url", ""))
    }

    # --- First pass: discover parent relationships (upward edges only) ---
    parent_map = {}  # child_id -> parent_id
    children_map = {}  # parent_id -> list of child_ids

    for pkg in all_packages:
        cfg = load_config_fn(pkg)
        if not cfg:
            continue

        base_path = cfg.get("_name_or_path")
        base_model = cfg.get("base_model")
        parent_uuid = None

        # Case 1: _name_or_path is an HF repo ID
        if base_path:
            parent_uuid = hf_index.get(base_path) or hf_index.get(
                extract_hf_id(base_path)
            )

        # Case 2: "base_model": "something-containing-name"
        elif base_model:
            for candidate in all_packages:
                if candidate.name in base_model:
                    parent_uuid = candidate.id
                    break

        if parent_uuid:
            parent_map[pkg.id] = parent_uuid
            children_map.setdefault(parent_uuid, []).append(pkg.id)

    # --- Unified traversal: Walk upward *and* downward ---
    def walk(model_id: str):
        if model_id in visited:
            return
        visited.add(model_id)

        pkg = pkg_index.get(model_id)
        if not pkg:
            return

        # Add node
        nodes[model_id] = {
            "artifact_id": pkg.id,
            "name": pkg.name,
            "source": "registry",
        }

        # Walk upward to parents
        parent_id = parent_map.get(model_id)
        if parent_id:
            edges.add((parent_id, model_id, "base_model"))
            walk(parent_id)

        # Walk downward to children
        for child_id in children_map.get(model_id, []):
            edges.add((model_id, child_id, "base_model"))
            walk(child_id)

    # Start from any model — now yields entire family graph
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
