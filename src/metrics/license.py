from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional, cast

import requests
from dotenv import load_dotenv

from log import logger
from metrics.base_metric import Metric
from models import Model
from resources.base_resource import _BaseResource


def try_readme(resource: _BaseResource, filename: str = "README.md") -> Optional[str]:
    """Attempt to fetch README.md via the resource's RepoView."""
    try:
        with resource.open_files(allow_patterns=[filename]) as repo:
            if repo.exists(filename):
                text = repo.read_text(filename)
                return cast(Optional[str], text)
    except Exception:
        return None
    return None


# Purdue GenAI setup
load_dotenv("config.env")
_API_KEY: Optional[str] = os.getenv("PURDUE_GENAI_API_KEY")
_BASE_URL = "https://genai.rcac.purdue.edu/api"


def _query_genai(prompt: str, model: str = "llama3.1:latest") -> Dict[str, Any]:
    """Call Purdue GenAI and return {'score': float, 'justification': str}."""
    if not _API_KEY:
        raise ValueError("Missing PURDUE_GENAI_API_KEY in config.env")

    url = f"{_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {"model": model, "messages": [{"role": "user", "content": prompt}]}

    resp = requests.post(url, headers=headers, json=body, timeout=30)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"].strip()

    try:
        parsed = json.loads(content)
        return {
            "score": float(parsed.get("score", 0.0)),
            "justification": str(parsed.get("justification", "No rationale provided")),
        }
    except Exception:
        try:
            return {"score": float(content), "justification": "Raw float only"}
        except ValueError:
            return {"score": 0.0, "justification": f"Unparsable output: {content}"}


class License(Metric):
    """Check model README for license clarity and LGPLv2.1 compatibility."""

    def __init__(self) -> None:
        """Initialize metric with name."""
        super().__init__(name="license")

    @staticmethod
    def _build_prompt(text: str) -> str:
        """Build license scoring prompt (bucketed for consistency)."""
        return (
            "You are a strict license rater. Output ONLY JSON.\n\n"
            "Task:\n"
            "- Read README and identify the license.\n"
            "- Evaluate clarity and compatibility with LGPLv2.1.\n\n"
            "Buckets (pick one):\n"
            "- 0.00 → No license info.\n"
            "- 0.50 → License mentioned but unclear placement or ambiguous.\n"
            "- 0.75 → Clear OSI license but compatibility uncertain.\n"
            "- 1.00 → Clear, explicit, and compatible (e.g., Apache-2.0).\n\n"
            "Output:\n"
            '{"score": 0.00 | 0.50 | 0.75 | 1.00, '
            '"justification": "<short explanation>"}\n\n'
            "README text:\n"
            f"{text}"
        )

    def compute(self, model: Model) -> None:
        """Populate value/latency/details using only the model README."""
        logger.info("Computing License metric...")
        t0 = time.perf_counter()
        try:
            readme: Optional[str] = None
            if model.model is not None:
                readme = try_readme(model.model)

            if readme:
                result = _query_genai(self._build_prompt(readme))
                self.value = float(result.get("score", 0.0))
                self.details = {"model": result}
            else:
                self.value = 0.0
                self.details = {
                    "model": {"score": 0.0, "justification": "README not found"}
                }
                logger.warning("No README found for License metric")

            self.latency_ms = int((time.perf_counter() - t0) * 1000)
            logger.debug(f"License details: {self.details}, final={self.value}")
        except Exception as e:
            logger.error(f"Error computing License metric: {e}")
            self.value = 0.0
            self.latency_ms = int((time.perf_counter() - t0) * 1000)
            self.details = {"error": str(e)}
