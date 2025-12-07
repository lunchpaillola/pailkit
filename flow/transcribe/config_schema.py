# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Config Schema - PailKit API

Defines the base configuration schema for transcription requests.
This is a provider-agnostic configuration that represents user intent
rather than provider-specific implementation details.
"""

from typing import Any

CORE_LANGUAGES: dict[str, str] = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "hi": "Hindi",
    "ru": "Russian",
    "nl": "Dutch",
    "id": "Indonesian",
    "tr": "Turkish",
    "sv": "Swedish",
    "uk": "Ukrainian",
    "auto": "Auto-detect",
}

VALID_REDACTION_TYPES: set[str] = {"pci", "phi", "pii"}


def validate_redact(redact: list[str] | None) -> None:
    """Validate redact values to ensure only valid redaction types are used."""
    if redact is None:
        return
    invalid_types = set(redact) - VALID_REDACTION_TYPES
    if invalid_types:
        raise ValueError(
            f"Invalid redaction types: {invalid_types}. "
            f"Valid types are: {sorted(VALID_REDACTION_TYPES)}"
        )


BASE_TRANSCRIPTION_CONFIG: dict[str, Any] = {
    "language": "auto",
    "features": {
        "punctuate": True,
        "diarization": False,
        "smart_format": False,
        "filler_words": False,
        "profanity_filter": False,
        "redact": None,
        "numerals": False,
    },
}
