"""Type guard utilities for runtime type checking.

Provides TypeGuard functions for safer type narrowing and
utility functions for type coercion with defaults.
"""

from typing import Any, TypeGuard


def is_dict(value: Any) -> TypeGuard[dict[str, Any]]:
    """Check if value is a dictionary.

    Args:
        value: Value to check

    Returns:
        True if value is a dict
    """
    return isinstance(value, dict)


def is_list(value: Any) -> TypeGuard[list[Any]]:
    """Check if value is a list.

    Args:
        value: Value to check

    Returns:
        True if value is a list
    """
    return isinstance(value, list)


def is_str(value: Any) -> TypeGuard[str]:
    """Check if value is a string.

    Args:
        value: Value to check

    Returns:
        True if value is a str
    """
    return isinstance(value, str)


def is_int(value: Any) -> TypeGuard[int]:
    """Check if value is an integer (not bool).

    Args:
        value: Value to check

    Returns:
        True if value is an int (not bool)
    """
    return isinstance(value, int) and not isinstance(value, bool)


def is_float(value: Any) -> TypeGuard[float]:
    """Check if value is a float.

    Args:
        value: Value to check

    Returns:
        True if value is a float
    """
    return isinstance(value, float)


def is_numeric(value: Any) -> TypeGuard[int | float]:
    """Check if value is numeric (int or float, not bool).

    Args:
        value: Value to check

    Returns:
        True if value is numeric
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_dict_with_key(value: Any, key: str) -> TypeGuard[dict[str, Any]]:
    """Check if value is a dict containing a specific key.

    Args:
        value: Value to check
        key: Key that must be present

    Returns:
        True if value is a dict with the specified key
    """
    return isinstance(value, dict) and key in value


def is_dict_with_keys(value: Any, keys: list[str]) -> TypeGuard[dict[str, Any]]:
    """Check if value is a dict containing all specified keys.

    Args:
        value: Value to check
        keys: Keys that must all be present

    Returns:
        True if value is a dict with all specified keys
    """
    return isinstance(value, dict) and all(k in value for k in keys)


def is_list_of_dicts(value: Any) -> TypeGuard[list[dict[str, Any]]]:
    """Check if value is a list of dictionaries.

    Args:
        value: Value to check

    Returns:
        True if value is a list where all items are dicts
    """
    return isinstance(value, list) and all(isinstance(item, dict) for item in value)


def is_list_of_strings(value: Any) -> TypeGuard[list[str]]:
    """Check if value is a list of strings.

    Args:
        value: Value to check

    Returns:
        True if value is a list where all items are strings
    """
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def is_non_empty_string(value: Any) -> TypeGuard[str]:
    """Check if value is a non-empty string.

    Args:
        value: Value to check

    Returns:
        True if value is a non-empty str
    """
    return isinstance(value, str) and len(value) > 0


def is_tool_result_dict(value: Any) -> TypeGuard[dict[str, Any]]:
    """Check if value looks like a tool result dictionary.

    Tool results have at minimum a 'success' boolean field.

    Args:
        value: Value to check

    Returns:
        True if value appears to be a tool result dict
    """
    return isinstance(value, dict) and "success" in value and isinstance(value.get("success"), bool)


# ===== Coercion Functions =====


def ensure_dict(value: Any, default: dict[str, Any] | None = None) -> dict[str, Any]:
    """Ensure value is a dict, returning default if not.

    Args:
        value: Value to coerce
        default: Default value if not a dict (defaults to empty dict)

    Returns:
        The value if it's a dict, otherwise the default
    """
    if isinstance(value, dict):
        return value
    return default if default is not None else {}


def ensure_list(value: Any, default: list[Any] | None = None) -> list[Any]:
    """Ensure value is a list, returning default if not.

    Args:
        value: Value to coerce
        default: Default value if not a list (defaults to empty list)

    Returns:
        The value if it's a list, otherwise the default
    """
    if isinstance(value, list):
        return value
    return default if default is not None else []


def ensure_str(value: Any, default: str = "") -> str:
    """Ensure value is a string, returning default if not.

    Args:
        value: Value to coerce
        default: Default value if not a str

    Returns:
        The value if it's a str, otherwise the default
    """
    if isinstance(value, str):
        return value
    return default


def ensure_int(value: Any, default: int = 0) -> int:
    """Ensure value is an int, returning default if not.

    Args:
        value: Value to coerce
        default: Default value if not an int

    Returns:
        The value if it's an int, otherwise the default
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return default


def ensure_float(value: Any, default: float = 0.0) -> float:
    """Ensure value is a float, returning default if not.

    Args:
        value: Value to coerce
        default: Default value if not a float

    Returns:
        The value if it's a float, otherwise the default
    """
    if isinstance(value, float):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    return default


def get_dict_value(data: dict[str, Any], key: str, default: Any = None) -> Any:
    """Safely get value from dict with type checking.

    Args:
        data: Dictionary to get value from
        key: Key to look up
        default: Default if key not found

    Returns:
        Value at key or default
    """
    if not isinstance(data, dict):
        return default
    return data.get(key, default)


def get_nested_value(data: dict[str, Any], keys: list[str], default: Any = None) -> Any:
    """Safely get nested value from dict.

    Args:
        data: Dictionary to traverse
        keys: List of keys for nested access
        default: Default if path not found

    Returns:
        Value at nested path or default

    Example:
        get_nested_value({"a": {"b": 1}}, ["a", "b"]) -> 1
    """
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current
