.PHONY: install dev test lint format clean

# Install for production
install:
	pip install -e .

# Install with dev dependencies
dev:
	pip install -e ".[dev]"

# Run tests
test:
	pytest tests/ -v

# Run tests with coverage
coverage:
	pytest tests/ -v --cov=src/kage --cov-report=html

# Run linter
lint:
	ruff check src/ tests/
	mypy src/kage/

# Format code
format:
	ruff format src/ tests/
	ruff check --fix src/ tests/

# Clean build artifacts
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf src/*.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# Build package
build: clean
	python -m build

# Run the CLI
run:
	python -m kage
