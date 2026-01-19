#!/bin/bash
# Setup script for Literature Review Assistant

set -e

echo "Literature Review Assistant - Setup Script"
echo "======================================"

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

echo "Creating virtual environment..."
uv venv

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Installing dependencies..."
uv pip install -e .

echo "Setting up environment file..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env file from .env.example"
    echo "Please edit .env and add your API keys"
else
    echo ".env file already exists"
fi

echo ""
echo "Setup complete!"
echo "Next steps:"
echo "1. Edit .env and add your API keys"
echo "2. Run: python main.py"
