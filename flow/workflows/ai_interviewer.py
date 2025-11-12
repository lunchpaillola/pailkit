# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
AI Interviewer Workflow

This workflow orchestrates a complete AI-powered interview process using modular steps.
Each step is implemented as a separate, testable unit in flow/steps/interview/.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph

from flow.steps.interview import (
    ConfigureAgentStep,
    ConductInterviewStep,
    CreateRoomStep,
    ExtractInsightsStep,
    GenerateQuestionsStep,
    GenerateSummaryStep,
    InitializeSessionStep,
    PackageResultsStep,
    ProcessTranscriptStep,
    StartRecordingStep,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Type Definitions
# ============================================================================


class InterviewState(TypedDict):
    """
    State dictionary for the interview workflow.

    This holds all the data that flows through the workflow steps.
    Think of it like a shared workspace where each step can read and write data.
    """

    # Input parameters
    candidate_info: Dict[str, Any]  # Candidate name, email, role, etc.
    interview_config: Dict[str, Any]  # Interview type, duration, difficulty, etc.
    provider_keys: Dict[str, str]  # API keys for room and transcription providers

    # Workflow execution state
    processing_status: str  # Current step status
    error: Optional[str]  # Error message if something goes wrong

    # Room and session data
    room_id: Optional[str]  # Created video room ID
    room_url: Optional[str]  # URL for joining the room
    session_id: Optional[str]  # Unique interview session ID

    # AI Interviewer configuration
    interviewer_persona: Optional[str]  # AI persona description
    interviewer_context: Optional[str]  # Additional context for the AI

    # Recording and transcription
    recording_id: Optional[str]  # Recording session ID
    transcription_id: Optional[str]  # Transcription session ID

    # Questions and interview flow
    question_bank: List[Dict[str, Any]]  # Available questions
    selected_questions: List[Dict[str, Any]]  # Questions selected for this interview
    current_question_index: int  # Which question we're on
    interview_transcript: Optional[str]  # Full interview transcript

    # Processing results
    qa_pairs: List[Dict[str, Any]]  # Separated questions and answers
    insights: Dict[str, Any]  # Extracted insights and assessments
    candidate_summary: Optional[str]  # Generated candidate profile

    # Final results
    results: Optional[Dict[str, Any]]  # Packaged final results


# ============================================================================
# Workflow Node Wrappers
# ============================================================================


def create_step_wrapper(step_instance: Any):
    """
    Create a wrapper function for a step instance to use in LangGraph.

    **Simple Explanation:**
    LangGraph needs regular functions, but our steps are class instances.
    This wrapper converts a step instance into a function that LangGraph can use.

    Args:
        step_instance: An instance of an InterviewStep

    Returns:
        A function that can be used as a LangGraph node
    """

    async def wrapper(state: InterviewState) -> InterviewState:
        """Wrapper function that calls the step's execute method."""
        return await step_instance.execute(state)

    return wrapper


# ============================================================================
# Workflow Class
# ============================================================================


class AIInterviewerWorkflow:
    """
    AI Interviewer Workflow using LangGraph and modular steps.

    This workflow orchestrates a complete AI-powered interview process:
    1. Creates a video room with recording/transcription
    2. Configures an AI interviewer persona
    3. Generates questions from a question bank
    4. Conducts the interview (AI-led)
    5. Processes the transcript
    6. Extracts insights and assesses competencies
    7. Generates a candidate summary
    8. Packages all results

    **Simple Explanation:**
    This is like a recipe that runs all the steps of an AI interview
    automatically. You give it candidate info and interview settings,
    and it handles everything from start to finish. Each step is a
    separate, testable module that can be developed independently.
    """

    name = "ai_interviewer"
    description = "Conduct AI-powered interviews with automated question generation, recording, transcription, and candidate assessment"

    def __init__(self):
        """Initialize the workflow and build the LangGraph graph."""
        # Initialize all step instances
        self.steps = {
            "initialize_session": InitializeSessionStep(),
            "create_room": CreateRoomStep(),
            "configure_agent": ConfigureAgentStep(),
            "start_recording": StartRecordingStep(),
            "generate_questions": GenerateQuestionsStep(),
            "conduct_interview": ConductInterviewStep(),
            "process_transcript": ProcessTranscriptStep(),
            "extract_insights": ExtractInsightsStep(),
            "generate_summary": GenerateSummaryStep(),
            "package_results": PackageResultsStep(),
        }

        # Build the workflow graph
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        """
        Build the LangGraph workflow graph.

        **Simple Explanation:**
        This creates a flowchart of all the steps. Each step is a "node"
        and they're connected in order. LangGraph will run them one after
        another, passing data between them.

        Returns:
            Compiled LangGraph workflow
        """
        # Create the state graph
        workflow = StateGraph(InterviewState)

        # Add all the workflow nodes using step wrappers
        for step_name, step_instance in self.steps.items():
            workflow.add_node(step_name, create_step_wrapper(step_instance))

        # Define the flow - connect nodes in order
        workflow.set_entry_point("initialize_session")
        workflow.add_edge("initialize_session", "create_room")
        workflow.add_edge("create_room", "configure_agent")
        workflow.add_edge("configure_agent", "start_recording")
        workflow.add_edge("start_recording", "generate_questions")
        workflow.add_edge("generate_questions", "conduct_interview")
        workflow.add_edge("conduct_interview", "process_transcript")
        workflow.add_edge("process_transcript", "extract_insights")
        workflow.add_edge("extract_insights", "generate_summary")
        workflow.add_edge("generate_summary", "package_results")
        workflow.add_edge("package_results", END)

        # Compile and return the graph
        return workflow.compile()

    async def execute_async(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the workflow asynchronously.

        **Simple Explanation:**
        This runs the entire workflow. You pass in the candidate info,
        interview config, and API keys, and it runs all the steps.

        Args:
            context: Dictionary containing:
                - candidate_info: Candidate information
                - interview_config: Interview configuration
                - provider_keys: API keys for providers

        Returns:
            Dictionary with execution results
        """
        try:
            # Extract parameters from context
            candidate_info = context.get("candidate_info", {})
            interview_config = context.get("interview_config", {})
            provider_keys = context.get("provider_keys", {})

            # Prepare initial state
            initial_state: InterviewState = {
                "candidate_info": candidate_info,
                "interview_config": interview_config,
                "provider_keys": provider_keys,
                "processing_status": "starting",
                "error": None,
                "room_id": None,
                "room_url": None,
                "session_id": None,
                "interviewer_persona": None,
                "interviewer_context": None,
                "recording_id": None,
                "transcription_id": None,
                "question_bank": [],
                "selected_questions": [],
                "current_question_index": 0,
                "interview_transcript": None,
                "qa_pairs": [],
                "insights": {},
                "candidate_summary": None,
                "results": None,
            }

            logger.info(
                f"🚀 Starting AI Interviewer workflow for "
                f"{candidate_info.get('name', 'Unknown')}"
            )

            # Execute the workflow
            result = await self.graph.ainvoke(initial_state)

            # Check for errors
            if result.get("error"):
                return {
                    "success": False,
                    "error": result["error"],
                    "processing_status": result.get("processing_status"),
                    "workflow": self.name,
                }

            return {
                "success": True,
                "response": "Interview workflow completed successfully",
                "results": result.get("results"),
                "processing_status": result.get("processing_status"),
                "workflow": self.name,
            }

        except Exception as e:
            logger.error(f"❌ Error in AI Interviewer workflow: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "workflow": self.name,
            }

    def execute(
        self, message: str, user_id: str | None = None, channel_id: str | None = None
    ) -> Dict[str, Any]:
        """
        Execute the workflow (synchronous wrapper for compatibility).

        This method implements the Workflow protocol interface, allowing
        the workflow to be used with the existing workflow system.

        **Simple Explanation:**
        This is a wrapper that makes the async workflow work with the
        existing system that expects a synchronous execute method. It properly
        handles event loops without needing nest-asyncio.

        Args:
            message: JSON string containing workflow parameters
            user_id: Optional user identifier
            channel_id: Optional channel identifier

        Returns:
            Dictionary with execution results
        """
        try:
            # Parse JSON message
            params = json.loads(message)

            # Extract required parameters
            candidate_info = params.get("candidate_info", {})
            interview_config = params.get("interview_config", {})
            provider_keys = params.get("provider_keys", {})

            # Validate required parameters
            if not candidate_info:
                return {
                    "success": False,
                    "error": "Missing required parameter: candidate_info",
                }

            if not interview_config:
                return {
                    "success": False,
                    "error": "Missing required parameter: interview_config",
                }

            # Prepare context
            context = {
                "candidate_info": candidate_info,
                "interview_config": interview_config,
                "provider_keys": provider_keys,
            }

            # Run the async workflow
            # Handle different async contexts properly
            try:
                # Try to get the current event loop
                # If we get here, we're in an async context with a running loop
                asyncio.get_running_loop()
                # Create a new event loop in a thread
                import concurrent.futures

                def run_in_thread():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(self.execute_async(context))
                    finally:
                        new_loop.close()

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_in_thread)
                    return future.result()
            except RuntimeError:
                # No running event loop, we can use asyncio.run()
                return asyncio.run(self.execute_async(context))

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON message: {e}")
            return {
                "success": False,
                "error": f"Invalid JSON in message: {str(e)}",
            }
        except Exception as e:
            logger.error(f"Error executing workflow: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
            }
