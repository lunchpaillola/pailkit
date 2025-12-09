# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Agent call workflow steps and bot service.

This module contains:
- Workflow steps (in steps/): ProcessTranscriptStep, ExtractInsightsStep
- Bot service components (in bot/): BotService, bot_service, and related Daily.co bot logic
"""

# Re-export everything from submodules for convenience
from flow.steps.agent_call.bot import (
    BotProcess,
    BotService,
    SpeakerTrackingProcessor,
    TalkingAnimation,
    TranscriptHandler,
    bot_service,
    load_bot_video_frames,
)
from flow.steps.agent_call.steps import (
    ExtractInsightsStep,
    InterviewStep,
    ProcessTranscriptStep,
)

__all__ = [
    # Steps
    "InterviewStep",
    "ProcessTranscriptStep",
    "ExtractInsightsStep",
    # Bot service components
    "BotService",
    "bot_service",
    "BotProcess",
    "TranscriptHandler",
    "SpeakerTrackingProcessor",
    "TalkingAnimation",
    "load_bot_video_frames",
]
