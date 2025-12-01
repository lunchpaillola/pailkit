# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Generate Summary Step

This step generates a candidate summary/profile in scorecard format.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any, Dict

from flow.steps.interview.base import InterviewStep

logger = logging.getLogger(__name__)


class GenerateSummaryStep(InterviewStep):
    """
    Generate candidate summary/profile.
    """

    def __init__(self):
        super().__init__(
            name="generate_summary",
            description="Generate candidate summary and profile",
        )

    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute summary generation in scorecard format.

        Args:
            state: Current workflow state containing participant_info, insights, and qa_pairs

        Returns:
            Updated state with candidate_summary
        """
        # Get participant_info from state
        participant_info = state.get("participant_info", {})

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

        # Get interview type - can come from meeting_config, interview_config, or state
        interview_type = (
            meeting_config.get("interview_type")
            or interview_config.get("interview_type")
            or state.get("interview_type", "Conversation")
        )
        interview_date = datetime.now().strftime("%Y-%m-%d")

        logger.info("📊 Generating summary")
        if summary_format_prompt:
            logger.info(
                f"   Using custom summary format prompt ({len(summary_format_prompt)} chars)"
            )

        # Extract participant name and role - check multiple sources
        # First check participant_info (primary source)
        participant_name = participant_info.get("name") or participant_info.get(
            "participant_name"
        )
        role = participant_info.get("role") or participant_info.get("position")

        # If still not found, check meeting_config
        if not participant_name or participant_name == "Unknown":
            participant_name = meeting_config.get("participant_name") or "Unknown"
        if not role or role == "Unknown":
            role = (
                meeting_config.get("role")
                or meeting_config.get("position")
                or "Unknown"
            )

        # Use custom format prompt if provided, otherwise use default
        if summary_format_prompt:
            # User provided a custom format prompt - use AI to generate summary
            logger.info("   Using AI to generate summary from custom format prompt")
            summary = await self._generate_ai_summary(
                participant_name,
                role,
                interview_type,
                interview_date,
                insights,
                qa_pairs,
                state.get("interview_transcript", ""),
                summary_format_prompt,
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

                # Only show score if it's meaningful (not 0.0) or if there are notes
                # Skip "Assessment pending" messages
                has_meaningful_assessment = score > 0.0 or (
                    notes
                    and notes.lower()
                    not in [
                        "assessment pending",
                        "assessment pending - ai analysis unavailable",
                    ]
                )

                if has_meaningful_assessment:
                    summary += f"Question {i} (Score: {score:.1f}/10)\n"
                else:
                    summary += f"Question {i}\n"
                summary += f"Q: {question}\n"
                summary += f"A: {answer}\n"
                # Only show assessment notes if they're meaningful
                if notes and notes.lower() not in [
                    "assessment pending",
                    "assessment pending - ai analysis unavailable",
                ]:
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

    async def _generate_ai_summary(
        self,
        participant_name: str,
        role: str,
        conversation_type: str,
        conversation_date: str,
        insights: Dict[str, Any],
        qa_pairs: list,
        transcript_text: str,
        format_prompt: str,
    ) -> str:
        """
        Generate summary using AI based on custom format prompt.
        """
        # Get OpenAI API key
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            logger.warning("⚠️ OPENAI_API_KEY not set - falling back to default format")
            return self._generate_default_summary(
                participant_name,
                role,
                conversation_type,
                conversation_date,
                insights,
                qa_pairs,
                transcript_text,
            )

        try:
            # Import OpenAI client
            try:
                from openai import AsyncOpenAI
            except ImportError:
                logger.error(
                    "❌ OpenAI package not installed. Install with: pip install openai"
                )
                return self._generate_default_summary(
                    participant_name,
                    role,
                    conversation_type,
                    conversation_date,
                    insights,
                    qa_pairs,
                    transcript_text,
                )

            client = AsyncOpenAI(api_key=openai_api_key)

            # Build context data for the AI
            context_data = {
                "participant_name": participant_name,
                "role": role,
                "conversation_type": conversation_type,
                "conversation_date": conversation_date,
                "overall_score": insights.get("overall_score", 0.0),
                "competency_scores": insights.get("competency_scores", {}),
                "strengths": insights.get("strengths", []),
                "weaknesses": insights.get("weaknesses", []),
                "questions_answered": len(qa_pairs),
                "qa_pairs": qa_pairs,
                "question_assessments": insights.get("question_assessments", []),
            }

            # Build the prompt for AI
            # Replace placeholders in format_prompt if they exist
            ai_prompt = format_prompt
            if "{participant_name}" in ai_prompt:
                ai_prompt = ai_prompt.replace("{participant_name}", participant_name)
            if "{role}" in ai_prompt:
                ai_prompt = ai_prompt.replace("{role}", role)
            if "{conversation_type}" in ai_prompt:
                ai_prompt = ai_prompt.replace("{conversation_type}", conversation_type)
            if "{conversation_date}" in ai_prompt:
                ai_prompt = ai_prompt.replace("{conversation_date}", conversation_date)

            # Add context data as JSON
            context_json = json.dumps(context_data, indent=2)
            ai_prompt += f"\n\nContext Data:\n{context_json}"

            # Add transcript if available
            if transcript_text:
                # Truncate very long transcripts
                transcript_preview = (
                    transcript_text[:3000] + "..."
                    if len(transcript_text) > 3000
                    else transcript_text
                )
                ai_prompt += f"\n\nConversation Transcript:\n{transcript_preview}"

            # Add instructions
            ai_prompt += "\n\nGenerate a summary following the format described above. "
            ai_prompt += "Use the context data provided. "
            ai_prompt += "Do not include 'Assessment pending' or placeholder text. "
            ai_prompt += "Only include scores and assessments if they are meaningful (not 0.0 or empty)."

            # Call OpenAI API
            logger.info("🤖 Calling OpenAI API to generate summary...")
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at creating professional summaries and reports. "
                        "Follow the user's format instructions precisely. "
                        "Create clear, well-structured summaries that are easy to read.",
                    },
                    {"role": "user", "content": ai_prompt},
                ],
                temperature=0.7,  # Slightly higher for more natural formatting
            )

            summary = response.choices[0].message.content
            logger.info(f"✅ AI-generated summary created ({len(summary)} chars)")
            return summary

        except Exception as e:
            logger.error(f"❌ Error during AI summary generation: {e}", exc_info=True)
            logger.info("   Falling back to default format")
            return self._generate_default_summary(
                participant_name,
                role,
                conversation_type,
                conversation_date,
                insights,
                qa_pairs,
                transcript_text,
            )
