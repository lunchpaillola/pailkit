# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Basic tests for individual interview workflow steps.

These tests verify that each step can be instantiated and executed with valid input.
"""

import pytest

from flow.steps.interview import (
    ConfigureAgentStep,
    ConductInterviewStep,
    CreateRoomStep,
    ExtractInsightsStep,
    GenerateQuestionsStep,
    GenerateSummaryStep,
    PackageResultsStep,
    ProcessTranscriptStep,
    StartRecordingStep,
)


@pytest.mark.asyncio
async def test_create_room_step():
    """Test CreateRoomStep."""
    step = CreateRoomStep()
    state = {
        "session_id": "test-session-123",
        "provider_keys": {
            "room_provider_key": "test-key",
            "room_provider": "daily",
        },
        "processing_status": "session_initialized",
    }

    result = await step.execute(state)

    assert result["room_id"] is not None
    assert result["room_url"] is not None
    assert result["processing_status"] == "room_created"


@pytest.mark.asyncio
async def test_configure_agent_step():
    """Test ConfigureAgentStep."""
    step = ConfigureAgentStep()
    state = {
        "candidate_info": {
            "name": "Test Candidate",
            "role": "Software Engineer",
            "experience_years": 5,
        },
        "interview_config": {
            "interview_type": "technical",
            "difficulty_level": "mid",
        },
        "processing_status": "room_created",
    }

    result = await step.execute(state)

    assert result["interviewer_persona"] is not None
    assert result["interviewer_context"] is not None
    assert "Software Engineer" in result["interviewer_persona"]
    assert result["processing_status"] == "ai_configured"


@pytest.mark.asyncio
async def test_start_recording_step():
    """Test StartRecordingStep."""
    step = StartRecordingStep()
    state = {
        "room_id": "test-room-123",
        "provider_keys": {
            "transcription_provider_key": "test-key",
        },
        "processing_status": "ai_configured",
    }

    result = await step.execute(state)

    assert result["recording_id"] is not None
    assert result["transcription_id"] is not None
    assert result["processing_status"] == "recording_started"


@pytest.mark.asyncio
async def test_generate_questions_step():
    """Test GenerateQuestionsStep."""
    step = GenerateQuestionsStep()
    state = {
        "interview_config": {
            "interview_type": "technical",
            "difficulty_level": "mid",
            "competencies": ["algorithms"],
            "question_count": 2,
        },
        "processing_status": "recording_started",
    }

    result = await step.execute(state)

    assert len(result["selected_questions"]) > 0
    assert result["question_bank"] is not None
    assert result["processing_status"] == "questions_generated"


@pytest.mark.asyncio
async def test_conduct_interview_step():
    """Test ConductInterviewStep."""
    step = ConductInterviewStep()
    state = {
        "session_id": "test-session-123",
        "selected_questions": [
            {"id": "q1", "question": "What is a stack?"},
            {"id": "q2", "question": "What is a queue?"},
        ],
        "processing_status": "questions_generated",
    }

    result = await step.execute(state)

    assert result["interview_transcript"] is not None
    assert "Interviewer:" in result["interview_transcript"]
    assert result["processing_status"] == "interview_completed"


@pytest.mark.asyncio
async def test_process_transcript_step():
    """Test ProcessTranscriptStep."""
    step = ProcessTranscriptStep()
    state = {
        "interview_transcript": "Interviewer: What is a stack?\n\nCandidate: A stack is a data structure...",
        "selected_questions": [
            {"id": "q1", "question": "What is a stack?"},
        ],
        "processing_status": "interview_completed",
    }

    result = await step.execute(state)

    assert len(result["qa_pairs"]) > 0
    assert result["qa_pairs"][0]["question"] is not None
    assert result["qa_pairs"][0]["answer"] is not None
    assert result["processing_status"] == "transcript_processed"


@pytest.mark.asyncio
async def test_extract_insights_step():
    """Test ExtractInsightsStep."""
    step = ExtractInsightsStep()
    state = {
        "qa_pairs": [
            {
                "question": "What is a stack?",
                "answer": "A stack is a data structure...",
                "question_id": "q1",
            },
        ],
        "interview_config": {
            "competencies": ["algorithms"],
        },
        "processing_status": "transcript_processed",
    }

    result = await step.execute(state)

    assert result["insights"] is not None
    assert "overall_score" in result["insights"]
    assert "competency_scores" in result["insights"]
    assert "question_assessments" in result["insights"]
    assert result["processing_status"] == "insights_extracted"


@pytest.mark.asyncio
async def test_generate_summary_step():
    """Test GenerateSummaryStep."""
    step = GenerateSummaryStep()
    state = {
        "candidate_info": {
            "name": "Test Candidate",
            "role": "Software Engineer",
        },
        "insights": {
            "overall_score": 7.5,
            "competency_scores": {"algorithms": 8.0},
            "strengths": ["Strong problem-solving"],
            "weaknesses": ["Could improve communication"],
            "question_assessments": [],
        },
        "qa_pairs": [
            {
                "question": "What is a stack?",
                "answer": "A stack is a data structure...",
            },
        ],
        "processing_status": "insights_extracted",
    }

    result = await step.execute(state)

    assert result["candidate_summary"] is not None
    assert "Test Candidate" in result["candidate_summary"]
    assert result["processing_status"] == "summary_generated"


@pytest.mark.asyncio
async def test_package_results_step():
    """Test PackageResultsStep."""
    step = PackageResultsStep()
    state = {
        "session_id": "test-session-123",
        "candidate_info": {"name": "Test Candidate"},
        "room_url": "https://example.com/room",
        "recording_id": "rec-123",
        "transcription_id": "trans-123",
        "interview_transcript": "Full transcript...",
        "qa_pairs": [],
        "insights": {},
        "candidate_summary": "Summary...",
        "processing_status": "summary_generated",
    }

    result = await step.execute(state)

    assert result["results"] is not None
    assert result["results"]["session_id"] == "test-session-123"
    assert result["results"]["candidate_info"] is not None
    assert result["processing_status"] == "completed"
