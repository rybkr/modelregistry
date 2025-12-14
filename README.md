# Model Registry

A trustworthy model registry for machine learning models with REST API, web interface, and cloud deployment on AWS. The Model Registry provides comprehensive quality metrics evaluation, package management, and a user-friendly web interface for managing ML models, datasets, and code repositories.

## Purpose

The Model Registry is designed to help organizations:
- **Evaluate ML Models**: Automatically compute quality metrics including license compatibility, code quality, performance claims, and more
- **Manage Packages**: Upload, search, and manage ML models, datasets, and code repositories
- **Ingest from HuggingFace**: Automatically ingest and evaluate models from HuggingFace with quality scoring
- **Track Quality Metrics**: Monitor model quality through comprehensive metrics including Net Score, Ramp-Up Time, Bus Factor, and more
- **Web Interface**: User-friendly web UI for browsing, uploading, and managing packages
- **Health Monitoring**: System health dashboard with activity tracking and logging

## Features

### ✅ Implemented Features
- **REST API**: Full CRUD operations for packages
- **Web Interface**: Modern, accessible web UI with WCAG 2.1 AA compliance
- **Package Management**: Upload, list, search, and delete packages
- **HuggingFace Integration**: Ingest models directly from HuggingFace
- **Quality Metrics**: Comprehensive metric evaluation system
- **Health Dashboard**: System monitoring and activity tracking
- **Authentication**: User authentication and authorization system
- **Search & Filtering**: Advanced search with regex support, sorting, and pagination
- **CI/CD Pipeline**: Automated testing and deployment via GitHub Actions
- **AWS Deployment**: Elastic Beanstalk deployment with automated CI/CD
- **End-to-End Testing**: Comprehensive Selenium-based GUI tests

### Quality Metrics
The registry evaluates models using the following metrics:
- **Net Score**: Overall quality score (weighted combination of all metrics)
- **License**: License clarity and LGPLv2.1 compatibility
- **Ramp-Up Time**: How quickly new users can start using the repository
- **Bus Factor**: Risk of abandonment based on contributors and activity
- **Dataset & Code Availability**: Presence of datasets and code for reproducibility
- **Dataset Quality**: Trustworthiness and maintenance of datasets
- **Code Quality**: Code style, type checking, and popularity signals
- **Performance Claims**: Evidence of performance benchmarks and results
- **Size**: Model size and device compatibility
- **Reviewedness**: Code review coverage and quality

## Quick Start

