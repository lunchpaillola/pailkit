"""
Deep Merge Utility - PailKit API

Recursively merges nested dictionaries, preserving values from both dictionaries.
"""

from typing import Any


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively merge two dictionaries.

    Merges nested dictionaries at every level, allowing profiles to override
    specific nested keys without losing other values.

    Args:
        base: The base dictionary to start with
        override: Dictionary containing values to override

    Returns:
        A new dictionary with merged values
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value

    return result
