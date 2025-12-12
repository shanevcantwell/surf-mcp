"""
JSON parsing utilities for LLM response handling.

Consolidates common JSON extraction patterns from various LLM response formats:
- Markdown code blocks (```json ... ```)
- XML-style tool_call tags (<tool_call>...</tool_call>)
- Raw JSON in text
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract JSON from various text formats.

    Tries in order:
    1. Markdown code blocks (```json {...} ```)
    2. XML-style tool_call tags (<tool_call>{...}</tool_call>)
    3. Raw JSON object in text

    Args:
        text: Text potentially containing JSON

    Returns:
        Parsed JSON dict if found and valid, None otherwise
    """
    # Try markdown code block first
    result = extract_json_from_markdown(text)
    if result is not None:
        return result

    # Try tool_call XML tags
    result = extract_json_from_tool_call_tags(text)
    if result is not None:
        return result

    # Try raw JSON
    return extract_raw_json(text)


def extract_json_from_markdown(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract JSON from markdown code blocks.

    Handles:
    - ```json {...} ```
    - ``` {...} ```

    Args:
        text: Text potentially containing markdown code block

    Returns:
        Parsed JSON dict if found and valid, None otherwise
    """
    match = re.search(r"```(?:json)?\s*({.*?})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            logger.debug(f"Markdown JSON parse failed: {match.group(1)[:100]}")
    return None


def extract_json_from_tool_call_tags(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract JSON from XML-style tool_call tags.

    Handles: <tool_call>{...}</tool_call>

    Args:
        text: Text potentially containing tool_call tags

    Returns:
        Parsed JSON dict if found and valid, None otherwise
    """
    match = re.search(r"<tool_call>\s*({.*?})\s*</tool_call>", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            logger.debug(f"Tool call JSON parse failed: {match.group(1)[:100]}")
    return None


def extract_raw_json(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract raw JSON object from text.

    Finds the first { and last } and attempts to parse.

    Args:
        text: Text potentially containing JSON object

    Returns:
        Parsed JSON dict if found and valid, None otherwise
    """
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            logger.debug(f"Raw JSON parse failed: {text[start:min(start+100, end+1)]}")
    return None


def safe_json_loads(text: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Safely parse JSON with a default fallback.

    Args:
        text: JSON string to parse
        default: Default value if parsing fails (default: empty dict)

    Returns:
        Parsed JSON or default value
    """
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
        return default if default is not None else {}
    except json.JSONDecodeError:
        return default if default is not None else {}