### Prerequisites
- Python 3.9 or higher
- pip package manager
- (Optional) AWS CLI for cloud deployment
- (Optional) Chrome/ChromeDriver for end-to-end tests

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd modelregistry
   ```

2. **Install dependencies**
   ```bash
   pip install -e ".[dev]"
   ```
   Or using requirements.txt:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up pre-commit hooks (optional)**
   ```bash
   pre-commit install
   ```

## Configuration

### Environment Variables

The Model Registry can be configured using the following environment variables:

#### Required for Full Functionality
- **`PORT`** (default: `8000`): Port number for the Flask server
- **`GH_API_TOKEN`** or **`GITHUB_TOKEN`**: GitHub API token for accessing GitHub repositories (required for code quality and reviewedness metrics)
- **`PURDUE_GENAI_API_KEY`**: Purdue GenAI API key for LLM-based metric evaluation (required for license, dataset/code, and performance claims metrics)

#### Optional Configuration
- **`USER_STORAGE_BUCKET`**: AWS S3 bucket name for storing package files (optional, uses in-memory storage if not set)
- **`DEFAULT_ADMIN_PASSWORD_HASH`**: Bcrypt hash for default admin user password (auto-generated if not set)
- **`LOG_FILE`**: Path to log file (logging disabled if not set)
- **`LOG_LEVEL`**: Logging level (`0` = silent, `1` = info, `2` = debug, default: `0`)

#### AWS Deployment
- **`AWS_ACCESS_KEY_ID`**: AWS access key for deployment
- **`AWS_SECRET_ACCESS_KEY`**: AWS secret key for deployment
- **`AWS_REGION`**: AWS region for deployment (e.g., `us-east-1`)

### Configuration File

Create a `.env` file in the project root (optional, for local development):
```bash
PORT=8000
GITHUB_TOKEN=your_github_token_here
PURDUE_GENAI_API_KEY=your_purdue_genai_key_here
LOG_LEVEL=1
LOG_FILE=model_registry.log
```

**Note**: The `.env` file is gitignored and should not be committed to version control.

## Running the Application

### Local Development

1. **Start the API server**
   ```bash
   python src/api_server.py
   ```
   Or using the application entry point:
   ```bash
   python src/application.py
   ```

2. **Access the web interface**
   - Web UI: http://localhost:8000
   - API: http://localhost:8000/api/health

3. **Run tests**
   ```bash
   # Run all tests
   pytest
   
   # Run with coverage
   pytest --cov=src --cov-report=html
   
   # Run end-to-end tests (requires Chrome)
   pytest test/e2e/ -v -m e2e
   
   # Run specific test file
   pytest test/test_api_crud.py -v
   ```

### Using the Legacy CLI Tool

The Phase 1 command-line tool is still available:
```bash
./run install    # Install dependencies
./run test       # Run tests  
./run urls.txt   # Evaluate models from URLs
```

## Deployment

### AWS Elastic Beanstalk Deployment

The Model Registry can be deployed to AWS Elastic Beanstalk with automated CI/CD.

#### Quick Deploy (5 minutes)

1. **Configure AWS CLI**
   ```bash
   aws configure
   ```

2. **Run setup script**
   ```bash
   ./scripts/aws_setup.sh
   ```

3. **Add secrets to GitHub**
   - Go to: Settings → Secrets → Actions
   - Add: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`

4. **Push to deploy**
   ```bash
   git push origin main
   ```

**Cost**: $0/month on AWS Free Tier ✅

#### Detailed Deployment Guides

- **[QUICK_START_AWS.md](./QUICK_START_AWS.md)** - 5-minute quick start
- **[AWS_DEPLOYMENT_GUIDE.md](./AWS_DEPLOYMENT_GUIDE.md)** - Detailed guide
- **[AWS_SETUP_CHECKLIST.md](./AWS_SETUP_CHECKLIST.md)** - Step-by-step checklist

### Manual Deployment

1. **Set environment variables** on your deployment platform
2. **Install dependencies**: `pip install -r requirements.txt`
3. **Run the application**: `python src/application.py` or use a WSGI server like gunicorn:
   ```bash
   gunicorn -w 4 -b 0.0.0.0:8000 application:application
   ```

## Interacting with the Model Registry

### Web Interface

The Model Registry provides a user-friendly web interface accessible at `http://localhost:8000` (or your deployment URL).

#### Available Pages

1. **Packages Page** (`/`)
   - Browse all packages
   - Search and filter packages
   - Sort by name, version, size, or date
   - Pagination support
   - Regex search option

2. **Upload Page** (`/upload`)
   - Upload new packages manually
   - Enter package name, version, URL, content, and metadata
   - Form validation and error handling

3. **Ingest Page** (`/ingest`)
   - Ingest models directly from HuggingFace
   - Automatic quality metric evaluation
   - Progress tracking during evaluation

4. **Package Detail Page** (`/packages/<id>`)
   - View detailed package information
   - See quality metrics and scores
   - Rate packages
   - Delete packages
   - View metadata

5. **Health Dashboard** (`/health`)
   - System health status
   - Package count and statistics
   - Activity timeline
   - System logs
   - Reset registry option

#### Web Interface Features

- **WCAG 2.1 AA Compliant**: Fully accessible interface
- **Responsive Design**: Works on desktop and mobile devices
- **Real-time Updates**: Dynamic content loading with live regions
- **Error Handling**: User-friendly error messages and validation
- **Keyboard Navigation**: Full keyboard accessibility support

### REST API

The Model Registry provides a comprehensive REST API for programmatic access.

#### Base URL
- Local: `http://localhost:8000/api`
- Production: `https://your-deployment-url/api`

#### Authentication

