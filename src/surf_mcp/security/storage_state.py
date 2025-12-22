"""
Storage state validation for surf-mcp.

Validates Playwright storage_state format to prevent crashes
from malformed input and provides defense-in-depth sanitization.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Maximum sizes to prevent DoS
MAX_COOKIES = 1000
MAX_ORIGINS = 100
MAX_LOCALSTORAGE_ITEMS = 1000
MAX_STRING_LENGTH = 100_000  # 100KB per string value


def validate_storage_state(
    state: Any,
) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    Validate and sanitize Playwright storage_state.

    Args:
        state: Input to validate (should be dict with cookies/origins)

    Returns:
        Tuple of (is_valid, error_message, sanitized_state)
        - If valid: (True, None, sanitized_dict)
        - If invalid: (False, error_string, None)
    """
    if state is None:
        return True, None, None

    if not isinstance(state, dict):
        return False, f"storage_state must be dict, got {type(state).__name__}", None

    sanitized: Dict[str, Any] = {}

    # Validate cookies
    if "cookies" in state:
        valid, error, cookies = _validate_cookies(state["cookies"])
        if not valid:
            return False, error, None
        sanitized["cookies"] = cookies
    else:
        sanitized["cookies"] = []

    # Validate origins (localStorage)
    if "origins" in state:
        valid, error, origins = _validate_origins(state["origins"])
        if not valid:
            return False, error, None
        sanitized["origins"] = origins
    else:
        sanitized["origins"] = []

    return True, None, sanitized


def _validate_cookies(
    cookies: Any,
) -> Tuple[bool, Optional[str], Optional[List[Dict[str, Any]]]]:
    """Validate cookies array."""
    if not isinstance(cookies, list):
        return False, f"cookies must be list, got {type(cookies).__name__}", None

    if len(cookies) > MAX_COOKIES:
        return False, f"too many cookies ({len(cookies)} > {MAX_COOKIES})", None

    validated = []
    for i, cookie in enumerate(cookies):
        if not isinstance(cookie, dict):
            return False, f"cookie[{i}] must be dict", None

        # Required fields
        for field in ("name", "value", "domain"):
            if field not in cookie:
                return False, f"cookie[{i}] missing required field: {field}", None
            if not isinstance(cookie[field], str):
                return False, f"cookie[{i}].{field} must be string", None
            if len(cookie[field]) > MAX_STRING_LENGTH:
                return False, f"cookie[{i}].{field} exceeds max length", None

        # Build validated cookie with known fields only
        valid_cookie = {
            "name": cookie["name"],
            "value": cookie["value"],
            "domain": cookie["domain"],
        }

        # Optional string fields
        for field in ("path", "sameSite"):
            if field in cookie:
                if isinstance(cookie[field], str):
                    valid_cookie[field] = cookie[field]

        # Optional numeric fields
        for field in ("expires",):
            if field in cookie:
                if isinstance(cookie[field], (int, float)):
                    valid_cookie[field] = cookie[field]

        # Optional boolean fields
        for field in ("httpOnly", "secure"):
            if field in cookie:
                if isinstance(cookie[field], bool):
                    valid_cookie[field] = cookie[field]

        validated.append(valid_cookie)

    return True, None, validated


def _validate_origins(
    origins: Any,
) -> Tuple[bool, Optional[str], Optional[List[Dict[str, Any]]]]:
    """Validate origins array (localStorage)."""
    if not isinstance(origins, list):
        return False, f"origins must be list, got {type(origins).__name__}", None

    if len(origins) > MAX_ORIGINS:
        return False, f"too many origins ({len(origins)} > {MAX_ORIGINS})", None

    validated = []
    for i, origin in enumerate(origins):
        if not isinstance(origin, dict):
            return False, f"origin[{i}] must be dict", None

        if "origin" not in origin:
            return False, f"origin[{i}] missing required field: origin", None
        if not isinstance(origin["origin"], str):
            return False, f"origin[{i}].origin must be string", None

        valid_origin: Dict[str, Any] = {"origin": origin["origin"]}

        # Validate localStorage
        if "localStorage" in origin:
            ls = origin["localStorage"]
            if not isinstance(ls, list):
                return False, f"origin[{i}].localStorage must be list", None
            if len(ls) > MAX_LOCALSTORAGE_ITEMS:
                return (
                    False,
                    f"origin[{i}].localStorage too many items ({len(ls)})",
                    None,
                )

            valid_ls = []
            for j, item in enumerate(ls):
                if not isinstance(item, dict):
                    return False, f"origin[{i}].localStorage[{j}] must be dict", None
                if "name" not in item or "value" not in item:
                    return (
                        False,
                        f"origin[{i}].localStorage[{j}] missing name/value",
                        None,
                    )
                if not isinstance(item["name"], str) or not isinstance(
                    item["value"], str
                ):
                    return (
                        False,
                        f"origin[{i}].localStorage[{j}] name/value must be strings",
                        None,
                    )
                if (
                    len(item["name"]) > MAX_STRING_LENGTH
                    or len(item["value"]) > MAX_STRING_LENGTH
                ):
                    return (
                        False,
                        f"origin[{i}].localStorage[{j}] exceeds max length",
                        None,
                    )
                valid_ls.append({"name": item["name"], "value": item["value"]})

            valid_origin["localStorage"] = valid_ls
        else:
            valid_origin["localStorage"] = []

        validated.append(valid_origin)

    return True, None, validated
