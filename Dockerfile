FROM python:3.11-slim

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Install package
RUN pip install --no-cache-dir .

# Install Playwright browsers
RUN playwright install chromium
RUN playwright install-deps chromium

# Create workspace directory
RUN mkdir -p /workspace

# Set environment variables
ENV NAVIGATOR_FS_SANDBOX=true
ENV NAVIGATOR_BROWSER_HEADLESS=true

# Expose stdio for MCP
CMD ["navigator-mcp"]