Most endpoints require authentication. Authenticate first:
```bash
PUT /api/authenticate
Content-Type: application/json

{
  "user": {"name": "username"},
  "secret": {"password": "password"}
}
```

Response includes an authentication token to use in subsequent requests:
```bash
X-Authorization: <token>
```

#### API Endpoints

##### Health Check
```bash
GET /api/health
```
Returns system health status.

##### Package Management

**List Packages**
```bash
GET /api/packages?offset=0&limit=25&name=search_term&version=1.0.0
```
Query parameters:
- `offset`: Pagination offset (default: 0)
- `limit`: Results per page (default: 25)
- `name`: Search by name (supports regex if `use_regex=true`)
- `version`: Filter by version
- `use_regex`: Enable regex search (default: false)
- `sort_field`: Sort by `alpha`, `version`, `size`, or `date`
- `sort_order`: `ascending` or `descending`

**Get Package**
```bash
GET /api/packages/<package_id>
```
Returns detailed package information including metrics.

**Upload Package**
```bash
POST /api/packages
Content-Type: application/json
X-Authorization: <token>

{
  "name": "My Model",
  "version": "1.0.0",
  "metadata": {
    "url": "https://huggingface.co/org/model",
    "description": "Model description"
  }
}
```

**Delete Package**
```bash
DELETE /api/packages/<package_id>
X-Authorization: <token>
```

**Rate Package**
```bash
POST /api/packages/<package_id>/rate
Content-Type: application/json
X-Authorization: <token>

{
  "rating": 4.5
}
```

##### Model Ingestion

**Ingest from HuggingFace**
```bash
POST /api/ingest
Content-Type: application/json
X-Authorization: <token>

{
  "url": "https://huggingface.co/org/model-name"
}
```

The system will:
1. Fetch model metadata from HuggingFace
2. Evaluate all quality metrics
3. Only ingest if all non-latency metrics score ≥ 0.5
4. Return package ID and metrics

##### System Management

**Reset Registry**
```bash
DELETE /api/reset
X-Authorization: <token>
```
⚠️ **Warning**: This deletes all packages and resets to default state.

**Get Health Dashboard Data**
```bash
GET /api/health/dashboard
X-Authorization: <token>
```

**Get Activity Logs**
```bash
GET /api/health/activity
X-Authorization: <token>
```

**Get System Logs**
```bash
GET /api/health/logs
X-Authorization: <token>
```

#### Example API Usage

**Python Example**
```python
import requests

BASE_URL = "http://localhost:8000/api"

# Authenticate
auth_response = requests.put(
    f"{BASE_URL}/authenticate",
    json={"user": {"name": "admin"}, "secret": {"password": "password"}}
)
token = auth_response.json()

headers = {"X-Authorization": token}

# List packages
response = requests.get(f"{BASE_URL}/packages", headers=headers)
packages = response.json()

# Upload a package
package_data = {
    "name": "My Model",
    "version": "1.0.0",
    "metadata": {"url": "https://huggingface.co/org/model"}
}
response = requests.post(
    f"{BASE_URL}/packages",
    json=package_data,
    headers=headers
)
package = response.json()
```

**cURL Example**
```bash
# Authenticate
TOKEN=$(curl -X PUT http://localhost:8000/api/authenticate \
  -H "Content-Type: application/json" \
  -d '{"user":{"name":"admin"},"secret":{"password":"password"}}')

# List packages
curl -H "X-Authorization: $TOKEN" \
  http://localhost:8000/api/packages

# Upload package
curl -X POST http://localhost:8000/api/packages \
  -H "X-Authorization: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Model",
    "version": "1.0.0",
    "metadata": {"url": "https://huggingface.co/org/model"}
  }'
```

## Development

### Project Structure

```
modelregistry/
├── src/                    # Source code
│   ├── api_server.py      # Flask API server
│   ├── application.py     # WSGI entry point
│   ├── storage.py         # Storage layer
│   ├── auth.py            # Authentication
│   ├── metrics/           # Quality metrics
│   ├── resources/         # Resource adapters
│   ├── templates/         # HTML templates
│   └── static/            # CSS, JS, assets
├── test/                  # Test suite
│   ├── unit/              # Unit tests
│   ├── integration/       # Integration tests
│   └── e2e/               # End-to-end Selenium tests
├── scripts/               # Utility scripts
├── .github/workflows/     # CI/CD pipelines
└── docs/                  # Documentation
```

