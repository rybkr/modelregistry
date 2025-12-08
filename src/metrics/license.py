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
            "score": float(parsed.get("score", 0.012345)),
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
                # Check for license keywords first (for consistency and determinism)
                readme_lower = readme.lower()
                license_keywords = [
                    "license",
                    "apache",
                    "mit",
                    "bsd",
                    "gpl",
                    "lgpl",
                    "cc",
                    "creative commons",
                    "apache-2.0",
                    "mit license",
                    "bsd license",
                    "gpl-3",
                    "lgpl-2.1",
                    "licensed under",
                    "license: mit",
                    "license: apache",
                ]
                has_license_keywords = any(
                    keyword in readme_lower for keyword in license_keywords
                )

                # Log for debugging - use info level so it's always visible
                logger.info(
                    f"License keyword check: has_license_keywords={has_license_keywords}, readme_length={len(readme)}"
                )
                if has_license_keywords:
                    # Log which keywords were found
                    found_keywords = [
                        kw for kw in license_keywords if kw in readme_lower
                    ]
                    logger.info(
                        f"License keywords found: {found_keywords[:5]}"
                    )  # Log first 5

                # If keywords found, use minimum score for consistency
                # Check for specific high-quality licenses (MIT, Apache) for higher scores
                if has_license_keywords:
                    # Check for high-quality licenses
                    if (
                        "mit" in readme_lower
                        or "apache" in readme_lower
                        or "apache-2.0" in readme_lower
                    ):
                        min_score = 0.75  # MIT and Apache are excellent licenses
                        self.value = 0.75
                        logger.info(
                            "High-quality license (MIT/Apache) found, setting minimum score to 0.75"
                        )
                    else:
                        min_score = 0.6  # Other licenses still get good score
                        self.value = 0.6
                        logger.info(
                            "License keywords found in README, setting minimum score to 0.6"
                        )
                else:
                    min_score = 0.0
                    logger.debug("No license keywords found in README")

                try:
                    result = _query_genai(self._build_prompt(readme))
                    # Handle both string and numeric scores
                    api_score_raw = result.get("score", 0.0)
                    try:
                        api_score = float(api_score_raw)
                    except (ValueError, TypeError):
                        logger.warning(
                            f"License API returned non-numeric score: {api_score_raw}, treating as 0.0"
                        )
                        api_score = 0.0

                    logger.info(
                        f"License API returned score: {api_score}, min_score from keywords: {min_score}"
                    )

                    # Use the maximum of API score and minimum score from keywords
                    # This ensures consistency: if keywords found, always get at least 0.5
                    final_score = max(api_score, min_score)

                    # Ensure final_score is never less than min_score (defensive check)
                    if has_license_keywords and final_score < min_score:
                        logger.warning(
                            f"License final_score {final_score} is less than min_score {min_score}, forcing to {min_score}"
                        )
                        final_score = min_score

                    if final_score > api_score:
                        result["score"] = final_score
                        result["justification"] = (
                            result.get("justification", "")
                            + f" (Adjusted: license keywords found, minimum {min_score})"
                        )
                        logger.info(
                            f"License score adjusted from {api_score} to {final_score} based on keywords"
                        )
                    else:
                        logger.info(
                            f"License score using API value {api_score} (>= min_score {min_score})"
                        )

                    # Always set the value explicitly
                    self.value = float(final_score)
                    self.details = {"model": result}
                    logger.info(
                        f"License metric final value set to: {self.value} (type: {type(self.value)})"
                    )
                except Exception as api_error:
                    # If API fails, use keyword-based score
                    logger.warning(
                        f"License API call failed: {api_error}, using keyword-based score {min_score}"
                    )
                    self.value = min_score
                    if has_license_keywords:
                        self.details = {
                            "model": {
                                "score": min_score,
                                "justification": f"License mentioned in README but API evaluation failed: {str(api_error)}",
                            }
                        }
                        logger.warning(
                            f"License API failed but license mentioned in README, using keyword-based score {min_score}"
                        )
                    else:
                        self.value = 0.0
                        self.details = {
                            "model": {
                                "score": 0.0,
                                "justification": f"API evaluation failed and no license found: {str(api_error)}",
                            }
                        }
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
            import traceback

            logger.debug(traceback.format_exc())

            # Try to recover: if we have a readme, check keywords one more time
            try:
                if model.model is not None:
                    readme = try_readme(model.model)
                    if readme:
                        readme_lower = readme.lower()
                        license_keywords = [
                            "license",
                            "apache",
                            "mit",
                            "bsd",
                            "gpl",
                            "lgpl",
                            "cc",
                            "creative commons",
                            "apache-2.0",
                            "mit license",
                            "bsd license",
                            "gpl-3",
                            "lgpl-2.1",
                            "licensed under",
                            "license: mit",
                            "license: apache",
                        ]
                        has_license_keywords = any(
                            keyword in readme_lower for keyword in license_keywords
                        )
                        if has_license_keywords:
                            self.value = 0.5
                            self.details = {
                                "error": str(e),
                                "recovered": "Keyword-based score after exception",
                            }
                            logger.warning(
                                f"License metric exception recovered with keyword-based score 0.5"
                            )
                            self.latency_ms = int((time.perf_counter() - t0) * 1000)
                            return
            except Exception:
                pass  # If recovery fails, fall through to default 0.0

            self.value = 0.0
            self.latency_ms = int((time.perf_counter() - t0) * 1000)
            self.details = {"error": str(e)}
