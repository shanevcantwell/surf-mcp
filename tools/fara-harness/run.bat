@echo off
REM Fara Test Harness launcher for Windows
REM Builds Docker image if needed, installs harness deps, and runs Streamlit

cd /d "%~dp0"
set REPO_DIR=%~dp0..\..

echo === Fara Test Harness ===

REM Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: python not found
    exit /b 1
)

REM Check Docker
where docker >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: docker not found
    echo Install Docker or uncheck 'Use Docker' in the harness to use local install.
    exit /b 1
)

REM Build surf-mcp Docker image if not present
docker images surf-mcp --format "{{.Repository}}" | findstr /c:"surf-mcp" >nul 2>&1
if %errorlevel% neq 0 (
    echo Building surf-mcp Docker image...
    docker build --target prod -t surf-mcp "%REPO_DIR%"
) else (
    echo Docker image 'surf-mcp' found.
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

echo.
echo Starting Streamlit...
echo Open http://localhost:8501 in your browser
echo.
echo Note: 'Use Docker' is checked by default - surf-mcp runs in container.
echo       Uncheck it to use local 'pip install -e ..\..' instead.
echo.

streamlit run app.py %*
