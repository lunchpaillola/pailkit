"""
Transcription Profiles - PailKit API

Defines opinionated experience profiles for different transcription use cases.
Each profile represents a complete transcription setup with sensible defaults.
"""

from typing import Any

from transcribe.config_schema import BASE_TRANSCRIPTION_CONFIG, deep_merge

# Meeting Notes profile - Detailed transcription for documentation
# Use case: Transcribe meetings, interviews, or conversations for note-taking
PROFILE_MEETING_NOTES: dict[str, Any] = deep_merge(
    BASE_TRANSCRIPTION_CONFIG,
    {
        "features": {
            "punctuation": True,  # Clean, readable text with punctuation
            "profanity_filter": False,  # Keep original content
            "speaker_diarization": True,  # Identify who said what
            "sentiment_analysis": False,
            "keyword_detection": False,
        },
        "output": {
            "format": "text",  # Plain text for easy reading
            "include_timestamps": True,  # Include timestamps for reference
            "include_speaker_labels": True,  # Show who said what
        },
        "targeting": {
            "scope": "all",  # Transcribe everything
        },
    },
)


# Live Captions profile - Real-time transcription for accessibility
# Use case: Live captions during video calls, streams, or presentations
PROFILE_LIVE_CAPTIONS: dict[str, Any] = deep_merge(
    BASE_TRANSCRIPTION_CONFIG,
    {
        "model": "nova-2",  # Fast, accurate model for real-time
        "features": {
            "punctuation": True,  # Clean captions with punctuation
            "profanity_filter": True,  # Filter profanity for public display
            "speaker_diarization": False,  # Not needed for live captions
            "sentiment_analysis": False,
            "keyword_detection": False,
        },
        "output": {
            "format": "text",  # Simple text format for display
            "include_timestamps": False,  # No timestamps for live display
            "include_speaker_labels": False,  # Keep it simple for readability
        },
        "targeting": {
            "scope": "all",  # Transcribe all audio
        },
    },
)


# Podcast Transcript profile - Full transcription for podcasts or audio content
# Use case: Create full transcripts of podcasts, interviews, or audio recordings
PROFILE_PODCAST_TRANSCRIPT: dict[str, Any] = deep_merge(
    BASE_TRANSCRIPTION_CONFIG,
    {
        "model": "nova-2",  # High-quality model for long-form content
        "features": {
            "punctuation": True,  # Well-formatted transcript
            "profanity_filter": False,  # Keep original content
            "speaker_diarization": True,  # Identify hosts and guests
            "sentiment_analysis": False,
            "keyword_detection": False,
        },
        "output": {
            "format": "text",  # Standard text format
            "include_timestamps": True,  # Timestamps for reference
            "include_speaker_labels": True,  # Show host vs guest
        },
        "targeting": {
            "scope": "all",  # Transcribe entire recording
        },
    },
)


# Dictionary mapping profile names to their configurations
PROFILES: dict[str, dict[str, Any]] = {
    "meeting_notes": PROFILE_MEETING_NOTES,
    "live_captions": PROFILE_LIVE_CAPTIONS,
    "podcast_transcript": PROFILE_PODCAST_TRANSCRIPT,
}
