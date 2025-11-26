# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Basic tests for AI Interviewer Workflow.

These tests verify that the workflow can be instantiated and basic functionality works.
"""

import pytest

from flow.workflows.ai_interviewer import AIInterviewerWorkflow
from flow.workflows import get_workflow, get_workflows


def test_workflow_import():
    """Test that the workflow can be imported."""
    from flow.workflows.ai_interviewer import AIInterviewerWorkflow

    assert AIInterviewerWorkflow is not None


def test_workflow_instantiation():
    """Test that the workflow can be instantiated."""
    workflow = AIInterviewerWorkflow()

    assert workflow is not None
    assert workflow.name == "ai_interviewer"
    assert workflow.description is not None
    # Recording and transcription steps removed - now handled client-side
    assert len(workflow.steps) == 7


def test_workflow_registered():
    """Test that the workflow is registered in the workflow registry."""
    workflows = get_workflows()

    assert "ai_interviewer" in workflows
    assert isinstance(workflows["ai_interviewer"], AIInterviewerWorkflow)


def test_workflow_get_by_name():
    """Test that the workflow can be retrieved by name."""
    workflow = get_workflow("ai_interviewer")

    assert workflow is not None
    assert workflow.name == "ai_interviewer"


def test_workflow_has_all_steps():
    """Test that the workflow has all required steps."""
    workflow = AIInterviewerWorkflow()

    expected_steps = [
        "configure_agent",
        "generate_questions",
        "conduct_interview",
        "process_transcript",
        "extract_insights",
        "generate_summary",
        "package_results",
    ]

    for step_name in expected_steps:
        assert step_name in workflow.steps, f"Missing step: {step_name}"

    # Verify recording/transcription steps are NOT in the workflow
    # (they're now handled client-side in meeting.html)
    assert (
        "start_recording" not in workflow.steps
    ), "start_recording should not be in workflow"
    assert (
        "start_transcript" not in workflow.steps
    ), "start_transcript should not be in workflow"


def test_workflow_graph_builds():
    """Test that the workflow graph can be built."""
    workflow = AIInterviewerWorkflow()

    assert workflow.graph is not None


@pytest.mark.asyncio
async def test_workflow_execute_with_minimal_input():
    """Test that the workflow can execute with minimal valid input."""
    workflow = AIInterviewerWorkflow()

    context = {
        "candidate_info": {
            "name": "Test Candidate",
            "email": "test@example.com",
            "role": "Software Engineer",
        },
        "interview_config": {
            "interview_type": "technical",
            "difficulty_level": "mid",
            "question_count": 3,
            "competencies": ["algorithms"],
        },
        "provider_keys": {
            "room_provider_key": "test-key",
            "transcription_provider_key": "test-key",
        },
    }

    result = await workflow.execute_async(context)

    # The workflow should complete (even if with simulated data)
    assert result is not None
    assert "success" in result
    # Note: This might fail if providers aren't implemented, but structure should work
    assert "workflow" in result
    assert result["workflow"] == "ai_interviewer"
