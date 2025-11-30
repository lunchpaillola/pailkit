# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Generate Summary Step

This step generates a candidate summary/profile in scorecard format.
"""

import logging
from datetime import datetime
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
        Execute summary generation in scorecard format.

        **Simple Explanation:**
        Creates a professional scorecard-style summary that includes:
        - Candidate and interview information
        - Overall score and competency breakdown
        - Strengths and areas for improvement
        - Detailed Q&A with individual scores

        Args:
            state: Current workflow state containing candidate_info, insights, and qa_pairs

        Returns:
            Updated state with candidate_summary
        """
        # Support both candidate_info (old) and participant_info (new)
        candidate_info = state.get("candidate_info") or state.get(
            "participant_info", {}
        )

        if not self.validate_state(state, ["insights", "qa_pairs"]):
            return self.set_error(state, "Missing required state: insights or qa_pairs")

        insights = state.get("insights", {})
        qa_pairs = state.get("qa_pairs", [])
        meeting_config = state.get("meeting_config", {})
        interview_config = state.get("interview_config", {})

        # Get summary format prompt - can come from meeting_config or interview_config
        summary_format_prompt = (
            meeting_config.get("summary_format_prompt")
            or interview_config.get("summary_format_prompt")
            or None
        )

        interview_type = state.get("interview_type", "Conversation")
        interview_date = datetime.now().strftime("%Y-%m-%d")

        logger.info("📊 Generating summary")
        if summary_format_prompt:
            logger.info(
                f"   Using custom summary format prompt ({len(summary_format_prompt)} chars)"
            )

        participant_name = candidate_info.get("name", "Unknown")
        role = candidate_info.get("role", "Unknown")

        # Use custom format prompt if provided, otherwise use default
        if summary_format_prompt:
            # User provided a custom format prompt - use AI to format it
            # For now, we'll use a simple template substitution approach
            # In the future, this could use AI to format based on the prompt
            logger.info(
                "   Using custom summary format (AI formatting not yet implemented, using template)"
            )
            # For now, fall through to default format
            summary = self._generate_default_summary(
                participant_name,
                role,
                interview_type,
                interview_date,
                insights,
                qa_pairs,
                state.get("interview_transcript", ""),
            )
        else:
            # Default summary format
            summary = self._generate_default_summary(
                participant_name,
                role,
                interview_type,
                interview_date,
                insights,
                qa_pairs,
                state.get("interview_transcript", ""),
            )

        state["candidate_summary"] = summary
        state = self.update_status(state, "summary_generated")

        logger.info("✅ Summary generated")

        return state

    def _generate_default_summary(
        self,
        participant_name: str,
        role: str,
        conversation_type: str,
        conversation_date: str,
        insights: Dict[str, Any],
        qa_pairs: list,
        transcript_text: str,
    ) -> str:
        """Generate default summary format."""
        overall_score = insights.get("overall_score", 0.0)
        competency_scores = insights.get("competency_scores", {})
        strengths = insights.get("strengths", [])
        weaknesses = insights.get("weaknesses", [])
        question_assessments = insights.get("question_assessments", [])

        # Build scorecard summary
        summary = f"""Conversation Summary

Participant: {participant_name}
Role: {role}
Type: {conversation_type}
Date: {conversation_date}

{'='*60}
OVERALL ASSESSMENT
{'='*60}
Overall Score: {overall_score:.1f}/10
Questions Answered: {len(qa_pairs)}

"""

        # Competency Scores Section
        if competency_scores:
            summary += f"{'='*60}\n"
            summary += "COMPETENCY SCORES\n"
            summary += f"{'='*60}\n"
            for comp, score in competency_scores.items():
                # Create a visual bar (10 characters for 10 points)
                bar_length = int(score)
                bar = "█" * bar_length + "░" * (10 - bar_length)
                summary += f"{comp:30s} {score:4.1f}/10 {bar}\n"
            summary += "\n"
        else:
            summary += "Competency Scores: Not assessed\n\n"

        # Strengths Section
        if strengths:
            summary += f"{'='*60}\n"
            summary += "STRENGTHS\n"
            summary += f"{'='*60}\n"
            for i, strength in enumerate(strengths, 1):
                summary += f"{i}. {strength}\n"
            summary += "\n"
        else:
            summary += "Strengths: To be analyzed from transcript\n\n"

        # Areas for Improvement Section
        if weaknesses:
            summary += f"{'='*60}\n"
            summary += "AREAS FOR IMPROVEMENT\n"
            summary += f"{'='*60}\n"
            for i, weakness in enumerate(weaknesses, 1):
                summary += f"{i}. {weakness}\n"
            summary += "\n"
        else:
            summary += "Areas for Improvement: To be analyzed from transcript\n\n"

        # Detailed Q&A Section
        summary += f"{'='*60}\n"
        summary += "DETAILED Q&A\n"
        summary += f"{'='*60}\n\n"

        # Use question_assessments if available, otherwise use qa_pairs
        if question_assessments and len(question_assessments) == len(qa_pairs):
            for i, assessment in enumerate(question_assessments, 1):
                question = assessment.get(
                    "question", qa_pairs[i - 1].get("question", "")
                )
                answer = assessment.get("answer", qa_pairs[i - 1].get("answer", ""))
                score = assessment.get("score", 0.0)
                notes = assessment.get("notes", "")

                summary += f"Question {i} (Score: {score:.1f}/10)\n"
                summary += f"Q: {question}\n"
                summary += f"A: {answer}\n"
                if notes:
                    summary += f"Assessment: {notes}\n"
                summary += "\n"
        else:
            # Fallback to basic Q&A format
            for i, qa in enumerate(qa_pairs, 1):
                summary += f"Question {i}\n"
                summary += f"Q: {qa.get('question', 'N/A')}\n"
                answer = qa.get("answer", "N/A")
                # Truncate very long answers for readability
                if len(answer) > 500:
                    answer = answer[:500] + "..."
                summary += f"A: {answer}\n\n"

        # Full Transcript Reference
        if transcript_text:
            summary += f"{'='*60}\n"
            summary += "FULL TRANSCRIPT\n"
            summary += f"{'='*60}\n"
            # Include full transcript (truncated if very long)
            if len(transcript_text) > 5000:
                summary += (
                    transcript_text[:5000]
                    + "\n\n[... transcript truncated for brevity ...]"
                )
            else:
                summary += transcript_text

        return summary
