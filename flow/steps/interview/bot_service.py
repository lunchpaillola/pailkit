# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Backward compatibility module - redirects to agent_call.bot.bot_service.

This module maintains backward compatibility for code that imports from flow.steps.interview.bot_service.
"""

# Re-export everything from the new location
from flow.steps.agent_call.bot.bot_service import (
    BotProcess,
    BotService,
    SpeakerTrackingProcessor,
    TalkingAnimation,
    TranscriptHandler,
    bot_service,
    load_bot_video_frames,
)

__all__ = [
    "BotService",
    "bot_service",
    "BotProcess",
    "TranscriptHandler",
    "SpeakerTrackingProcessor",
    "TalkingAnimation",
    "load_bot_video_frames",
]
