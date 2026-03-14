"""Domain utilities.

Provides common utilities used across domain services:
- Text truncation and formatting
- Type guards for runtime type checking
- JSON parsing utilities
- Diff utilities
"""

from app.domain.utils.llm_compat import is_native_openai
from app.domain.utils.text import (
    TextTruncator,
    TruncationResult,
    TruncationStyle,
    truncate,
    truncate_output,
)
from app.domain.utils.type_guards import (
    ensure_dict,
    ensure_float,
    ensure_int,
    ensure_list,
    ensure_str,
    get_dict_value,
    get_nested_value,
    is_dict,
    is_dict_with_key,
    is_dict_with_keys,
    is_float,
    is_int,
    is_list,
    is_list_of_dicts,
    is_list_of_strings,
    is_non_empty_string,
    is_numeric,
    is_str,
    is_tool_result_dict,
)

__all__ = [
    "TextTruncator",
    "TruncationResult",
    "TruncationStyle",
    "ensure_dict",
    "ensure_float",
    "ensure_int",
    "ensure_list",
    "ensure_str",
    "get_dict_value",
    "get_nested_value",
    "is_dict",
    "is_dict_with_key",
    "is_dict_with_keys",
    "is_float",
    "is_int",
    "is_list",
    "is_list_of_dicts",
    "is_list_of_strings",
    "is_non_empty_string",
    "is_numeric",
    "is_str",
    "is_native_openai",
    "is_tool_result_dict",
    "truncate",
    "truncate_output",
]
