"""
Room Profiles - PailKit API

Defines opinionated experience profiles for different use cases.
Each profile represents a complete room experience with sensible defaults.
"""

from typing import Any

from rooms.config_schema import BASE_CONFIG
from utils import deep_merge

# Conversation profile - Standard video chat
# Use case: Quick 1-on-1 or small group video calls
PROFILE_CONVERSATION: dict[str, Any] = deep_merge(
    BASE_CONFIG,
    {
        "capabilities": {
            "chat": True,
            "recording": False,
            "transcription": False,
            "live_captions": False,
        },
        "interaction": {"prejoin": True},
    },
)


# Audio Room profile - Audio-only conversation
# Use case: Voice chat, audio meetings, phone call style
PROFILE_AUDIO_ROOM: dict[str, Any] = deep_merge(
    BASE_CONFIG,
    {
        "media": {
            "video": False,  # Audio only
            "audio": True,
            "screenshare_capable": False,
        },
        "capabilities": {"chat": True, "recording": False},
        "interaction": {"prejoin": False},  # Fast join for audio
    },
)


# Broadcast profile - One-to-many presentation
# Use case: Webinars, presentations, teaching sessions
PROFILE_BROADCAST: dict[str, Any] = deep_merge(
    BASE_CONFIG,
    {
        "capabilities": {
            "chat": True,  # Q&A chat
            "recording": True,  # Save the session
            "transcription": True,  # Accessibility
            "live_captions": True,  # Show captions on screen
            "rtmp_streaming": False,
        },
        "interaction": {
            "broadcast_mode": True,  # One person broadcasts, others watch
            "prejoin": True,
        },
    },
)


# Podcast profile - Audio recording session
# Use case: Podcasts, interviews, audio content creation
PROFILE_PODCAST: dict[str, Any] = deep_merge(
    BASE_CONFIG,
    {
        "media": {
            "video": False,  # Audio only
            "audio": True,
            "screenshare_capable": False,
        },
        "capabilities": {
            "chat": False,  # Minimal UI, focus on recording
            "recording": True,  # Record the session
            "transcription": True,  # Automatic transcription
            "live_captions": False,
        },
        "interaction": {"prejoin": True, "broadcast_mode": False},
    },
)


# Live Stream profile - Stream to external platforms
# Use case: Stream to YouTube, Twitch, or other RTMP platforms
# TODO: Implement this profile
PROFILE_LIVE_STREAM: dict[str, Any] = deep_merge(
    BASE_CONFIG,
    {
        "capabilities": {
            "chat": True,  # Audience chat
            "recording": True,  # Save a copy locally
            "rtmp_streaming": True,  # Stream to external platform
            "transcription": False,
            "live_captions": False,
        },
        "interaction": {
            "broadcast_mode": True,  # Broadcaster controls
            "prejoin": True,
        },
    },
)


# Workshop profile - Interactive collaborative session
# Use case: Classes, training sessions, collaborative workshops
PROFILE_WORKSHOP: dict[str, Any] = deep_merge(
    BASE_CONFIG,
    {
        "capabilities": {
            "chat": True,
            "screenshare_capable": True,
            "recording": True,
            "transcription": True,
            "live_captions": True,
            "breakout_rooms": True,  # Enable breakout sessions
        },
        "interaction": {"prejoin": True, "broadcast_mode": False},
    },
)


# Dictionary mapping profile names to their configurations
PROFILES: dict[str, dict[str, Any]] = {
    "conversation": PROFILE_CONVERSATION,
    "audio_room": PROFILE_AUDIO_ROOM,
    "broadcast": PROFILE_BROADCAST,
    "podcast": PROFILE_PODCAST,
    "live_stream": PROFILE_LIVE_STREAM,
    "workshop": PROFILE_WORKSHOP,
}
