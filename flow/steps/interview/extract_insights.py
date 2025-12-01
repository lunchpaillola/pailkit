# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Extract Insights Step

This step extracts insights and assesses competencies from the interview.
"""

import json
import logging
import os
from typing import Any, Dict, List, cast

from flow.steps.interview.base import InterviewStep

logger = logging.getLogger(__name__)


class ExtractInsightsStep(InterviewStep):
    """
    Extract insights and assess competencies.
    """

    def __init__(self):
        super().__init__(
            name="extract_insights",
            description="Extract insights and assess candidate competencies",
        )

    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute insight extraction using AI analysis.

        Args:
            state: Current workflow state containing qa_pairs and interview_config

        Returns:
            Updated state with insights
        """
        # Validate required state
        if not self.validate_state(state, ["qa_pairs"]):
            return self.set_error(state, "Missing required state: qa_pairs")

        qa_pairs = state.get("qa_pairs", [])
        meeting_config = state.get("meeting_config", {})
        interview_config = state.get("interview_config", {})

        # Get analysis prompt - this is the main way to configure analysis
        # Can come from meeting_config or interview_config (for backwards compatibility)
        analysis_prompt = (
            meeting_config.get("analysis_prompt")
            or interview_config.get("analysis_prompt")
            or None
        )

        logger.info("🧠 Extracting insights using AI analysis")
        if analysis_prompt:
            logger.info(
                f"   Using custom analysis prompt ({len(analysis_prompt)} chars)"
            )
        else:
            logger.info("   Using default analysis prompt")

        # Get OpenAI API key
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            logger.warning("⚠️ OPENAI_API_KEY not set - using placeholder insights")
            return self._create_placeholder_insights(state, qa_pairs, [])

        try:
            # Import OpenAI client
            try:
                from openai import AsyncOpenAI
            except ImportError:
                logger.error(
                    "❌ OpenAI package not installed. Install with: pip install openai"
                )
                return self._create_placeholder_insights(state, qa_pairs, [])

            client = AsyncOpenAI(api_key=openai_api_key)

            # Build transcript text from Q&A pairs
            qa_text = "\n\n".join(
                [
                    f"Q{i+1}: {qa.get('question', '')}\nA{i+1}: {qa.get('answer', '')}"
                    for i, qa in enumerate(qa_pairs)
                ]
            )

            # Use custom analysis prompt if provided, otherwise use default
            if analysis_prompt:
                # User provided a custom prompt - inject the transcript into it
                # Look for placeholders like {transcript} or {qa_text} or just append
                if "{transcript}" in analysis_prompt:
                    final_prompt = analysis_prompt.replace("{transcript}", qa_text)
                elif "{qa_text}" in analysis_prompt:
                    final_prompt = analysis_prompt.replace("{qa_text}", qa_text)
                else:
                    # No placeholder found - append transcript at the end
                    final_prompt = (
                        f"{analysis_prompt}\n\nConversation Transcript:\n{qa_text}"
                    )
            else:
                # Default analysis prompt (generic, not interview-specific)
                final_prompt = f"""Analyze this conversation transcript and provide a comprehensive assessment.

Conversation Transcript:
{qa_text}

Please provide a JSON response with the following structure:
{{
    "overall_score": <number 0-10>,
    "competency_scores": {{
        "<competency_name>": <score 0-10>,
        ...
    }},
    "strengths": ["<strength1>", "<strength2>", ...],
    "weaknesses": ["<weakness1>", "<weakness2>", ...],
    "question_assessments": [
        {{
            "question": "<question text>",
            "answer": "<answer text>",
            "score": <number 0-10>,
            "notes": "<brief assessment notes>"
        }},
        ...
    ]
}}

Guidelines:
- Analyze the conversation objectively
- Identify key themes, competencies, or topics discussed
- Provide specific, constructive feedback
- Score each Q&A pair individually (0-10)
- Focus on what was actually said in the transcript

Return ONLY valid JSON, no additional text."""

            # Call OpenAI API
            logger.info("🤖 Calling OpenAI API for analysis...")
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert interview evaluator. Always respond with valid JSON only.",
                    },
                    {"role": "user", "content": final_prompt},
                ],
                temperature=0.3,  # Lower temperature for more consistent analysis
                response_format={"type": "json_object"},
            )

            # Parse response
            response_text = response.choices[0].message.content
            insights = json.loads(response_text)

            # Validate and normalize insights
            insights = self._validate_insights(insights, qa_pairs)

            state["insights"] = insights
            state = self.update_status(state, "insights_extracted")

            logger.info(f"✅ Extracted insights for {len(qa_pairs)} questions")
            logger.info(f"   Overall Score: {insights.get('overall_score', 0.0)}/10")
            logger.info(
                f"   Competencies: {len(insights.get('competency_scores', {}))}"
            )
            logger.info(f"   Strengths: {len(insights.get('strengths', []))}")
            logger.info(f"   Weaknesses: {len(insights.get('weaknesses', []))}")

            return state

        except json.JSONDecodeError as e:
            logger.error(f"❌ Failed to parse AI response as JSON: {e}")
            logger.error(
                f"   Response: {response_text[:500] if 'response_text' in locals() else 'N/A'}"
            )
            return self._create_placeholder_insights(state, qa_pairs, [])
        except Exception as e:
            logger.error(f"❌ Error during AI analysis: {e}", exc_info=True)
            return self._create_placeholder_insights(state, qa_pairs, [])

    def _validate_insights(
        self, insights: Dict[str, Any], qa_pairs: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Validate and normalize insights structure.
        """
        # Ensure all required fields exist
        validated = {
            "overall_score": float(insights.get("overall_score", 0.0)),
            "competency_scores": insights.get("competency_scores", {}),
            "strengths": insights.get("strengths", []),
            "weaknesses": insights.get("weaknesses", []),
            "question_assessments": insights.get("question_assessments", []),
        }

        # Clamp scores to 0-10
        validated["overall_score"] = max(0.0, min(10.0, validated["overall_score"]))

        # Clamp competency scores
        for comp in validated["competency_scores"]:
            validated["competency_scores"][comp] = max(
                0.0, min(10.0, float(validated["competency_scores"][comp]))
            )

        # Ensure question_assessments match qa_pairs
        if len(validated["question_assessments"]) != len(qa_pairs):
            # Rebuild assessments from qa_pairs if they don't match
            validated["question_assessments"] = []
            for qa in qa_pairs:
                # Try to find matching assessment
                matching = next(
                    (
                        a
                        for a in insights.get("question_assessments", [])
                        if a.get("question") == qa.get("question")
                    ),
                    None,
                )
                if matching:
                    matching["score"] = max(
                        0.0, min(10.0, float(matching.get("score", 0.0)))
                    )
                    validated["question_assessments"].append(matching)
                else:
                    # Only create placeholder if we truly don't have an assessment
                    # Otherwise, try to extract from existing assessments
                    validated["question_assessments"].append(
                        {
                            "question": qa.get("question", ""),
                            "answer": qa.get("answer", ""),
                            "score": 0.0,
                            "notes": "",  # Empty notes instead of "Assessment pending"
                        }
                    )

        # Ensure strengths and weaknesses are lists of strings
        if not isinstance(validated["strengths"], list):
            validated["strengths"] = []
        if not isinstance(validated["weaknesses"], list):
            validated["weaknesses"] = []

        return validated

    def _create_placeholder_insights(
        self,
        state: Dict[str, Any],
        qa_pairs: List[Dict[str, Any]],
        competencies: List[str],
    ) -> Dict[str, Any]:
        """
        Create placeholder insights when AI analysis is not available.
        """
        insights: Dict[str, Any] = {
            "overall_score": 0.0,
            "competency_scores": (
                {comp: 0.0 for comp in competencies} if competencies else {}
            ),
            "strengths": ["Analysis pending - AI analysis unavailable"],
            "weaknesses": ["Analysis pending - AI analysis unavailable"],
            "question_assessments": [],
        }

        # Create basic assessments for each Q&A pair
        for i, qa in enumerate(qa_pairs):
            assessment = {
                "question": qa.get("question", ""),
                "answer": qa.get("answer", ""),
                "score": 0.0,
                "notes": "Assessment pending - AI analysis unavailable",
            }
            cast(List[Dict[str, Any]], insights["question_assessments"]).append(
                assessment
            )

        state["insights"] = insights
        state = self.update_status(state, "insights_extracted")
        logger.info(f"✅ Created placeholder insights for {len(qa_pairs)} questions")

        return state
