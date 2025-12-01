# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Package Results Step

This step packages and returns final results.
"""

import logging
from typing import Any, Dict

from flow.steps.interview.base import InterviewStep

logger = logging.getLogger(__name__)


class PackageResultsStep(InterviewStep):
    """
    Package and return final results.

    This is the final step. It puts together all the results (video recording,
    transcript, analysis) into a nice package that can be returned. It's like
    putting everything in a folder and labeling it.
    """

    def __init__(self):
        super().__init__(
            name="package_results", description="Package final interview results"
        )

    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute result packaging.

        Args:
            state: Current workflow state with all interview data

        Returns:
            Updated state with packaged results
        """
        logger.info("📦 Packaging final results")

        results = {
            "session_id": state.get("session_id"),
            "candidate_info": state.get("candidate_info"),
            "room_url": state.get("room_url"),
            "recording_id": state.get("recording_id"),
            "transcription_id": state.get("transcription_id"),
            "interview_transcript": state.get("interview_transcript"),
            "qa_pairs": state.get("qa_pairs"),
            "insights": state.get("insights"),
            "candidate_summary": state.get("candidate_summary"),
            "processing_status": state.get("processing_status"),
        }

        state["results"] = results
        state = self.update_status(state, "completed")

        logger.info("✅ Results packaged successfully")

        return state
