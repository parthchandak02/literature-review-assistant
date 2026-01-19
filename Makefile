.PHONY: setup install test clean run

setup:
	@echo "Setting up Research Article Writer..."
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
	@python main.py

clean:
	@echo "Cleaning up..."
	@rm -rf __pycache__ src/**/__pycache__ .venv data/outputs/*.png data/outputs/*.md data/outputs/*.json
	@echo "Clean complete"

test:
	@echo "Running tests..."
	@python -m pytest tests/ || echo "No tests directory found"

lint:
	@echo "Running Ruff linter and formatter..."
	@ruff check --fix src/ main.py
	@ruff format src/ main.py
	@echo "Linting complete!"

help:
	@echo "Available commands:"
	@echo "  make setup    - Create virtual environment"
	@echo "  make install  - Install dependencies"
	@echo "  make run      - Run the workflow"
	@echo "  make clean    - Clean generated files"
	@echo "  make test     - Run tests"
	@echo "  make lint     - Run Ruff linter and formatter"