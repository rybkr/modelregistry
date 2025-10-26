.PHONY: test clean

test:
	@python3 -m pytest --cov=src --cov-report=html:test/_htmlcov
	@echo "Open test/_htmlcov/index.py in a browser for full coverage report."

clean:
	@find . -type d -name "__pycache__" -exec rm -r {} +
