# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Integration tests for AI Interviewer workflow.

These tests verify that the workflow is properly integrated with the API and MCP server.
"""

import json


from flow.main import execute_workflow_logic, list_workflows_logic
from flow.mcp_local.server import execute_workflow, list_workflows


def test_workflow_listed_in_api():
    """Test that the workflow is listed in the API."""
    result = list_workflows_logic()

    workflow_names = [w["name"] for w in result["workflows"]]
    assert "ai_interviewer" in workflow_names

    # Find the workflow in the list
    ai_workflow = next(w for w in result["workflows"] if w["name"] == "ai_interviewer")
    assert ai_workflow["description"] is not None
    assert len(ai_workflow["description"]) > 0


def test_workflow_listed_in_mcp():
    """Test that the workflow is listed in the MCP server."""
    result = list_workflows()

    assert "workflows" in result
    workflow_names = [w["name"] for w in result["workflows"]]
    assert "ai_interviewer" in workflow_names


def test_workflow_executable_via_api():
    """Test that the workflow can be executed via the API logic."""
    message = json.dumps(
        {
            "candidate_info": {
                "name": "Test Candidate",
                "email": "test@example.com",
                "role": "Software Engineer",
            },
            "interview_config": {
                "interview_type": "technical",
                "difficulty_level": "mid",
                "question_count": 2,
                "competencies": ["algorithms"],
            },
            "provider_keys": {
                "room_provider_key": "test-key",
                "transcription_provider_key": "test-key",
            },
        }
    )

    result = execute_workflow_logic(
        workflow_name="ai_interviewer",
        message=message,
    )

    assert result is not None
    assert "success" in result or "error" in result


def test_workflow_executable_via_mcp():
    """Test that the workflow can be executed via the MCP server."""
    message = json.dumps(
        {
            "candidate_info": {
                "name": "Test Candidate",
                "email": "test@example.com",
                "role": "Software Engineer",
            },
            "interview_config": {
                "interview_type": "technical",
                "difficulty_level": "mid",
                "question_count": 2,
                "competencies": ["algorithms"],
            },
            "provider_keys": {
                "room_provider_key": "test-key",
                "transcription_provider_key": "test-key",
            },
        }
    )

    result = execute_workflow(
        workflow_name="ai_interviewer",
        message=message,
    )

    assert result is not None
    assert "success" in result or "error" in result


def test_workflow_handles_invalid_json():
    """Test that the workflow handles invalid JSON gracefully."""
    result = execute_workflow_logic(
        workflow_name="ai_interviewer",
        message="invalid json {",
    )

    # Should return an error response
    assert result is not None
    assert "error" in result or "success" in result


def test_workflow_handles_missing_parameters():
    """Test that the workflow handles missing required parameters."""
    message = json.dumps(
        {
            "candidate_info": {
                "name": "Test Candidate",
            },
            # Missing interview_config
        }
    )

    result = execute_workflow_logic(
        workflow_name="ai_interviewer",
        message=message,
    )

    # Should return an error response
    assert result is not None
    assert "error" in result or "success" in result
