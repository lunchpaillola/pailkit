# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Config Builder - PailKit API

Builds final transcription configuration by merging base config, profile, and overrides.
This is the single source of truth for config composition across all adapters.
"""

from typing import Any

from transcribe.config_schema import (
    BASE_TRANSCRIPTION_CONFIG,
    validate_redact,
)
from transcribe.profiles import PROFILES
from utils.deep_merge import deep_merge


def build_config(
    profile: str = "meeting", overrides: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Build the final transcription configuration by merging base, profile, and overrides.

    This function implements a three-layer merge strategy:
    1. Start with BASE_TRANSCRIPTION_CONFIG (sensible defaults for all settings)
    2. Apply profile overrides (modify specific settings for a use case)
    3. Apply user overrides (customize anything the user wants to change)

    This allows users to say "I want meeting transcription" (profile) and
    customize it with "but use Spanish language" (overrides), without having to
    specify all settings from scratch.

    Args:
        profile: Name of the profile to use (e.g., "meeting", "podcast", "medical", "finance")
        overrides: Optional dictionary of settings to override

    Returns:
        Final configuration dictionary ready to be translated to provider-specific format

    Raises:
        ValueError: If invalid profile name or invalid redaction types are provided
    """
    # Step 1: Start with base configuration
    config = BASE_TRANSCRIPTION_CONFIG.copy()

    # Step 2: Apply profile overrides
    if profile not in PROFILES:
        raise ValueError(
            f"Invalid profile: {profile}. Valid profiles are: {sorted(PROFILES.keys())}"
        )
    profile_config = PROFILES[profile]
    config = deep_merge(config, profile_config)

    # Step 3: Apply user-provided overrides if any
    if overrides:
        config = deep_merge(config, overrides)

    # Step 4: Validate redact values if present
    features = config.get("features", {})
    if isinstance(features, dict):
        redact_value = features.get("redact")
        if redact_value is not None:
            validate_redact(redact_value)

    # Step 5: Add profile name to config for provider-specific model mapping
    # This allows providers to map profiles to their own model names
    config["profile"] = profile

    return config
