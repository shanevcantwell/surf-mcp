"""
Pytest configuration and fixtures.
"""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # Create some test files and directories
        (workspace / "file1.txt").write_text("Hello, World!")
        (workspace / "file2.py").write_text("print('Hello')")
        (workspace / "subdir").mkdir()
        (workspace / "subdir" / "nested.txt").write_text("Nested content")

        yield workspace


@pytest.fixture
def mock_screenshot():
    """Create a minimal valid PNG for testing."""
    # Minimal 1x1 white PNG
    import base64

    # This is a valid 1x1 white PNG
    png_data = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
        b"\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe"
        b"\xa7V\xbd\xfa\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return base64.b64encode(png_data).decode("utf-8")
