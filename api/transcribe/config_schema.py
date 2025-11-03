"""
Config Schema - PailKit API

Defines the base configuration schema for transcription requests.
This is a provider-agnostic configuration that represents user intent
rather than provider-specific implementation details.
"""

from typing import Any

BASE_TRANSCRIPTION_CONFIG = {
    "language": "en",  # Language code (ISO 639-1)
    "model": "nova-2",  # Transcription model to use
    "features": {
        "punctuation": True,  # Add punctuation to transcript
        "profanity_filter": False,  # Filter out profanity
        "speaker_diarization": False,  # Identify different speakers
        "sentiment_analysis": False,  # Analyze sentiment of speech
        "keyword_detection": False,  # Detect specific keywords
    },
    "output": {
        "format": "text",  # Output format: "text", "json", "srt", "vtt"
        "include_timestamps": False,  # Include timestamps in output
        "include_speaker_labels": False,  # Include speaker labels (requires diarization)
    },
    "targeting": {
        "scope": "all",  # What to transcribe: "all", "speakers", "audio_only"
        "speaker_ids": None,  # Specific speaker IDs to transcribe (if scope is "speakers")
    },
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively merge two dictionaries.

    This function merges nested dictionaries at every level, not just the top level.
    This is critical for the profile system because it allows profiles to override
    only specific nested keys without losing other values.

    Example:
        base = {"features": {"punctuation": True, "diarization": True}}
        override = {"features": {"punctuation": False}}
        result = {"features": {"punctuation": False, "diarization": True}}  # Diarization preserved!

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
