"""
Tests for FileSystemDriver.
"""

import pytest
from pathlib import Path

from navigator_mcp.drivers.filesystem import FileSystemDriver


@pytest.mark.asyncio
async def test_init(temp_workspace):
    """Test driver initialization."""
    driver = FileSystemDriver(root=str(temp_workspace), sandbox=True)

    assert driver.root == temp_workspace
    assert driver.cwd == temp_workspace
    assert driver.sandbox is True
    assert driver.history == []


@pytest.mark.asyncio
async def test_goto(temp_workspace):
    """Test navigation to subdirectory."""
    driver = FileSystemDriver(root=str(temp_workspace), sandbox=True)

    result = await driver.goto("subdir")

    assert result.success is True
    assert result.location == str(temp_workspace / "subdir")
    assert len(driver.history) == 1


@pytest.mark.asyncio
async def test_goto_sandbox_escape(temp_workspace):
    """Test that sandbox prevents escaping root."""
    driver = FileSystemDriver(root=str(temp_workspace), sandbox=True)

    result = await driver.goto("..")

    assert result.success is False
    assert "sandbox" in result.error.lower()
    assert driver.cwd == temp_workspace  # Unchanged


@pytest.mark.asyncio
async def test_list(temp_workspace):
    """Test directory listing."""
    driver = FileSystemDriver(root=str(temp_workspace), sandbox=True)

    entries = await driver.list()

    names = [e["name"] for e in entries]
    assert "file1.txt" in names
    assert "file2.py" in names
    assert "subdir" in names

    # Directories should come first
    assert entries[0]["type"] == "directory"


@pytest.mark.asyncio
async def test_read(temp_workspace):
    """Test file reading."""
    driver = FileSystemDriver(root=str(temp_workspace), sandbox=True)

    content = await driver.read("file1.txt")

    assert content == "Hello, World!"
    assert str(temp_workspace / "file1.txt") in driver.files_read


@pytest.mark.asyncio
async def test_write(temp_workspace):
    """Test file writing."""
    driver = FileSystemDriver(root=str(temp_workspace), sandbox=True)

    result = await driver.write("new_file.txt", "New content")

    assert result.success is True
    assert (temp_workspace / "new_file.txt").read_text() == "New content"
    assert str(temp_workspace / "new_file.txt") in driver.files_written


@pytest.mark.asyncio
async def test_write_creates_directories(temp_workspace):
    """Test that write creates parent directories."""
    driver = FileSystemDriver(root=str(temp_workspace), sandbox=True)

    result = await driver.write("new_dir/nested/file.txt", "Content")

    assert result.success is True
    assert (temp_workspace / "new_dir" / "nested" / "file.txt").exists()


@pytest.mark.asyncio
async def test_delete_file(temp_workspace):
    """Test file deletion."""
    driver = FileSystemDriver(root=str(temp_workspace), sandbox=True)

    result = await driver.delete("file1.txt")

    assert result.success is True
    assert not (temp_workspace / "file1.txt").exists()


@pytest.mark.asyncio
async def test_copy(temp_workspace):
    """Test file copying."""
    driver = FileSystemDriver(root=str(temp_workspace), sandbox=True)

    result = await driver.copy("file1.txt", "file1_copy.txt")

    assert result.success is True
    assert (temp_workspace / "file1.txt").exists()  # Original still exists
    assert (temp_workspace / "file1_copy.txt").read_text() == "Hello, World!"


@pytest.mark.asyncio
async def test_move(temp_workspace):
    """Test file moving."""
    driver = FileSystemDriver(root=str(temp_workspace), sandbox=True)

    result = await driver.move("file1.txt", "moved.txt")

    assert result.success is True
    assert not (temp_workspace / "file1.txt").exists()
    assert (temp_workspace / "moved.txt").read_text() == "Hello, World!"


@pytest.mark.asyncio
async def test_find(temp_workspace):
    """Test file search."""
    driver = FileSystemDriver(root=str(temp_workspace), sandbox=True)

    matches = await driver.find("*.txt")

    assert "file1.txt" in matches
    assert "subdir/nested.txt" in matches or "subdir\\nested.txt" in matches


@pytest.mark.asyncio
async def test_back_forward(temp_workspace):
    """Test history navigation."""
    driver = FileSystemDriver(root=str(temp_workspace), sandbox=True)

    # Navigate
    await driver.goto("subdir")
    assert driver.cwd == temp_workspace / "subdir"

    # Go back
    result = await driver.back()
    assert result.success is True
    assert driver.cwd == temp_workspace

    # Go forward
    result = await driver.forward()
    assert result.success is True
    assert driver.cwd == temp_workspace / "subdir"


@pytest.mark.asyncio
async def test_snapshot(temp_workspace):
    """Test snapshot returns JSON."""
    driver = FileSystemDriver(root=str(temp_workspace), sandbox=True)

    snapshot = await driver.snapshot()

    import json
    data = json.loads(snapshot)

    assert "cwd" in data
    assert "root" in data
    assert "entries" in data
