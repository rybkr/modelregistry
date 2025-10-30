from models import Metrics, SizeScore

# where to write the golden file
# REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
GOLDEN_FILE = "test/golden/metrics.ndjson"

# sample "golden" object
example = Metrics(
    name="bert-base",
    category="MODEL",
    net_score=0.82,
    net_score_latency=120,
    ramp_up_time=0.9,
    ramp_up_time_latency=100,
    bus_factor=0.7,
    bus_factor_latency=95,
    performance_claims=0.85,
    performance_claims_latency=110,
    license=1.0,
    license_latency=50,
    size_score=SizeScore(
        raspberry_pi=0.2,
        jetson_nano=0.4,
        desktop_pc=0.9,
        aws_server=1.0,
    ),
    size_score_latency=200,
    dataset_and_code_score=0.8,
    dataset_and_code_score_latency=70,
    dataset_quality=0.75,
    dataset_quality_latency=65,
    code_quality=0.9,
    code_quality_latency=60,
)

# ensure golden directory exists
# GOLDEN_FILE.parent.mkdir(parents=True, exist_ok=True)

# write as NDJSON (one line per object)
with open(GOLDEN_FILE, "w") as f:
    f.write(example.model_dump_json() + "\n")

print(f"Golden file written to {GOLDEN_FILE}")
