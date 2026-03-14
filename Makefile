.PHONY: install dev test lint format clean setup uninstall update

# Full installation (creates venv, installs, adds to PATH)
setup:
ifeq ($(OS),Windows_NT)
	powershell -ExecutionPolicy Bypass -File scripts/install.ps1
else
	bash scripts/install.sh
endif

# Full installation with dev dependencies
setup-dev:
ifeq ($(OS),Windows_NT)
	powershell -ExecutionPolicy Bypass -File scripts/install.ps1 -Dev
else
	bash scripts/install.sh --dev
endif

# Quick install (no venv, assumes pip available)
install:
	pip install -e .

# Install with dev dependencies
dev:
	pip install -e ".[dev]"

# Uninstall kage
uninstall:
ifeq ($(OS),Windows_NT)
	powershell -ExecutionPolicy Bypass -File scripts/uninstall.ps1 -Yes
else
	bash scripts/uninstall.sh --yes
endif

# Update kage
update:
ifeq ($(OS),Windows_NT)
	powershell -ExecutionPolicy Bypass -File scripts/update.ps1
else
	bash scripts/update.sh
endif

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
