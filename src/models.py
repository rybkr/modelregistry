"""Data models for representing ML models and evaluation metrics.

This module defines Pydantic models for representing machine learning models
with their associated resources (code, datasets) and evaluation metrics.
It includes models for size compatibility scores and complete metric sets
for model quality assessment.
"""

from typing import Annotated, Optional

from pydantic import BaseModel, Field, StringConstraints

from resources.code_resource import CodeResource
from resources.dataset_resource import DatasetResource
from resources.model_resource import ModelResource


class Model(BaseModel):
    """Represents a machine learning model with associated dataset and code resources.

    Attributes:
        model:   The model resource containing model-specific information.
        dataset: The dataset resource associated with model.
        code:    The code resource associated with the model.
    """

    model: ModelResource
    dataset: Optional[DatasetResource] = None
    code: Optional[CodeResource] = None


class SizeScore(BaseModel):
    """Model size compatibility scores for different deployment targets.

    Each attribute represents how well the model fits on a specific hardware
    platform, with scores ranging from 0.0 (incompatible) to 1.0 (optimal).

    Attributes:
        raspberry_pi: Compatibility score for Raspberry Pi deployment
        jetson_nano: Compatibility score for Jetson Nano deployment
        desktop_pc: Compatibility score for desktop PC deployment
        aws_server: Compatibility score for AWS server deployment
    """

    raspberry_pi: float = Field(1.0, ge=0, le=1)
    jetson_nano: float = Field(1.0, ge=0, le=1)
    desktop_pc: float = Field(1.0, ge=0, le=1)
    aws_server: float = Field(1.0, ge=0, le=1)


class Metrics(BaseModel):
    """Complete evaluation metrics for a model, dataset, or code resource.

    Contains quality, performance, and compatibility scores along with
    computation latencies for each metric. All scores range from 0.0 to 1.0.

    Attributes:
        name: Resource identifier (typically a URL)
        category: Resource type, must be "MODEL", "DATASET", or "CODE"
        net_score: Overall quality score (0.0-1.0)
        net_score_latency: Computation time for net_score in milliseconds
        ramp_up_time: Learning curve score (0.0-1.0)
        ramp_up_time_latency: Computation time in milliseconds
        bus_factor: Project sustainability score (0.0-1.0)
        bus_factor_latency: Computation time in milliseconds
        performance_claims: Performance validation score (0.0-1.0)
        performance_claims_latency: Computation time in milliseconds
        license: License compliance score (0.0-1.0)
        license_latency: Computation time in milliseconds
        size_score: Hardware compatibility scores by platform
        size_score_latency: Computation time in milliseconds
        dataset_and_code_score: Combined dataset/code availability score (0.0-1.0)
        dataset_and_code_score_latency: Computation time in milliseconds
        dataset_quality: Dataset quality assessment (0.0-1.0)
        dataset_quality_latency: Computation time in milliseconds
        code_quality: Code quality assessment (0.0-1.0)
        code_quality_latency: Computation time in milliseconds
    """

    name: str
    category: Annotated[str, StringConstraints(pattern="^(MODEL|DATASET|CODE)$")]

    net_score: float = Field(1.0, ge=0, le=1)
    net_score_latency: int = 200

    ramp_up_time: float = Field(1.0, ge=0, le=1)
    ramp_up_time_latency: int = 200

    bus_factor: float = Field(1.0, ge=0, le=1)
    bus_factor_latency: int = 200

    performance_claims: float = Field(1.0, ge=0, le=1)
    performance_claims_latency: int = 200

    license: float = Field(1.0, ge=0, le=1)
    license_latency: int = 200

    size_score: SizeScore
    size_score_latency: int = 200

    dataset_and_code_score: float = Field(1.0, ge=0, le=1)
    dataset_and_code_score_latency: int = 200

    dataset_quality: float = Field(1.0, ge=0, le=1)
    dataset_quality_latency: int = 200

    code_quality: float = Field(1.0, ge=0, le=1)
    code_quality_latency: int = 200
