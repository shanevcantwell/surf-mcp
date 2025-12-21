#!/bin/bash
# Fara Test Harness launcher
# Checks dependencies and runs the Streamlit app

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Fara Test Harness ==="

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found"
    exit 1
fi

# Check if in virtualenv, warn if not
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Warning: Not in a virtual environment"
fi

# Check/install pip dependencies
echo "Checking dependencies..."
if ! python3 -c "import streamlit" 2>/dev/null; then
    echo "Installing harness dependencies..."
    pip install -r requirements.txt
fi

if ! python3 -c "import mcp" 2>/dev/null; then
    echo "Installing MCP SDK..."
    pip install mcp
fi

# Check Playwright package
if ! python3 -c "import playwright" 2>/dev/null; then
    echo "Installing Playwright..."
    pip install playwright
fi

# Check Playwright chromium browser binary
CHROMIUM_CHECK=$(python3 -c "
from playwright.sync_api import sync_playwright
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        browser.close()
    print('ok')
except Exception as e:
    if 'Executable' in str(e):
        print('missing')
    else:
        print('error: ' + str(e))
" 2>&1)

if [ "$CHROMIUM_CHECK" = "missing" ]; then
    echo "Installing Playwright Chromium browser..."
    playwright install chromium
elif [ "$CHROMIUM_CHECK" != "ok" ]; then
    echo "Warning: Playwright check returned: $CHROMIUM_CHECK"
fi

# Check surf-mcp is available
if ! command -v surf-mcp &> /dev/null; then
    echo "Warning: surf-mcp not in PATH"
    echo "Install with: pip install -e /path/to/surf-mcp"
fi

echo ""
echo "Starting Streamlit..."
echo "Open http://localhost:8501 in your browser"
echo ""

exec streamlit run app.py "$@"
