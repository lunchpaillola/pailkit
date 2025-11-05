"""
Transcription Profiles - PailKit API

Defines opinionated experience profiles for different transcription use cases.
Each profile represents a complete transcription setup with sensible defaults.
"""

from typing import Any

from transcribe.config_schema import BASE_TRANSCRIPTION_CONFIG
from utils import deep_merge

# Meeting profile - Optimized for meeting transcription
# Use case: Business meetings, team standups, conference calls
PROFILE_MEETING: dict[str, Any] = deep_merge(
    BASE_TRANSCRIPTION_CONFIG,
    {
        "features": {
            "punctuate": True,
            "diarization": True,
            "smart_format": True,
            "filler_words": True,
        },
    },
)


# Podcast profile - High-quality transcription for content
# Use case: Podcasts, interviews, long-form audio content
PROFILE_PODCAST: dict[str, Any] = deep_merge(
    BASE_TRANSCRIPTION_CONFIG,
    {
        "features": {
            "punctuate": True,
            "diarization": True,
            "smart_format": True,
            "filler_words": False,
        },
    },
)


# Medical profile - Medical vocabulary and HIPAA compliance
# Use case: Medical consultations, patient interviews, healthcare recordings
PROFILE_MEDICAL: dict[str, Any] = deep_merge(
    BASE_TRANSCRIPTION_CONFIG,
    {
        "features": {
            "punctuate": True,
            "diarization": True,
            "smart_format": True,
            "redact": ["phi"],
        },
    },
)


# Finance profile - Finance vocabulary and number formatting
# Use case: Financial meetings, earnings calls, trading discussions
PROFILE_FINANCE: dict[str, Any] = deep_merge(
    BASE_TRANSCRIPTION_CONFIG,
    {
        "features": {
            "punctuate": True,
            "diarization": True,
            "smart_format": True,
            "numerals": True,
            "filler_words": False,
        },
    },
)


# Dictionary mapping profile names to their configurations
PROFILES: dict[str, dict[str, Any]] = {
    "meeting": PROFILE_MEETING,
    "podcast": PROFILE_PODCAST,
    "medical": PROFILE_MEDICAL,
    "finance": PROFILE_FINANCE,
}
