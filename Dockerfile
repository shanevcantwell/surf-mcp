# Multi-stage Dockerfile for surf-mcp
# Usage:
#   Production: docker build -t surf-mcp .
#   Development: docker build --target dev -t surf-mcp:dev .

FROM python:3.11-slim AS base

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ src/

# ==============================================================================
# Production target (default)
# ==============================================================================
FROM base AS prod

# Install package (production dependencies only)
RUN pip install --no-cache-dir .

# Install Playwright browsers
RUN playwright install chromium
RUN playwright install-deps chromium

# Set environment variables
ENV SURF_BROWSER_HEADLESS=true

# Expose stdio for MCP
CMD ["surf-mcp"]

# ==============================================================================
# Development target
# ==============================================================================
FROM base AS dev

# Copy test files and harness tools
COPY tests/ tests/
COPY tools/ tools/

# Install package with dev dependencies
RUN pip install --no-cache-dir ".[dev]"

# Install Playwright browsers
RUN playwright install chromium
RUN playwright install-deps chromium

# Set environment variables
ENV SURF_BROWSER_HEADLESS=true

# Default to running tests
CMD ["pytest", "-v"]
