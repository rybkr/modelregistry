# Model Registry - Phase 2

A trustworthy model registry for machine learning models with REST API, web interface, and cloud deployment on AWS.

## Phase 2 Progress

### ✅ Completed
- **Basic CRUD Operations**: Upload, list, get, and delete packages via REST API
- **CI/CD Pipeline**: GitHub Actions for testing and deployment
- **Storage Layer**: In-memory storage (to be migrated to AWS DynamoDB)
- **API Testing**: Basic test suite for CRUD operations

### 🚧 In Progress  
- **AWS Integration**: Setting up S3, DynamoDB, and Lambda/EC2
- **Model Ingest**: HuggingFace model ingestion with Phase 1 metrics
- **Enumerate**: Search and pagination for large registries
- **Rate Endpoint**: Integrate Phase 1 scoring metrics

### 📋 TODO
- Web UI frontend
- Authentication system
- Observability dashboard
- Security analysis (STRIDE, OWASP Top 10)
- Extended requirements selection

## Quick Start

### Installation
```bash
pip install -e ".[dev]"
```

### Run the API Server
```bash
python src/api_server.py
```

The server will start on `http://localhost:8000`

### API Endpoints

- `GET /health` - Health check
- `POST /packages` - Upload a package
- `GET /packages` - List all packages
- `GET /packages/<id>` - Get a specific package
- `DELETE /packages/<id>` - Delete a package
- `DELETE /reset` - Reset registry to default state

### Running Tests
```bash
pytest test/test_api_crud.py
```

## Phase 1 CLI (Legacy)

The Phase 1 command-line tool is still available:

```bash
./run install    # Install dependencies
./run test       # Run tests  
./run urls.txt   # Evaluate models from URLs
```

See below for Phase 1 metrics and implementation details.

---

## Phase 1 Metrics

| **Metric**                  | **Operationalization** |
|------------------------------|-------------------------|
| **Size**                     | Computes total model file size from weight files and scores compatibility against device memory budgets (Pi, Nano, PC, AWS) using a smoothstep curve, outputting per-device scores (0–1) and latency. **Justification**: Deployability depends on size. |
| **License**                  | Uses Purdue GenAI LLM to parse README/metadata for license clarity and LGPLv2.1 compatibility. Returns JSON with score (1.0 = clear/compatible, partial credit if unclear/uncommon, 0.0 = missing or incompatible). **Justification**: License compatibility is a hard requirement for ACME. |
| **Ramp-Up Time**             | Estimates how quickly a new user can start using the repository. Computed from README length (docs quality) and number of model files (ease of reuse). Weighted 0.6/0.4, normalized to [0,1]. External: Hugging Face API (file fetch). **Calculation**: `0.4·(README content) + 0.35·(Examples/Notebooks) + 0.25·(HuggingFace Likes)`. **Justification**: The most important factors are README content and usable examples; HF likes serve as an additional signal of reliability. |
| **Bus Factor**               | Combines number of unique contributors (normalized) with recency of updates (exponential decay, 1-year half-life). Produces a 0–1 score, higher for projects with many contributors and recent activity. **Justification**: Reduces risk of abandonment. |
| **Available Dataset & Code** | Same scoring logic (1.0 / 0.5 / 0.0), but implementation uses GenAI to semantically evaluate the README. The LLM identifies mentions of datasets (e.g., "evaluated on GLUE") and code references (GitHub links, HuggingFace Spaces, etc.), even if phrased in non-standard ways. **Justification**: Reproducibility requires dataset + code. |
| **Dataset Quality**          | Evaluates how trustworthy and well-maintained a dataset is, based on repository metadata (description, license, homepage), recency of updates, community validation (stars, forks, watchers, subscribers), and presence of example/tutorial signals. Returns a weighted score in 0,1. |
| **Code Quality**             | Runs flake8 (style/lint) and mypy (type checks) on the linked repo, and uses GitHub/GitLab/HF stars/likes as a popularity signal. Combines these into a score ∈ [0, 1] (higher = cleaner, more trusted code). **Justification**: Maintainability and reliability. |
| **Performance Claims**       | Implemented structured 4-bucket scoring system: 0.0 → no claims, 0.5 → vague statements only (e.g., "shows good results"), 0.75 → dataset/benchmark/metric mentioned but no numbers (e.g., "evaluated on GLUE") 1.0 → concrete numerical results, tables, or linked papers. Uses GenAI to classify text into one of these categories and return structured JSON. **Justification**: ACME wants evidence of performance. |
| **Net Score**                | Calculates an overall model quality score in [0–1] by combining the results of all metrics using fixed weights that reflect Sarah's priorities (License 0.20, Ramp-Up Time 0.15, Bus Factor 0.15, Dataset & Code Availability 0.10, Dataset Quality 0.10, Code Quality 0.10, Performance Claims 0.10, Size 0.10). For the Size metric, the average across device scores is used. The implementation iterates through all metric outputs, multiplies each by its weight, sums them, and records the total computation latency in milliseconds.|

---

## Development Standards

### CI Requirements

Our CI runs on **Python 3.11 and 3.12** and enforces these gates:

1. **Formatting (Black)**: `black --check .`
2. **Import Sorting (isort)**: `isort --check-only --diff .`
3. **Linting (Flake8)**: `flake8 .`
4. **Type Checks (mypy)**: `mypy`
5. **Tests + Coverage**: ≥ 70% coverage required

### Pre-commit Hooks
```bash
pip install -e ".[dev]"
pre-commit install
pre-commit run --all-files
```

## Contributors
* [Noddie Mgbodille](https://github.com/nmgbodil)
* [Will Ott](https://github.com/willott29)
* [Trevor Ju](https://github.com/teajuw)
* [Anna Stark](https://github.com/annastarky)
