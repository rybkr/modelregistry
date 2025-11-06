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


class Performance(Metric):
    """Rate performance claims found in model and code READMEs."""

    def __init__(self) -> None:
        """Initialize metric with name."""
        super().__init__(name="performance_claims")

    @classmethod
    def _extract_readmes(cls, model: Model) -> Dict[str, Optional[str]]:
        """Return README text for 'model' and 'code' when available."""
        readmes: Dict[str, Optional[str]] = {"model": None, "code": None}
        if model.model is not None:
            readmes["model"] = try_readme(model.model)
        if model.code is not None:
            readmes["code"] = try_readme(model.code)
        return readmes

    @staticmethod
    def _build_prompt(text: str) -> str:
        """Build a concise, bucketed-scoring prompt for consistency."""
        return (
            "You are a strict evaluator. Read the README and output ONLY JSON.\n\n"
            "Definition:\n"
            "- Performance claims = any evidence of evaluation, benchmarks, or "
            "metrics.\n"
            "- Includes numbers/tables, dataset mentions, metric keywords, or "
            "links to papers/results.\n\n"
            "Scoring buckets (pick one):\n"
            "- 0.00 → No claims (no metrics/benchmarks/numbers).\n"
            '- 0.50 → Vague language (e.g., "good results").\n'
            "- 0.75 → Mentions dataset/benchmark/metric (e.g., GLUE, F1) "
            "without clear numbers/links.\n"
            "- 1.00 → Concrete evidence: numerical results, result tables, "
            "explicit comparisons, or links.\n\n"
            "Output format:\n"
            '{"score": 0.00 | 0.50 | 0.75 | 1.00, '
            '"justification": "<short explanation>"}\n\n'
            "Examples:\n"
            '- "92% accuracy on CIFAR-10" → {"score": 1.00, '
            '"justification": "Concrete number"}\n'
            '- "GLUE test results table ..." → {"score": 1.00, '
            '"justification": "Numerical table"}\n'
            '- "Evaluated on GLUE, strong results" → {"score": 0.75, '
            '"justification": "Benchmark, no numbers"}\n'
            '- "Good performance" → {"score": 0.50, '
            '"justification": "Vague claim"}\n'
            '- No eval → {"score": 0.00, "justification": "No claims"}\n\n'
            "README text:\n"
            f"{text}"
        )

    def compute(self, model: Model) -> None:
        """Populate value/latency/details on this instance."""
        logger.info("Computing Performance metric...")
        t0 = time.perf_counter()
        try:
            readmes = self._extract_readmes(model)

            details: Dict[str, Any] = {}
            scores: list[float] = []

            for key, text in readmes.items():
                if text:
                    # Check for performance keywords first (for consistency and determinism)
                    text_lower = text.lower()
                    perf_keywords = [
                        "accuracy", "performance", "benchmark", "evaluation", "results", 
                        "score", "f1", "bleu", "rouge", "glue", "sota", "state-of-the-art",
                        "outperforms", "achieves", "comparable", "better than", "beats",
                        "math", "code", "reasoning", "tasks", "metrics"
                    ]
                    has_perf_keywords = any(keyword in text_lower for keyword in perf_keywords)
                    
                    # If keywords found, use minimum score for consistency
                    min_score = 0.5 if has_perf_keywords else 0.0
                    
                    try:
                        result = _query_genai(self._build_prompt(text))
                        api_score = result.get("score", 0.0)
                        
                        # Use the maximum of API score and minimum score from keywords
                        # This ensures consistency: if keywords found, always get at least 0.5
                        final_score = max(api_score, min_score)
                        
                        if final_score > api_score:
                            result["score"] = final_score
                            result["justification"] = result.get("justification", "") + f" (Adjusted: performance keywords found, minimum {min_score})"
                            logger.info(f"Performance score for {key} adjusted from {api_score} to {final_score} based on keywords")
                        
                        scores.append(final_score)
                        details[key] = result
                    except Exception as api_error:
                        # If API fails, use keyword-based score
                        if has_perf_keywords:
                            scores.append(min_score)
                            details[key] = {
                                "score": min_score,
                                "justification": f"Performance mentioned in README but API evaluation failed: {str(api_error)}"
                            }
                            logger.warning(f"Performance API failed for {key} but performance mentioned, using keyword-based score {min_score}")
                        else:
                            scores.append(0.0)
                            details[key] = {
                                "score": 0.0,
                                "justification": f"API evaluation failed and no performance claims found: {str(api_error)}"
                            }
                else:
                    scores.append(0.0)
                    details[key] = {
                        "score": 0.0,
                        "justification": "README not found",
                    }
                    logger.warning(f"No README found for {key} in Performance metric")

            if all(s == 0.0 for s in scores):
                self.value = 0.0
            elif all(s >= 0.9 for s in scores):
                self.value = 1.0
            else:
                self.value = sum(scores) / len(scores)

            self.latency_ms = int(round((time.perf_counter() - t0) * 1000))
            self.details = details

            logger.debug(
                f"Performance details: model={details.get('model')}, "
                f"code={details.get('code')}, final={self.value}"
            )
        except Exception as e:
            logger.error(f"Error computing Performance metric: {e}")
            self.value = 0.0
            self.latency_ms = int(round((time.perf_counter() - t0) * 1000))
            self.details = {"error": str(e)}
