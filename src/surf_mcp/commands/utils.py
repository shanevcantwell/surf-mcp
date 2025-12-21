"""
Shared utilities for MCP command handlers.

Consolidates common patterns like driver retrieval and input validation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple, Type

if TYPE_CHECKING:
    from ..drivers.base import NavigatorDriver
    from ..drivers.browser import BrowserDriver
    from ..drivers.filesystem import FileSystemDriver
    from ..session_manager import SessionManager


async def get_driver(
    manager: SessionManager,
    args: Dict[str, Any],
    expected_type: Optional[Type[NavigatorDriver]] = None,
) -> Tuple[Optional[NavigatorDriver], Optional[Dict[str, str]]]:
    """
    Get driver from session with validation.

    Args:
        manager: SessionManager instance
        args: Command arguments containing session_id and driver
        expected_type: Optional type check (BrowserDriver, FileSystemDriver)

    Returns:
        Tuple of (driver, error_dict). If successful, error_dict is None.
        If failed, driver is None and error_dict contains error message.
    """
    session_id = args.get("session_id")
    driver_alias = args.get("driver")

    if not session_id:
        return None, {"error": "session_id required"}

    session = await manager.get_session(str(session_id))
    if not session:
        return None, {"error": f"Session not found: {session_id}"}

    if not driver_alias:
        return None, {"error": "driver required"}

    driver = session.get_driver(str(driver_alias))
    if not driver:
        return None, {"error": f"Driver not found: {driver_alias}"}

    if expected_type and not isinstance(driver, expected_type):
        return None, {
            "error": f"Driver {driver_alias} is not a {expected_type.__name__}"
        }

    return driver, None


async def get_browser_driver(
    manager: SessionManager,
    args: Dict[str, Any],
) -> Tuple[Optional[BrowserDriver], Optional[Dict[str, str]]]:
    """Get browser driver with type validation."""
    from ..drivers.browser import BrowserDriver

    driver, error = await get_driver(manager, args, BrowserDriver)
    if error:
        return None, error
    # Type narrowing for mypy
    assert isinstance(driver, BrowserDriver)
    return driver, None


async def get_filesystem_driver(
    manager: SessionManager,
    args: Dict[str, Any],
) -> Tuple[Optional[FileSystemDriver], Optional[Dict[str, str]]]:
    """Get filesystem driver with type validation."""
    from ..drivers.filesystem import FileSystemDriver

    driver, error = await get_driver(manager, args, FileSystemDriver)
    if error:
        return None, error
    # Type narrowing for mypy
    assert isinstance(driver, FileSystemDriver)
    return driver, None


def validate_required(
    args: Dict[str, Any], *fields: str
) -> Optional[Dict[str, str]]:
    """
    Validate that required fields are present in args.

    Args:
        args: Command arguments
        *fields: Field names that must be present and non-empty

    Returns:
        Error dict if validation fails, None if all fields present
    """
    for field in fields:
        value = args.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            return {"error": f"{field} required"}
    return None
