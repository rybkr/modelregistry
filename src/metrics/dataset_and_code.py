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


class DatasetAndCode(Metric):
    """Score dataset documentation and example code clarity in READMEs."""

    def __init__(self) -> None:
        """Initialize metric with name."""
        super().__init__(name="dataset_and_code_score")

    @staticmethod
    def _build_prompt(text: str) -> str:
        """Build dataset/code documentation scoring prompt."""
        return (
            "You are a strict rater. Output ONLY JSON.\n\n"
            "Task:\n"
            "- Assess README for dataset documentation and example code.\n"
            "- Look for named datasets, links, preprocessing details, splits, "
            "and runnable examples (scripts/notebooks/commands).\n\n"
            "Buckets (pick one):\n"
            "- 0.00 → No dataset info and no example code.\n"
            "- 0.50 → Mentions dataset or shows minimal example, sparse details.\n"
            "- 0.75 → Both present but incomplete; some specifics missing.\n"
            "- 1.00 → Well documented dataset and clear runnable examples.\n\n"
            "Output:\n"
            '{"score": 0.00 | 0.50 | 0.75 | 1.00, '
            '"justification": "<short explanation>"}\n\n'
            "README text:\n"
            f"{text}"
        )

    def compute(self, model: Model) -> None:
        """Populate value/latency/details from model+code READMEs."""
        logger.info("Computing DatasetAndCode metric...")
        t0 = time.perf_counter()
        try:
            details: Dict[str, Any] = {}
            scores: list[float] = []

            # Model README
            model_text: Optional[str] = None
            if model.model is not None:
                model_text = try_readme(model.model)

            if model_text:
                r_model = _query_genai(self._build_prompt(model_text))
                scores.append(r_model.get("score", 0.0))
                details["model"] = r_model
            else:
                scores.append(0.0)
                details["model"] = {
                    "score": 0.0,
                    "justification": "README not found",
                }

            # Code README
            code_text: Optional[str] = None
            if model.code is not None:
                code_text = try_readme(model.code)

            if code_text:
                r_code = _query_genai(self._build_prompt(code_text))
                scores.append(r_code.get("score", 0.0))
                details["code"] = r_code
            else:
                scores.append(0.0)
                details["code"] = {
                    "score": 0.0,
                    "justification": "README not found",
                }

            if all(s == 0.0 for s in scores):
                self.value = 0.0
            elif all(s >= 0.9 for s in scores):
                self.value = 1.0
            else:
                self.value = sum(scores) / len(scores)

            self.latency_ms = int((time.perf_counter() - t0) * 1000)
            self.details = details

            logger.debug(
                f"DatasetAndCode results: model_score={details.get('model')}, "
                f"code_score={details.get('code')}, final={self.value}"
            )
        except Exception as e:
            logger.error(f"Error computing DatasetAndCode metric: {e}")
            self.value = 0.0
            self.latency_ms = int((time.perf_counter() - t0) * 1000)
            self.details = {"error": str(e)}
