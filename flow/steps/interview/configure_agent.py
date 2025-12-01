# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Configure Agent Step

This step configures the AI interviewer persona and context.
"""

import logging
from typing import Any, Dict

from flow.steps.interview.base import InterviewStep

logger = logging.getLogger(__name__)


class ConfigureAgentStep(InterviewStep):
    """
    Configure the AI interviewer persona and context.

    This step sets up how the AI interviewer should behave - what tone to use,
    what context it should have about the role, etc. It's like giving the AI
    a job description and instructions on how to conduct the interview.
    """

    def __init__(self):
        super().__init__(
            name="configure_agent",
            description="Configure AI interviewer persona and context",
        )

    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute agent configuration.

        Args:
            state: Current workflow state containing candidate_info and interview_config

        Returns:
            Updated state with interviewer_persona and interviewer_context
        """
        # Validate required state
        if not self.validate_state(state, ["candidate_info", "interview_config"]):
            return self.set_error(
                state, "Missing required state: candidate_info or interview_config"
            )

        candidate_info = state.get("candidate_info", {})
        interview_config = state.get("interview_config", {})

        role = candidate_info.get("role", "Software Engineer")
        interview_type = interview_config.get("interview_type", "mixed")
        difficulty = interview_config.get("difficulty_level", "mid")

        # Build interviewer persona
        persona = f"""You are a professional, friendly, and thorough technical interviewer.
Your role is to conduct a {difficulty}-level {interview_type} interview for a {role} position.
You should:
- Ask clear, well-structured questions
- Listen actively to responses
- Provide brief, encouraging feedback when appropriate
- Move to the next question when the candidate has finished answering
- Maintain a professional but warm tone"""

        # Build context about the role and candidate
        context = f"""Interview Details:
- Position: {role}
- Interview Type: {interview_type}
- Difficulty Level: {difficulty}
- Candidate: {candidate_info.get('name', 'Unknown')}
- Experience: {candidate_info.get('experience_years', 'Not specified')} years"""

        if candidate_info.get("resume_url"):
            context += f"\n- Resume: {candidate_info['resume_url']}"

        state["interviewer_persona"] = persona
        state["interviewer_context"] = context
        state = self.update_status(state, "ai_configured")

        logger.info(f"✅ AI interviewer configured for {role} position")

        return state
