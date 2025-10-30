from typing import Annotated, Optional

from pydantic import BaseModel, Field, StringConstraints

from resources.code_resource import CodeResource
from resources.dataset_resource import DatasetResource
from resources.model_resource import ModelResource


class Model(BaseModel):
    """Represents a machine learning model with associated dataset and code resources.

    Attributes:
        model (ModelResource): The model resource containing model-specific information.
        dataset (Optional[DatasetResource]): The dataset resource associated with model.
        code (Optional[CodeResource]): The code resource associated with the model.
    """

    model: ModelResource
    dataset: Optional[DatasetResource] = None
    code: Optional[CodeResource] = None


class SizeScore(BaseModel):
    """Calculates the score for size metric."""

    raspberry_pi: float = Field(1.0, ge=0, le=1)
    jetson_nano: float = Field(1.0, ge=0, le=1)
    desktop_pc: float = Field(1.0, ge=0, le=1)
    aws_server: float = Field(1.0, ge=0, le=1)


class Metrics(BaseModel):
    """Base model for the metrics calculations."""

    name: str
    category: Annotated[
        str, StringConstraints(pattern="^(MODEL|DATASET|CODE)$")
    ]  # enum-like restriction

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
