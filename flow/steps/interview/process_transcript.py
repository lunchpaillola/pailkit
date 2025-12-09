# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Backward compatibility module - redirects to agent_call.steps.process_transcript.

This module maintains backward compatibility for code that imports from flow.steps.interview.process_transcript.
"""

# Re-export everything from the new location
from flow.steps.agent_call.steps.process_transcript import (
    ProcessTranscriptStep,
    parse_transcript_to_qa_pairs,
    parse_vtt_to_text,
    send_email,
    send_webhook,
)

__all__ = [
    "ProcessTranscriptStep",
    "parse_transcript_to_qa_pairs",
    "parse_vtt_to_text",
    "send_email",
    "send_webhook",
]
