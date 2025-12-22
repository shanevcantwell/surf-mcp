#!/bin/bash
# Fara Test Harness launcher
# Creates a virtual environment if needed, installs dependencies, and runs Streamlit

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Fara Test Harness ==="

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found"
    exit 1
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

# Install surf-mcp (the MCP server we'll connect to)
if ! command -v surf-mcp &> /dev/null; then
    echo "Installing surf-mcp..."
    pip install -q -e "$SCRIPT_DIR/../.."
fi

echo ""
echo "Starting Streamlit..."
echo "Open http://localhost:8501 in your browser"
echo ""

exec streamlit run app.py "$@"
