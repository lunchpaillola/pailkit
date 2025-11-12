# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Process Transcript Step

This step processes the transcript and separates Q&A pairs.
"""

import logging
from typing import Any, Dict

from flow.steps.interview.base import InterviewStep

logger = logging.getLogger(__name__)


class ProcessTranscriptStep(InterviewStep):
    """
    Process transcript and separate Q&A pairs.

    **Simple Explanation:**
    This step takes the full interview transcript and breaks it down into
    individual question-answer pairs so we can analyze each one separately.
    It's like cutting a long conversation into separate Q&A segments.
    """

    def __init__(self):
        super().__init__(
            name="process_transcript",
            description="Process interview transcript and separate into Q&A pairs",
        )

    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute transcript processing.

        Args:
            state: Current workflow state containing interview_transcript and selected_questions

        Returns:
            Updated state with qa_pairs
        """
        # Validate required state
        if not self.validate_state(state, ["interview_transcript"]):
            return self.set_error(state, "No interview transcript available")

        interview_transcript = state.get("interview_transcript", "")
        selected_questions = state.get("selected_questions", [])

        logger.info("📄 Processing transcript and separating Q&A pairs")

        # TODO: Replace with proper NLP/AI-based transcript parsing
        # In a real implementation, this would use NLP/AI to properly separate
        # questions and answers from the transcript. For now, we'll do a simple split.

        qa_pairs = []

        # Simple parsing: split by "Interviewer:" and "Candidate:" markers
        lines = interview_transcript.split("\n\n")
        current_question = None
        current_answer = None

        for line in lines:
            if line.startswith("Interviewer:"):
                # Save previous Q&A pair if exists
                if current_question and current_answer:
                    qa_pairs.append(
                        {
                            "question": current_question,
                            "answer": current_answer,
                            "question_id": (
                                selected_questions[len(qa_pairs)].get("id")
                                if len(qa_pairs) < len(selected_questions)
                                else None
                            ),
                        }
                    )
                current_question = line.replace("Interviewer:", "").strip()
                current_answer = None
            elif line.startswith("Candidate:"):
                current_answer = line.replace("Candidate:", "").strip()

        # Add the last pair
        if current_question and current_answer:
            qa_pairs.append(
                {
                    "question": current_question,
                    "answer": current_answer,
                    "question_id": (
                        selected_questions[len(qa_pairs)].get("id")
                        if len(qa_pairs) < len(selected_questions)
                        else None
                    ),
                }
            )

        state["qa_pairs"] = qa_pairs
        state = self.update_status(state, "transcript_processed")

        logger.info(f"✅ Processed {len(qa_pairs)} Q&A pairs")

        return state
