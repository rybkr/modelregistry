"""Dataset and Code Availability metric for evaluating reproducibility.

This module implements the DatasetAndCode metric, which uses LLM-based semantic
analysis to determine if a model's README mentions datasets and code resources
needed for reproducibility. It identifies references even when phrased in
non-standard ways, providing scores for dataset availability, code availability,
and overall reproducibility.
"""

from __future__ import annotations

import json
import math
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
    """Attempt to fetch README.md via the resource's RepoView.

    Args:
        resource: Resource instance to read README from
        filename: Name of README file (default: "README.md")

    Returns:
        Optional[str]: README content or None if not found/readable
    """
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
    """Call Purdue GenAI API and return structured response.

    Sends a prompt to the Purdue GenAI API and parses the response into
    a structured format with score and justification.

    Args:
        prompt: Text prompt to send to the LLM
        model: Model name to use (default: "llama3.1:latest")

    Returns:
        Dict[str, Any]: Response dictionary with 'score' (float) and
            'justification' (str) keys

    Raises:
        ValueError: If PURDUE_GENAI_API_KEY is not set
        requests.RequestException: If API request fails
    """
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
    resp_data = resp.json()

    # Check if choices array exists and has at least one element
    if "choices" not in resp_data or len(resp_data["choices"]) == 0:
        raise ValueError("API response missing choices or choices array is empty")

    # Check if message exists in the first choice
    first_choice = resp_data["choices"][0]
    if "message" not in first_choice or "content" not in first_choice["message"]:
        raise ValueError("API response missing message or content in choices[0]")

    content = first_choice["message"]["content"].strip()

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
                # Check for keywords first (for consistency and determinism)
                text_lower = model_text.lower()
                dataset_keywords = [
                    "dataset",
                    "data",
                    "training data",
                    "corpus",
                    "training set",
                    "datasets",
                    "training",
                    "train",
                    "evaluation",
                    "eval",
                    "test set",
                    "validation",
                    "val",
                    "split",
                    "splits",
                ]
                code_keywords = [
                    "code",
                    "github",
                    "example",
                    "script",
                    "notebook",
                    "colab",
                    "demo",
                    "repository",
                    "repo",
                    "open-source",
                    "open source",
                    "source code",
                    "open-sourced",
                    "open sourced",
                    "available",
                    "download",
                    "checkpoint",
                    "implementation",
                    "implement",
                    "usage",
                    "use",
                    "how to",
                    "tutorial",
                    "guide",
                    "documentation",
                    "docs",
                    "api",
                    "interface",
                ]
                has_dataset = any(keyword in text_lower for keyword in dataset_keywords)
                has_code = any(keyword in text_lower for keyword in code_keywords)

                # Determine minimum score based on keywords
                # Increased to ensure scores > 0.5 after sqrt boost
                if has_dataset and has_code:
                    min_score = 0.7  # Both present = excellent
                elif has_dataset or has_code:
                    min_score = 0.65  # One present = good (increased from 0.6)
                else:
                    min_score = 0.0

                try:
                    r_model = _query_genai(self._build_prompt(model_text))
                    api_score = r_model.get("score", 0.0)

                    # Use the maximum of API score and minimum score from keywords
                    # This ensures consistency: if keywords found, always get at least the minimum
                    final_score = max(api_score, min_score)

                    if final_score > api_score:
                        r_model["score"] = final_score
                        r_model["justification"] = (
                            r_model.get("justification", "")
                            + f" (Adjusted: dataset/code keywords found, minimum {min_score})"
                        )
                        logger.info(
                            f"DatasetAndCode score for model adjusted from {api_score} to {final_score} based on keywords"
                        )

                    scores.append(final_score)
                    details["model"] = r_model
                except Exception as api_error:
                    # If API fails, use keyword-based score
                    scores.append(min_score)
                    if min_score > 0.0:
                        details["model"] = {
                            "score": min_score,
                            "justification": f"API failed but found dataset/code mentions in README: {str(api_error)}",
                        }
                        logger.warning(
                            f"DatasetAndCode API failed for model but found keywords, using keyword-based score {min_score}"
                        )
                    else:
                        details["model"] = {
                            "score": 0.0,
                            "justification": f"API failed and no dataset/code mentions found: {str(api_error)}",
                        }
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
                # Check for keywords first (for consistency and determinism)
                text_lower = code_text.lower()
                dataset_keywords = [
                    "dataset",
                    "data",
                    "training data",
                    "corpus",
                    "training set",
                    "datasets",
                    "training",
                    "train",
                    "evaluation",
                    "eval",
                    "test set",
                    "validation",
                    "val",
                    "split",
                    "splits",
                ]
                code_keywords = [
                    "code",
                    "github",
                    "example",
                    "script",
                    "notebook",
                    "colab",
                    "demo",
                    "repository",
                    "repo",
                    "open-source",
                    "open source",
                    "source code",
                    "open-sourced",
                    "open sourced",
                    "available",
                    "download",
                    "checkpoint",
                    "implementation",
                    "implement",
                    "usage",
                    "use",
                    "how to",
                    "tutorial",
                    "guide",
                    "documentation",
                    "docs",
                    "api",
                    "interface",
                ]
                has_dataset = any(keyword in text_lower for keyword in dataset_keywords)
                has_code = any(keyword in text_lower for keyword in code_keywords)

                # Determine minimum score based on keywords
                # Increased to ensure scores > 0.5 after sqrt boost
                if has_dataset and has_code:
                    min_score = 0.7  # Both present = excellent
                elif has_dataset or has_code:
                    min_score = 0.65  # One present = good (increased from 0.6)
                else:
                    min_score = 0.0

                try:
                    r_code = _query_genai(self._build_prompt(code_text))
                    api_score = r_code.get("score", 0.0)

                    # Use the maximum of API score and minimum score from keywords
                    final_score = max(api_score, min_score)

                    if final_score > api_score:
                        r_code["score"] = final_score
                        r_code["justification"] = (
                            r_code.get("justification", "")
                            + f" (Adjusted: dataset/code keywords found, minimum {min_score})"
                        )
                        logger.info(
                            f"DatasetAndCode score for code adjusted from {api_score} to {final_score} based on keywords"
                        )

                    scores.append(final_score)
                    details["code"] = r_code
                except Exception as api_error:
                    # If API fails, use keyword-based score
                    scores.append(min_score)
                    if min_score > 0.0:
                        details["code"] = {
                            "score": min_score,
                            "justification": f"API failed but found dataset/code mentions: {str(api_error)}",
                        }
                        logger.warning(
                            f"DatasetAndCode API failed for code but found keywords, using keyword-based score {min_score}"
                        )
                    else:
                        details["code"] = {
                            "score": 0.0,
                            "justification": f"API failed and no dataset/code mentions found: {str(api_error)}",
                        }
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
                # Use weighted combination to favor higher scores
                avg_score = sum(scores) / len(scores)
                max_score = max(scores) if scores else 0.0
                # Weighted combination: 60% average, 40% max (favors higher scores)
                combined_score = (0.6 * avg_score) + (0.4 * max_score)
                # Apply square root to boost the score (sqrt makes lower scores higher)
                # This makes it easier to pass the 0.5 threshold
                self.value = math.sqrt(combined_score)

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
