.PHONY: test clean install serve test-api health upload list reset ingest lint format type-check security-check ci

# Setup and installation
install:
	@pip install -e ".[dev]"
	@pre-commit install

# Code quality
lint:
	@echo "Running linters..."
	@flake8 src test --count --select=E9,F63,F7,F82 --show-source --statistics
	@flake8 src test --count --exit-zero --max-complexity=10 --max-line-length=88 --statistics

format:
	@echo "Formatting code..."
	@black src test
	@isort src test

type-check:
	@echo "Type checking..."
	@mypy src --ignore-missing-imports

security-check:
	@echo "Running security checks..."
	@bandit -r src -ll || true
	@safety check || true

# Testing
test:
	@python3 -m pytest --cov=src --cov-report=html:test/_htmlcov --junitxml=test/_junit.xml -v
	@echo "Open test/_htmlcov/index.html in a browser for full coverage report."

test-fast:
	@python3 -m pytest --cov=src --cov-report=term-missing -v -m "not integration and not e2e"

test-integration:
	@python3 -m pytest test/integration -v -m integration

test-e2e:
	@python3 -m pytest test/e2e -v -m e2e

# Full CI pipeline (matches GitHub Actions)
ci: lint type-check test security-check
	@echo "✅ All checks passed!"

# Cleanup
clean:
	@find . -type d -name "__pycache__" -exec rm -r {} +
	@rm -f .api_server.pid
	@rm -rf test/_htmlcov
	@rm -f test/_coverage.xml test/_junit.xml
	@rm -rf dist build *.egg-info

# API server commands
serve:
	@echo "Starting API server on http://localhost:8000"
	@python src/api_server.py

test-api:
	@echo "Running API tests..."
	@python src/api_server.py > /dev/null 2>&1 & echo $$! > .api_server.pid
	@sleep 2
	@pytest test/test_api_crud.py -v || true
	@-kill `cat .api_server.pid` 2>/dev/null
	@rm -f .api_server.pid

health:
	@python src/api_server.py > /dev/null 2>&1 & echo $$! > .api_server.pid
	@sleep 2
	@curl -s http://localhost:8000/health | python -m json.tool || true
	@-kill `cat .api_server.pid` 2>/dev/null
	@rm -f .api_server.pid

upload:
	@python src/api_server.py > /dev/null 2>&1 & echo $$! > .api_server.pid
	@sleep 2
	@curl -s -X POST http://localhost:8000/packages \
		-H "Content-Type: application/json" \
		-d '{"name": "gpt2-model", "version": "1.0.0", "metadata": {"url": "https://huggingface.co/openai-community/gpt2", "readme": "GPT-2 is a transformer model"}}' \
		| python -m json.tool || true
	@curl -s -X POST http://localhost:8000/packages \
		-H "Content-Type: application/json" \
		-d '{"name": "bert-base", "version": "2.0.0", "metadata": {"readme": "BERT base model"}}' \
		| python -m json.tool || true
	@-kill `cat .api_server.pid` 2>/dev/null
	@rm -f .api_server.pid

list:
	@python src/api_server.py > /dev/null 2>&1 & echo $$! > .api_server.pid
	@sleep 2
	@curl -s http://localhost:8000/packages | python -m json.tool || true
	@-kill `cat .api_server.pid` 2>/dev/null
	@rm -f .api_server.pid

search:
	@python src/api_server.py > /dev/null 2>&1 & echo $$! > .api_server.pid
	@sleep 2
	@echo "Uploading test packages..."
	@curl -s -X POST http://localhost:8000/packages \
		-H "Content-Type: application/json" \
		-d '{"name": "gpt2-model", "version": "1.0.0", "metadata": {"readme": "GPT-2 transformer"}}' > /dev/null
	@curl -s -X POST http://localhost:8000/packages \
		-H "Content-Type: application/json" \
		-d '{"name": "bert-base", "version": "2.0.0", "metadata": {"readme": "BERT model"}}' > /dev/null
	@echo "\nSearching for 'gpt':"
	@curl -s "http://localhost:8000/packages?query=gpt" | python -m json.tool || true
	@-kill `cat .api_server.pid` 2>/dev/null
	@rm -f .api_server.pid

search-regex:
	python src/api_server.py > /dev/null 2>&1 & echo $$! > .api_server.pid
	@sleep 2
	@echo "Uploading test packages..."
	curl -s -X POST http://localhost:8000/packages \
		-H "Content-Type: application/json" \
		-d '{"name": "gpt2-model", "version": "1.0.0", "metadata": {"readme": "GPT-2 transformer"}}' > /dev/null
	curl -s -X POST http://localhost:8000/packages \
		-H "Content-Type: application/json" \
		-d '{"name": "bert-base", "version": "2.0.0", "metadata": {"readme": "BERT model"}}' > /dev/null
	curl -s -X POST http://localhost:8000/packages \
		-H "Content-Type: application/json" \
		-d '{"name": "gpt3-large", "version": "3.0.0", "metadata": {"readme": "GPT-3 large"}}' > /dev/null
	@echo "\nRegex search 'gpt.*2':"
	curl -s "http://localhost:8000/packages?query=gpt.*2&regex=true" | python -m json.tool || true
	@echo "\nRegex search '^gpt[0-9]':"
	curl -s "http://localhost:8000/packages?query=^gpt[0-9]&regex=true" | python -m json.tool || true
	-kill `cat .api_server.pid` 2>/dev/null
	@rm -f .api_server.pid

reset:
	@python src/api_server.py > /dev/null 2>&1 & echo $$! > .api_server.pid
	@sleep 2
	@curl -s -X DELETE http://localhost:8000/reset | python -m json.tool || true
	@-kill `cat .api_server.pid` 2>/dev/null
	@rm -f .api_server.pid

ingest:
	python src/api_server.py > /dev/null 2>&1 & echo $$! > .api_server.pid
	@sleep 2
	curl -s -X POST http://localhost:8000/ingest \
		-H "Content-Type: application/json" \
		-d '{"url": "https://huggingface.co/openai-community/gpt2"}' \
		| python -m json.tool || true
	-kill `cat .api_server.pid` 2>/dev/null
	@rm -f .api_server.pid
