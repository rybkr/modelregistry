from metrics.base_metric import Metric
from metrics.bus_factor import BusFactor
from metrics.code_quality import CodeQuality
from metrics.dataset_and_code import DatasetAndCode
from metrics.dataset_quality import DatasetQuality
from metrics.license import License
from metrics.performance import Performance
from metrics.ramp_up_time import RampUpTime
from metrics.reviewedness import Reviewedness
from metrics.size import Size

ALL_METRICS: list[Metric] = [
    RampUpTime(),
    BusFactor(),
    CodeQuality(),
    Size(),
    License(),
    Performance(),
    DatasetAndCode(),
    DatasetQuality(),
    Reviewedness(),
    # add more metrics here
]

METRICS_BY_NAME: dict[str, Metric] = {m.name: m for m in ALL_METRICS}
