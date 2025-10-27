"""
Config Builder - PailKit API

Builds final room configuration by merging base config, profile, and overrides.
This is the single source of truth for config composition across all adapters.
"""

from typing import Any

from rooms.config_schema import BASE_CONFIG, deep_merge
from rooms.profiles import PROFILES


def build_config(
    profile: str = "conversation", overrides: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Build the final room configuration by merging base, profile, and overrides.

    This function implements a three-layer merge strategy:
    1. Start with BASE_CONFIG (sensible defaults for all settings)
    2. Apply profile overrides (modify specific settings for a use case)
    3. Apply user overrides (customize anything the user wants to change)

    This allows users to say "I want a broadcast room" (profile) and
    customize it with "but turn off chat" (overrides), without having to
    specify all settings from scratch.

    Args:
        profile: Name of the profile to use (e.g., "conversation", "broadcast")
        overrides: Optional dictionary of settings to override

    Returns:
        Final configuration dictionary ready to be translated to provider-specific format

    Example:
        >>> config = build_config(profile="broadcast", overrides={"capabilities": {"chat": False}})
        >>> # Result: broadcast config with chat disabled
    """
    # Step 1: Start with base configuration
    config = BASE_CONFIG.copy()

    # Step 2: Apply profile overrides if the profile exists
    if profile in PROFILES:
        profile_config = PROFILES[profile]
        config = deep_merge(config, profile_config)
    else:
        # If invalid profile, fall back to base (could also raise an error)
        pass

    # Step 3: Apply user-provided overrides if any
    if overrides:
        config = deep_merge(config, overrides)

    return config

