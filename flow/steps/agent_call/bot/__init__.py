# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Daily.co bot service and related components.

This module contains the bot service, executor, and all Daily.co-related bot logic
including transcript handling, speaker tracking, animation, and video frames.
"""

from flow.steps.agent_call.bot.animation import TalkingAnimation
from flow.steps.agent_call.bot.bot_process import BotProcess
from flow.steps.agent_call.bot.bot_service import BotService, bot_service
from flow.steps.agent_call.bot.speaker_tracking import SpeakerTrackingProcessor
from flow.steps.agent_call.bot.transcript_handler import TranscriptHandler
from flow.steps.agent_call.bot.video_frames import load_bot_video_frames

__all__ = [
    "BotService",
    "bot_service",
    "BotProcess",
    "TranscriptHandler",
    "SpeakerTrackingProcessor",
    "TalkingAnimation",
    "load_bot_video_frames",
]
