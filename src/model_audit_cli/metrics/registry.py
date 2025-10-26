from model_audit_cli.metrics.base_metric import Metric
from model_audit_cli.metrics.bus_factor import BusFactor
from model_audit_cli.metrics.code_quality import CodeQuality
from model_audit_cli.metrics.dataset_and_code import DatasetAndCode
from model_audit_cli.metrics.dataset_quality import DatasetQuality
from model_audit_cli.metrics.license import License
from model_audit_cli.metrics.performance import Performance
from model_audit_cli.metrics.ramp_up_time import RampUpTime
from model_audit_cli.metrics.size import Size

ALL_METRICS: list[Metric] = [
    RampUpTime(),
    BusFactor(),
    CodeQuality(),
    Size(),
    License(),
    Performance(),
    DatasetAndCode(),
    DatasetQuality(),
    # add more metrics here
]

METRICS_BY_NAME: dict[str, Metric] = {m.name: m for m in ALL_METRICS}
