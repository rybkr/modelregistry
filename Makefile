.PHONY: test clean install serve test-api health upload list reset

test:
	@python3 -m pytest --cov=src --cov-report=html:test/_htmlcov
	@echo "Open test/_htmlcov/index.py in a browser for full coverage report."

clean:
	@find . -type d -name "__pycache__" -exec rm -r {} +
	@rm -f .api_server.pid

install:
	@pip install -e ".[dev]"

serve:
	@python src/api_server.py

test-api:
	@python src/api_server.py > /dev/null 2>&1 & echo $$! > .api_server.pid
	@sleep 0.5
	@pytest test/test_api_crud.py -v || true
	@-kill `cat .api_server.pid` 2>/dev/null
	@rm -f .api_server.pid

health:
	@python src/api_server.py > /dev/null 2>&1 & echo $$! > .api_server.pid
	@sleep 0.5
	@curl -s http://localhost:8000/health | python -m json.tool || true
	@-kill `cat .api_server.pid` 2>/dev/null
	@rm -f .api_server.pid

upload:
	@python src/api_server.py > /dev/null 2>&1 & echo $$! > .api_server.pid
	@sleep 0.5
	@curl -s -X POST http://localhost:8000/packages \
		-H "Content-Type: application/json" \
		-d '{"name": "test-model", "version": "1.0.0", "metadata": {"url": "https://huggingface.co/gpt2"}}' \
		| python -m json.tool || true
	@-kill `cat .api_server.pid` 2>/dev/null
	@rm -f .api_server.pid

list:
	@python src/api_server.py > /dev/null 2>&1 & echo $$! > .api_server.pid
	@sleep 0.5
	@curl -s http://localhost:8000/packages | python -m json.tool || true
	@-kill `cat .api_server.pid` 2>/dev/null
	@rm -f .api_server.pid

reset:
	@python src/api_server.py > /dev/null 2>&1 & echo $$! > .api_server.pid
	@sleep 0.5
	@curl -s -X DELETE http://localhost:8000/reset | python -m json.tool || true
	@-kill `cat .api_server.pid` 2>/dev/null
	@rm -f .api_server.pid
