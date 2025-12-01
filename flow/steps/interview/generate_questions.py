# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Generate Questions Step

This step generates interview questions from the question bank.
"""

import logging
from typing import Any, Dict, List

from flow.steps.interview.base import InterviewStep

logger = logging.getLogger(__name__)


# Question bank data structure
# This is a simple in-memory question bank. In production, this would be
# stored in a database or external service.
QUESTION_BANK: Dict[str, List[Dict[str, Any]]] = {
    "technical": [
        {
            "id": "tech_1",
            "question": "Can you explain the difference between a stack and a queue?",
            "category": "data_structures",
            "difficulty": "junior",
            "competencies": ["algorithms", "data_structures"],
        },
        {
            "id": "tech_2",
            "question": "How would you optimize a slow database query?",
            "category": "databases",
            "difficulty": "mid",
            "competencies": ["databases", "performance"],
        },
        {
            "id": "tech_3",
            "question": "Explain the concept of microservices and when you would use them.",
            "category": "architecture",
            "difficulty": "senior",
            "competencies": ["architecture", "system_design"],
        },
    ],
    "behavioral": [
        {
            "id": "behav_1",
            "question": "Tell me about a time you had to work under pressure.",
            "category": "stress_management",
            "difficulty": "junior",
            "competencies": ["communication", "stress_management"],
        },
        {
            "id": "behav_2",
            "question": "Describe a situation where you had to resolve a conflict with a team member.",
            "category": "teamwork",
            "difficulty": "mid",
            "competencies": ["teamwork", "conflict_resolution"],
        },
        {
            "id": "behav_3",
            "question": "Give an example of a time you led a project that failed. What did you learn?",
            "category": "leadership",
            "difficulty": "senior",
            "competencies": ["leadership", "learning"],
        },
    ],
    "mixed": [
        {
            "id": "mixed_1",
            "question": "How do you approach debugging a complex issue?",
            "category": "problem_solving",
            "difficulty": "mid",
            "competencies": ["problem_solving", "technical_skills"],
        },
        {
            "id": "mixed_2",
            "question": "Describe your process for learning a new technology.",
            "category": "learning",
            "difficulty": "junior",
            "competencies": ["learning", "adaptability"],
        },
    ],
}


def get_questions_from_bank(
    interview_type: str,
    difficulty: str,
    competencies: List[str],
    question_count: int,
) -> List[Dict[str, Any]]:
    """
    Select questions from the question bank based on criteria.

    This function picks the right questions for the interview based on:
    - What type of interview it is (technical, behavioral, etc.)
    - How difficult it should be
    - What skills we want to test
    - How many questions we need

    Args:
        interview_type: Type of interview (technical, behavioral, mixed)
        difficulty: Difficulty level (junior, mid, senior)
        competencies: List of competencies to assess
        question_count: Number of questions to select

    Returns:
        List of selected question dictionaries
    """
    # Get questions for the interview type
    available_questions = []

    if interview_type == "mixed":
        # For mixed interviews, combine technical and behavioral
        available_questions.extend(QUESTION_BANK.get("technical", []))
        available_questions.extend(QUESTION_BANK.get("behavioral", []))
    else:
        available_questions.extend(QUESTION_BANK.get(interview_type, []))

    # Filter by difficulty
    filtered_questions = [
        q for q in available_questions if q.get("difficulty") == difficulty
    ]

    # If no questions match exact difficulty, use all available
    if not filtered_questions:
        filtered_questions = available_questions

    # Filter by competencies if specified
    if competencies:
        competency_questions = []
        for q in filtered_questions:
            question_competencies = q.get("competencies", [])
            # If question matches any of the required competencies, include it
            if any(comp in question_competencies for comp in competencies):
                competency_questions.append(q)

        if competency_questions:
            filtered_questions = competency_questions

    # Select up to question_count questions
    selected = filtered_questions[:question_count]

    logger.info(
        f"Selected {len(selected)} questions from {len(available_questions)} available "
        f"for {interview_type} interview at {difficulty} level"
    )

    return selected


class GenerateQuestionsStep(InterviewStep):
    """
    Generate interview questions from the question bank.

    This step picks the right questions for this interview based on the
    interview type, difficulty, and what skills we want to test.
    """

    def __init__(self):
        super().__init__(
            name="generate_questions",
            description="Generate interview questions from question bank based on criteria",
        )

    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute question generation.

        Args:
            state: Current workflow state containing interview_config

        Returns:
            Updated state with selected_questions and question_bank
        """
        # Validate required state
        if not self.validate_state(state, ["interview_config"]):
            return self.set_error(state, "Missing required state: interview_config")

        interview_config = state.get("interview_config", {})

        interview_type = interview_config.get("interview_type", "mixed")
        difficulty = interview_config.get("difficulty_level", "mid")
        competencies = interview_config.get("competencies", [])
        question_count = interview_config.get("question_count", 5)

        logger.info(
            f"📝 Generating questions: type={interview_type}, "
            f"difficulty={difficulty}, count={question_count}"
        )

        # Get questions from the question bank
        selected_questions = get_questions_from_bank(
            interview_type=interview_type,
            difficulty=difficulty,
            competencies=competencies,
            question_count=question_count,
        )

        state["question_bank"] = QUESTION_BANK
        state["selected_questions"] = selected_questions
        state = self.update_status(state, "questions_generated")

        logger.info(f"✅ Generated {len(selected_questions)} questions")

        return state
