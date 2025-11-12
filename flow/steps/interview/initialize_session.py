# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Initialize Session Step

This step initializes the interview session with candidate details and creates
a unique session ID for tracking.
"""

import logging
import uuid
from typing import Any, Dict

from flow.steps.interview.base import InterviewStep

logger = logging.getLogger(__name__)


class InitializeSessionStep(InterviewStep):
    """
    Initialize the interview session.

    **Simple Explanation:**
    This is the first step. It takes the candidate information and sets up
    a unique session ID for tracking this interview. It's like creating a
    new file folder for this specific interview.
    """

    def __init__(self):
        super().__init__(
            name="initialize_session",
            description="Initialize interview session with candidate details and create session ID",
        )

    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the session initialization.

        Args:
            state: Current workflow state containing candidate_info

        Returns:
            Updated state with session_id and initialized fields
        """
        candidate_info = state.get("candidate_info", {})
        candidate_name = candidate_info.get("name", "Unknown")

        logger.info(f"🚀 Initializing interview session for {candidate_name}")

        # Generate a unique session ID
        session_id = str(uuid.uuid4())

        # Initialize state fields
        state["session_id"] = session_id
        state["current_question_index"] = 0
        state["qa_pairs"] = []
        state["insights"] = {}

        # Update status
        state = self.update_status(state, "session_initialized")

        logger.info(f"✅ Session initialized: {session_id}")

        return state