### Development Standards

#### CI Requirements

Our CI runs on **Python 3.11 and 3.12** and enforces these gates:

1. **Formatting (Black)**: `black --check .`
2. **Import Sorting (isort)**: `isort --check-only --diff .`
3. **Linting (Flake8)**: `flake8 .`
4. **Type Checks (mypy)**: `mypy`
5. **Tests + Coverage**: ≥ 70% coverage required

#### Running Tests

```bash
# All tests
pytest

# With coverage report
pytest --cov=src --cov-report=html

# Specific test category
pytest test/unit/          # Unit tests only
pytest test/integration/    # Integration tests only
pytest test/e2e/ -m e2e    # End-to-end tests only

# Specific test file
pytest test/test_api_crud.py -v
```

#### Pre-commit Hooks

```bash
pip install -e ".[dev]"
pre-commit install
pre-commit run --all-files
```

### Code Quality Metrics

The registry evaluates models using comprehensive metrics:

| **Metric**                  | **Description** |
|------------------------------|-----------------|
| **Size**                     | Computes total model file size and scores compatibility against device memory budgets (Pi, Nano, PC, AWS) using a smoothstep curve |
| **License**                  | Uses Purdue GenAI LLM to parse README/metadata for license clarity and LGPLv2.1 compatibility |
| **Ramp-Up Time**             | Estimates how quickly a new user can start using the repository based on README quality, examples, and HuggingFace likes |
| **Bus Factor**               | Combines number of unique contributors with recency of updates (exponential decay, 1-year half-life) |
| **Available Dataset & Code** | Uses GenAI to semantically evaluate README for dataset and code references |
| **Dataset Quality**          | Evaluates dataset trustworthiness based on metadata, recency, and community validation |
| **Code Quality**             | Runs flake8 and mypy on linked repos, combines with popularity signals |
| **Performance Claims**       | Structured 4-bucket scoring: 0.0 (no claims) → 0.25 → 0.6 → 0.9 → 1.0 (concrete results) |
| **Reviewedness**             | Evaluates code review coverage and quality from GitHub PRs and reviews |
| **Net Score**                | Weighted combination: License (0.20), Ramp-Up (0.15), Bus Factor (0.15), Dataset & Code (0.10), Dataset Quality (0.10), Code Quality (0.10), Performance (0.10), Size (0.10) |

## Documentation

- **[E2E Tests README](./test/e2e/README.md)** - End-to-end testing guide
- **[WCAG Compliance Assessment](./WCAG_COMPLIANCE_ASSESSMENT.md)** - Accessibility compliance details
- **[OpenAPI Spec](./openapi-spec.yml)** - API specification

## Troubleshooting

### Common Issues

1. **Port already in use**
   - Change the `PORT` environment variable
   - Or stop the process using port 8000

2. **GitHub API rate limiting**
   - Ensure `GH_API_TOKEN` or `GITHUB_TOKEN` is set
   - Use a personal access token with appropriate permissions

3. **Metrics evaluation fails**
   - Check that `PURDUE_GENAI_API_KEY` is set (if using LLM-based metrics)
   - Some metrics work without API keys but with reduced functionality

4. **AWS deployment issues**
   - Verify AWS credentials are set correctly
   - Check Elastic Beanstalk logs: `eb logs`
   - Ensure environment variables are set in EB configuration

## Contributing

See the project's contribution guidelines for information on:
- Code style and standards
- Testing requirements
- Pull request process
- Development workflow

## Contributors

* [Aadhavan Srinivasan](https://github.com/aadhavans2027)
* [Ryan Baker](https://github.com/rybkr)
* [Luisa Cruz Miotto](https://github.com/lcruzmio)
* [Nikhil Chaudhary](https://github.com/chaudhary-nikhil)

## License

[Add license information here]

---

**Last Updated**: 2025
