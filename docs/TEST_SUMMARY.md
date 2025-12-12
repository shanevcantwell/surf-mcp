# Test Suite Summary

## Overview

| Category | Files | Tests |
|----------|-------|-------|
| Unit | 0 | 0 |
| Integration | 2 | 14 |
| Other | 5 | 18 |
| **Total** | **7** | **32** |


## `tests\test_fara_integration.py`

- **`test_recorded_google_search_click`**
  - *Test parsing of recorded Fara response for Google search.*
- **`test_recorded_type_action`**
  - *Test parsing of recorded type action.*
- **`test_recorded_scroll_down`**
  - *Test parsing of recorded scroll action.*
- **`test_recorded_multiline_thinking`**
  - *Test parsing when Fara includes extensive chain-of-thought.*

## `tests\test_fara_real.py`

- **`test_nest_asyncio_works`**
  - *Test that nest_asyncio allows nested event loops.*
- **`test_sync_wrapper_pattern`**
  - *Test the sync wrapper pattern used in the harness.*

## `tests\test_harness_integration.py`

- **`test_sync_wrapper_creates_loop`**
  - *SyncNavigatorClient creates event loop.*
- **`test_storage_state_json_roundtrip`**
  - *Storage state survives JSON round-trip.*
- **`test_parse_goto`**
  - *Parse goto command - direct navigation.*
- **`test_parse_goto_auto_https`**
  - *Parse goto without protocol - auto-prepends https://*
- **`test_parse_scroll`**
  - *Parse scroll command - direct scroll.*
- **`test_parse_natural_language_goes_to_act`**
  - *Natural language commands go to Fara via 'act'.*
- **`test_draw_overlay`**
  - *draw_overlay adds marker to image.*
- **`test_draw_overlay_no_coords`**
  - *draw_overlay returns original if no coords.*
- **`test_sync_client_connect_disconnect`**
  - *Test sync client connect/disconnect cycle.*
- **`test_sync_client_filesystem_roundtrip`**
  - *Test sync client with filesystem driver.*

## `tests\test_llm_factory.py`

- **`test_parse_computer_use_left_click`**
  - *Parse Fara's computer_use left_click format.*
- **`test_parse_computer_use_type_with_coords`**
  - *Parse Fara's computer_use type action with coordinates.*
- **`test_parse_playwright_format`**
  - *Parse Fara's playwright tool_call format.*
- **`test_parse_computer_format`**
  - *Parse Fara's computer tool_call format.*
- **`test_parse_scroll_no_coordinates`**
  - *Parse Fara's scroll action (no coordinates needed).*
- **`test_parse_terminate_action`**
  - *Parse Fara's terminate action.*
- **`test_parse_serpico_format`**
  - *Parse Fara's serpico tool_call format.*
- **`test_parse_unknown_format_returns_not_found`**
  - *Unknown tool_call format returns found=False with debug info.*
- **`test_parse_response_with_tool_call_tags`**
  - *Parse response wrapped in <tool_call> tags.*
- **`test_parse_response_with_markdown_json`**
  - *Parse response with markdown code block.*
- **`test_parse_response_with_raw_json`**
  - *Parse raw JSON response.*
- **`test_parse_response_unparseable_returns_not_found`**
  - *Unparseable response returns found=False.*
- **`test_parse_multiple_servers`**
  - *Parses comma-separated server list.*
- **`test_parse_single_server`**
  - *Parses single server.*
- **`test_parse_fallback_when_empty`**
  - *Falls back to default when LMSTUDIO_SERVERS not set.*
- **`test_parse_model_ids`**
  - *Parses comma-separated model IDs.*

## `tests\test_security_controls.py`


## `tests\test_session_manager.py`


## `tests\drivers\test_filesystem.py`
