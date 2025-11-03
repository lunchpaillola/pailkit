"""
Config Builder - PailKit API

Builds final transcription configuration by merging base config, profile, and overrides.
This is the single source of truth for config composition across all adapters.
"""

from typing import Any

from transcribe.config_schema import BASE_TRANSCRIPTION_CONFIG, deep_merge
from transcribe.profiles import PROFILES


def build_config(
    profile: str = "meeting_notes", overrides: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Build the final transcription configuration by merging base, profile, and overrides.

    This function implements a three-layer merge strategy:
    1. Start with BASE_TRANSCRIPTION_CONFIG (sensible defaults for all settings)
    2. Apply profile overrides (modify specific settings for a use case)
    3. Apply user overrides (customize anything the user wants to change)

    This allows users to say "I want meeting notes" (profile) and
    customize it with "but use Spanish language" (overrides), without having to
    specify all settings from scratch.

    Args:
        profile: Name of the profile to use (e.g., "meeting_notes", "live_captions")
        overrides: Optional dictionary of settings to override

    Returns:
        Final configuration dictionary ready to be translated to provider-specific format

    Example:
        >>> config = build_config(profile="meeting_notes", overrides={"language": "es"})
        >>> # Result: meeting notes config with Spanish language
    """
    # Step 1: Start with base configuration
    config = BASE_TRANSCRIPTION_CONFIG.copy()

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
