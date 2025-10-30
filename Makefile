.PHONY: test clean install serve test-api health upload list reset ingest

test:
	@python3 -m pytest --cov=src --cov-report=html:test/_htmlcov
	@echo "Open test/_htmlcov/index.py in a browser for full coverage report."

clean:
	@find . -type d -name "__pycache__" -exec rm -r {} +
	@rm -f .api_server.pid

install:
	@pip install -e ".[dev]"

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
		-d '{"name": "test-model", "version": "1.0.0", "metadata": {"url": "https://huggingface.co/openai-community/gpt2"}}' \
		| python -m json.tool || true
	@-kill `cat .api_server.pid` 2>/dev/null
	@rm -f .api_server.pid

list:
	@python src/api_server.py > /dev/null 2>&1 & echo $$! > .api_server.pid
	@sleep 2
	@curl -s http://localhost:8000/packages | python -m json.tool || true
	@-kill `cat .api_server.pid` 2>/dev/null
	@rm -f .api_server.pid

reset:
	@python src/api_server.py > /dev/null 2>&1 & echo $$! > .api_server.pid
	@sleep 2
	@curl -s -X DELETE http://localhost:8000/reset | python -m json.tool || true
	@-kill `cat .api_server.pid` 2>/dev/null
	@rm -f .api_server.pid

ingest:
	@python src/api_server.py > /dev/null 2>&1 & echo $$! > .api_server.pid
	@sleep 2
	@curl -s -X POST http://localhost:8000/ingest \
		-H "Content-Type: application/json" \
		-d '{"url": "https://huggingface.co/openai-community/gpt2"}' \
		| python -m json.tool || true
	@-kill `cat .api_server.pid` 2>/dev/null
	@rm -f .api_server.pid
