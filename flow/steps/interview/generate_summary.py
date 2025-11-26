# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Generate Summary Step

This step generates a candidate summary/profile.
"""

import logging
from typing import Any, Dict

from flow.steps.interview.base import InterviewStep

logger = logging.getLogger(__name__)


class GenerateSummaryStep(InterviewStep):
    """
    Generate candidate summary/profile.

    **Simple Explanation:**
    This step creates a final summary document about the candidate based on
    everything we learned during the interview. It's like writing a report
    card that summarizes their performance.
    """

    def __init__(self):
        super().__init__(
            name="generate_summary",
            description="Generate candidate summary and profile",
        )

    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute summary generation.

        Args:
            state: Current workflow state containing candidate_info, insights, and qa_pairs

        Returns:
            Updated state with candidate_summary
        """
        # Validate required state
        if not self.validate_state(state, ["candidate_info", "insights", "qa_pairs"]):
            return self.set_error(
                state, "Missing required state: candidate_info, insights, or qa_pairs"
            )

        candidate_info = state.get("candidate_info", {})
        insights = state.get("insights", {})
        qa_pairs = state.get("qa_pairs", [])

        logger.info("📊 Generating candidate summary")

        # TODO: Replace with actual AI-based summary generation
        # In a real implementation, this would use an AI model to generate
        # a comprehensive summary. For now, we'll create a basic template.

        candidate_name = candidate_info.get("name", "Unknown")
        role = candidate_info.get("role", "Unknown")

        summary = f"""Candidate Interview Summary

Candidate: {candidate_name}
Position: {role}
Interview Date: [Date would be added]

Overall Assessment:
- Overall Score: {insights.get('overall_score', 0.0)}/10
- Questions Answered: {len(qa_pairs)}

Competency Scores:
"""

        for comp, score in insights.get("competency_scores", {}).items():
            summary += f"- {comp}: {score}/10\n"

        summary += f"""
Strengths:
{chr(10).join(f"- {s}" for s in insights.get('strengths', ['To be assessed']))}

Areas for Improvement:
{chr(10).join(f"- {w}" for w in insights.get('weaknesses', ['To be assessed']))}

Detailed Q&A:
"""

        for i, qa in enumerate(qa_pairs, 1):
            summary += f"\n{i}. {qa.get('question')}\n"
            summary += f"   Answer: {qa.get('answer', 'N/A')[:200]}...\n"

        state["candidate_summary"] = summary
        state = self.update_status(state, "summary_generated")

        logger.info("✅ Candidate summary generated")

        return state
