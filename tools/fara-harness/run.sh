#!/bin/bash
# Fara Test Harness launcher
# Builds Docker image if needed, installs harness deps, and runs Streamlit

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$SCRIPT_DIR"

echo "=== Fara Test Harness ==="

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found"
    exit 1
fi

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "Error: docker not found"
    echo "Install Docker or uncheck 'Use Docker' in the harness to use local install."
    exit 1
fi

# Build surf-mcp Docker image if not present
if ! docker images surf-mcp --format "{{.Repository}}" | grep -q "surf-mcp"; then
    echo "Building surf-mcp Docker image..."
    docker build --target prod -t surf-mcp "$REPO_DIR"
else
    echo "Docker image 'surf-mcp' found."
fi

# Create venv if not in one and .venv doesn't exist
VENV_DIR="$SCRIPT_DIR/.venv"
if [ -z "$VIRTUAL_ENV" ]; then
    if [ ! -d "$VENV_DIR" ]; then
        echo "Creating virtual environment..."
        python3 -m venv "$VENV_DIR"
    fi
    echo "Activating virtual environment..."
    source "$VENV_DIR/bin/activate"
fi

# Install harness dependencies (streamlit, pillow, mcp client)
echo "Checking dependencies..."
if ! python3 -c "import streamlit" 2>/dev/null; then
    echo "Installing harness dependencies..."
    pip install -q -r requirements.txt
fi

echo ""
echo "Starting Streamlit..."
echo "Open http://localhost:8501 in your browser"
echo ""
echo "Note: 'Use Docker' is checked by default - surf-mcp runs in container."
echo "      Uncheck it to use local 'pip install -e ../..' instead."
echo ""

exec streamlit run app.py "$@"
