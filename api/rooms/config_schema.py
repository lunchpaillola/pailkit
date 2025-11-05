"""
Config Schema - PailKit API

Defines the base configuration schema for room creation.
This is a provider-agnostic configuration that represents user intent
rather than provider-specific implementation details.
"""

from typing import Any

BASE_CONFIG: dict[str, Any] = {
    "media": {"video": True, "audio": True, "screenshare_capable": True},
    "capabilities": {
        "chat": True,
        "recording": False,
        "transcription": False,
        "live_captions": False,
        "rtmp_streaming": False,
        "breakout_rooms": False,
    },
    "interaction": {
        "prejoin": True,
        "broadcast_mode": False,
        "knocking": False,
    },
    "access": {"privacy": "public", "max_participants": None},
    "lifespan": {
        "expires_in": None,
        "eject_at_expiry": False,
    },
    "localization": {"lang": "auto"},
}
