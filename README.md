# Model-Audit-CLI

A lightweight CLI for managing and evaluating Hugging Face models: fetch metadata, run local checks, and compute metrics with reproducible outputs and CI-friendly reports.

## Dependency Management
---

To install all dependencies run the following command

```
pip install -e ".[dev]"
```
---
## Contributing & CI Requirements

Our CI runs on **Python 3.11 and 3.12** and enforces these gates. Please run them locally before pushing or opening a PR.

1) **Formatting (Black)**  
Check only (no edits):
```bash
black --check .
```
Auto-format:
```bash
black .
```

2) **Import Sorting (isort)**  
Check only:
```bash
isort --check-only --diff .
```
Auto-fix:
```bash
isort .
```

3) **Linting (Flake8 + Docstrings)**
```bash
flake8 .
```

4) **Type Checks (mypy)**
```bash
mypy
```

5) **Tests + Coverage (unit tests)**  
CI expects all tests to pass and **≥ 80%** code coverage over `src/`.

Optional HTML report (human-friendly):
```bash
pytest --cov=src --cov-report=html:test/_htmlcov
# open test/_htmlcov/index.html
```

---

## Pre-commit (recommended)

We use **pre-commit** so formatting/linting/type checks run automatically on commit.

**One-time setup:**
```bash
pip install -e ".[dev]"
pre-commit install
pre-commit run --all-files   # baseline the repo once
```

THe phase-1 `run` script that serves as the CLI entrypoint for the project.  
It currently supports three commands required by the specification:

 `./run install`  
  Installs project dependencies and exits with code 0 on success.

 `./run test`  
  Runs the pytest test suite, generates JUnit + coverage XML reports, and prints a summary
  of passed/failed test cases and code coverage percentage.

 `./run urls.txt`  
  Reads a list of URLs and evaluates each. For now, metrics return
  placeholder values, formatted as NDJSON lines. 

| **Metric**                  | **Operationalization** |
|------------------------------|-------------------------|
| **Size**                     | Computes total model file size from weight files and scores compatibility against device memory budgets (Pi, Nano, PC, AWS) using a smoothstep curve, outputting per-device scores (0–1) and latency. **Justification**: Deployability depends on size. |
| **License**                  | Uses Purdue GenAI LLM to parse README/metadata for license clarity and LGPLv2.1 compatibility. Returns JSON with score (1.0 = clear/compatible, partial credit if unclear/uncommon, 0.0 = missing or incompatible). **Justification**: License compatibility is a hard requirement for ACME. |
| **Ramp-Up Time**             | Estimates how quickly a new user can start using the repository. Computed from README length (docs quality) and number of model files (ease of reuse). Weighted 0.6/0.4, normalized to [0,1]. External: Hugging Face API (file fetch). **Calculation**: `0.4·(README content) + 0.35·(Examples/Notebooks) + 0.25·(HuggingFace Likes)`. **Justification**: The most important factors are README content and usable examples; HF likes serve as an additional signal of reliability. |
| **Bus Factor**               | Combines number of unique contributors (normalized) with recency of updates (exponential decay, 1-year half-life). Produces a 0–1 score, higher for projects with many contributors and recent activity. **Justification**: Reduces risk of abandonment. |
| **Available Dataset & Code** | Same scoring logic (1.0 / 0.5 / 0.0), but implementation uses GenAI to semantically evaluate the README. The LLM identifies mentions of datasets (e.g., “evaluated on GLUE”) and code references (GitHub links, HuggingFace Spaces, etc.), even if phrased in non-standard ways. **Justification**: Reproducibility requires dataset + code. |
| **Dataset Quality**          | Evaluates how trustworthy and well-maintained a dataset is, based on repository metadata (description, license, homepage), recency of updates, community validation (stars, forks, watchers, subscribers), and presence of example/tutorial signals. Returns a weighted score in 0,1. |
| **Code Quality**             | Runs flake8 (style/lint) and mypy (type checks) on the linked repo, and uses GitHub/GitLab/HF stars/likes as a popularity signal. Combines these into a score ∈ [0, 1] (higher = cleaner, more trusted code). **Justification**: Maintainability and reliability. |
| **Performance Claims**       | Implemented structured 4-bucket scoring system: 0.0 → no claims, 0.5 → vague statements only (e.g., “shows good results”), 0.75 → dataset/benchmark/metric mentioned but no numbers (e.g., “evaluated on GLUE”) 1.0 → concrete numerical results, tables, or linked papers. Uses GenAI to classify text into one of these categories and return structured JSON. **Justification**: ACME wants evidence of performance. |
| **Net Score**                | Calculates an overall model quality score in [0–1] by combining the results of all metrics using fixed weights that reflect Sarah’s priorities (License 0.20, Ramp-Up Time 0.15, Bus Factor 0.15, Dataset & Code Availability 0.10, Dataset Quality 0.10, Code Quality 0.10, Performance Claims 0.10, Size 0.10). For the Size metric, the average across device scores is used. The implementation iterates through all metric outputs, multiplies each by its weight, sums them, and records the total computation latency in milliseconds.|


## Contributors
* [Noddie Mgbodille](https://github.com/nmgbodil)
* [Will Ott](https://github.com/willott29)
* [Trevor Ju](https://github.com/teajuw)
* [Anna Stark](https://github.com/annastarky)
