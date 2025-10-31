"""
Config Schema - PailKit API

Defines the base configuration schema for room creation.
This is a provider-agnostic configuration that represents user intent
rather than provider-specific implementation details.
"""

from typing import Any

BASE_CONFIG = {
    "media": {"video": True, "audio": True, "screenshare_capable": True},
    "capabilities": {
        "chat": True,
        "recording": False,
        "transcription": False,
        "live_captions": False,
        "rtmp_streaming": False,  # For live streaming to external platforms
        "breakout_rooms": False,
    },
    "interaction": {
        "prejoin": True,
        "broadcast_mode": False,  # One person broadcasts, others watch
        "knocking": False,  # Require approval to join
    },
    "access": {"privacy": "public", "max_participants": None},  # "public" or "private"
    "lifespan": {
        "expires_in": None,  # seconds, None = doesn't expire
        "eject_at_expiry": False,  # Kick everyone out when room expires
    },
    "localization": {"lang": "en"},
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively merge two dictionaries.

    This function merges nested dictionaries at every level, not just the top level.
    This is critical for the profile system because it allows profiles to override
    only specific nested keys without losing other values.

    Example:
        base = {"features": {"chat": True, "screenshare": True}}
        override = {"features": {"chat": False}}
        result = {"features": {"chat": False, "screenshare": True}}  # Screenshare preserved!

    Args:
        base: The base dictionary to start with
        override: Dictionary containing values to override

    Returns:
        A new dictionary with merged values
    """
    # Start with a copy of the base dictionary
    result = base.copy()

    # Iterate through each key-value pair in the override dictionary
    for key, value in override.items():
        # Check if this key exists in the base AND both values are dictionaries
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # Both are dictionaries, so merge them recursively
            result[key] = deep_merge(result[key], value)
        else:
            # One or both are not dictionaries, so just replace the value
            result[key] = value

    return result
