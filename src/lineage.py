"""Lineage tracking for model dependencies and relationships.

This module provides functionality to build dependency graphs between models
based on their configuration files (e.g., base_model references) and compute
scores based on parent model quality. It supports HuggingFace model lineage
tracking through config.json analysis.
"""

from urllib.parse import urlparse
from registry_models import Package
from typing import Optional, List


def extract_hf_id(url: str) -> Optional[str]:
    """Extract HuggingFace repository ID from a URL.

    Parses a HuggingFace URL and extracts the organization/repository identifier.
    Handles URLs for models, datasets, and spaces.

    Args:
        url: HuggingFace URL (e.g., "https://huggingface.co/org/model-name")

    Returns:
        Optional[str]: Repository ID in format "org/repo" or None if URL is invalid
    """
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
) -> dict:
    """Build a lineage graph showing model dependencies.

    Traverses model dependencies starting from a root package, following
    base_model and _name_or_path references in configuration files to build
    a graph of parent-child relationships.

    Args:
        root_id: ID of the root package to start traversal from
        all_packages: List of all packages in the registry
        load_config_fn: Function to load config.json from a package
            (signature: Package -> Optional[dict])

    Returns:
        dict: Graph structure with "nodes" and "edges" keys:
            - nodes: List of node dictionaries with artifact_id, name, source
            - edges: List of edge dictionaries with from_node_artifact_id,
              to_node_artifact_id, and relationship type
    """
    nodes = {}
    edges = set()
    visited = set()

    # Quick lookup by artifact ID
    pkg_index = {p.id: p for p in all_packages}

    # HF repo ID → artifact ID mapping
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

        # Add node for this package
        nodes[model_id] = {
            "artifact_id": pkg.id,
            "name": pkg.name,
            "source": "registry",
        }

        # Load config for parent inspection
        cfg = load_config_fn(pkg)
        if not cfg:
            return

        base_path: str = cfg.get("_name_or_path")
        base_model: str = cfg.get("base_model")

        parent_uuid = None

        # Case 1: _name_or_path resembles HF repo
        if base_path:
            parent_uuid = hf_index.get(base_path) or hf_index.get(
                extract_hf_id(base_path)
            )

        # Case 2: fuzzy match via 'base_model'
        elif base_model:
            for package in all_packages:
                if package.name in base_model:
                    parent_uuid = package.id
                    break

        # If we found a parent, add edge and walk upward
        if parent_uuid:
            edges.add((parent_uuid, model_id, "base_model"))
            walk(parent_uuid)

    # Only walk ancestors starting from root
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


def compute_tree_score(root_id: str, lineage_graph: dict, score_lookup_fn) -> float:
    """Compute a tree score based on parent model quality.

    Calculates the average score of all parent models in the lineage graph
    for a given root package. This provides a measure of inherited quality
    from base models.

    Args:
        root_id: ID of the root package to compute score for
        lineage_graph: Lineage graph structure from build_lineage_graph()
        score_lookup_fn: Function to get score for a package ID
            (signature: str -> Optional[float])

    Returns:
        float: Average score of parent models, or 0.0 if no parents found
    """
    parent_scores = []
    for edge in lineage_graph["edges"]:
        if edge["to_node_artifact_id"] == root_id:
            parent_score = score_lookup_fn(edge["from_node_artifact_id"])
            if parent_score is not None:
                parent_scores.append(parent_score)

    if not parent_scores:
        return 0.0

    return round(sum(parent_scores) / len(parent_scores), 4)
