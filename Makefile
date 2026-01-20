.PHONY: setup install test clean run

setup:
	@echo "Setting up Literature Review Assistant..."
	@if ! command -v uv &> /dev/null; then \
		echo "Installing uv..."; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
	fi
	@uv venv
	@echo "Virtual environment created. Activate with: source .venv/bin/activate"

install:
	@echo "Installing dependencies..."
	@uv pip install -e .
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env file. Please edit it with your API keys."; \
	fi

run:
	@if [ -d .venv ]; then .venv/bin/python main.py; else python3 main.py; fi

clean:
	@echo "Cleaning up..."
	@rm -rf __pycache__ src/**/__pycache__ .venv data/outputs/*.png data/outputs/*.md data/outputs/*.json
	@echo "Clean complete"

test:
	@echo "Running tests..."
	@if [ -d .venv ]; then .venv/bin/python -m pytest tests/ || echo "No tests directory found"; else python3 -m pytest tests/ || echo "No tests directory found"; fi

test-prisma:
	@echo "Running PRISMA 2020 tests..."
	@if [ -d .venv ]; then .venv/bin/python scripts/run_prisma_tests.py; else python3 scripts/run_prisma_tests.py; fi

test-all:
	@echo "Running all tests..."
	@if [ -d .venv ]; then .venv/bin/python -m pytest tests/ -v || echo "No tests directory found"; else python3 -m pytest tests/ -v || echo "No tests directory found"; fi

test-report:
	@echo "Generating test report..."
	@if [ -d .venv ]; then .venv/bin/python scripts/run_prisma_tests.py; else python3 scripts/run_prisma_tests.py; fi
	@echo "Test report saved to data/test_outputs/"

test-status:
	@echo "Checking test status..."
	@if [ -d .venv ]; then .venv/bin/python scripts/check_test_status.py; else python3 scripts/check_test_status.py; fi

lint:
	@echo "Running Ruff linter and formatter..."
	@ruff check --fix src/ main.py
	@ruff format src/ main.py
	@echo "Linting complete!"

help:
	@echo "Available commands:"
	@echo "  make setup       - Create virtual environment"
	@echo "  make install     - Install dependencies"
	@echo "  make run         - Run the workflow"
	@echo "  make clean       - Clean generated files"
	@echo "  make test        - Run all tests"
	@echo "  make test-prisma - Run PRISMA 2020 tests with reports"
	@echo "  make test-all    - Run all tests (verbose)"
	@echo "  make test-report - Generate test report"
	@echo "  make test-status - Check test status (quick)"
	@echo "  make lint        - Run Ruff linter and formatter"