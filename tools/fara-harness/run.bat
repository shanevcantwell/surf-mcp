@echo off
REM Fara Test Harness launcher for Windows
REM Checks dependencies and runs the Streamlit app

cd /d "%~dp0"

echo === Fara Test Harness ===

REM Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: python not found
    exit /b 1
)

REM Check/install pip dependencies
echo Checking dependencies...
python -c "import streamlit" 2>nul
if %errorlevel% neq 0 (
    echo Installing harness dependencies...
    pip install -r requirements.txt
)

python -c "import mcp" 2>nul
if %errorlevel% neq 0 (
    echo Installing MCP SDK...
    pip install mcp
)

python -c "import playwright" 2>nul
if %errorlevel% neq 0 (
    echo Installing Playwright...
    pip install playwright
)

REM Check Playwright chromium
echo Checking Playwright Chromium...
python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(headless=True); b.close(); p.stop()" 2>nul
if %errorlevel% neq 0 (
    echo Installing Playwright Chromium browser...
    playwright install chromium
)

REM Check navigator-mcp
where navigator-mcp >nul 2>&1
if %errorlevel% neq 0 (
    echo Warning: navigator-mcp not in PATH
    echo Install with: pip install -e /path/to/navigation-mcp
)

echo.
echo Starting Streamlit...
echo Open http://localhost:8501 in your browser
echo.

streamlit run app.py %*
