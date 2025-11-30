# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
AI Interviewer Workflow

This workflow orchestrates a complete AI-powered interview process using modular steps.
Each step is implemented as a separate, testable unit in flow/steps/interview/.

This workflow uses one_time_meeting.py as a subgraph for room creation:
1. Uses one_time_meeting workflow as a subgraph to create the room
   (with auto-start recording/transcription via URL parameters)
2. Continues with AI interviewer configuration and interview execution
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from flow.steps.interview import (
    CallVAPIStep,
    ConfigureAgentStep,
    ConductInterviewStep,
    ExtractInsightsStep,
    GenerateQuestionsStep,
    GenerateSummaryStep,
    PackageResultsStep,
    ProcessTranscriptStep,
)
from flow.workflows.one_time_meeting import (
    OneTimeMeetingState,
    OneTimeMeetingWorkflow,
)

logger = logging.getLogger(__name__)

# Shared checkpointer for all workflow instances
# This allows workflows to be resumed across different instances
_shared_checkpointer = None


def get_shared_checkpointer():
    """Get or create the shared checkpointer for workflow state persistence."""
    global _shared_checkpointer
    if _shared_checkpointer is None:
        _shared_checkpointer = MemorySaver()
    return _shared_checkpointer


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
    hosted_url: Optional[str]  # Hosted meeting.html URL
    room_name: Optional[str]  # Room name (extracted from URL, used for API calls)
    room_provider: Optional[str]  # Room provider name (e.g., "daily")
    meeting_token: Optional[str]  # Daily.co meeting token
    dialin_code: Optional[str]  # PIN code for dial-in (from Daily.co)
    vapi_call_id: Optional[str]  # VAPI call ID if VAPI calling is used
    vapi_call_created: bool  # Whether VAPI call was successfully created
    session_id: Optional[str]  # Unique interview session ID

    # AI Interviewer configuration
    interviewer_persona: Optional[str]  # AI persona description
    interviewer_context: Optional[str]  # Additional context for the AI

    # Recording and transcription
    recording_id: Optional[str]  # Recording session ID
    transcription_id: Optional[
        str
    ]  # Transcription session ID (deprecated, use transcription_session_id)
    transcription_session_id: Optional[str]  # Unique transcription session ID

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

    Args:
        step_instance: An instance of an InterviewStep

    Returns:
        A function that can be used as a LangGraph node
    """

    async def wrapper(state: InterviewState) -> InterviewState:
        """Wrapper function that calls the step's execute method."""
        return await step_instance.execute(state)

    return wrapper


def map_to_one_time_meeting_state(state: InterviewState) -> OneTimeMeetingState:
    """
    Map InterviewState to OneTimeMeetingState for the subgraph.

    Args:
        state: InterviewState from the parent workflow

    Returns:
        OneTimeMeetingState for the one_time_meeting subgraph
    """
    import uuid

    interview_config = state.get("interview_config", {})
    base_url = os.getenv("MEET_BASE_URL", "http://localhost:8001")
    session_id = state.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())

    return {
        "meeting_config": interview_config,  # Use interview_config as meeting_config
        "provider_keys": state.get("provider_keys", {}),
        "session_id": session_id,
        "meet_base_url": base_url,
        "processing_status": state.get("processing_status", "starting"),
        "error": state.get("error"),
        "room_id": state.get("room_id"),
        "room_name": state.get("room_name"),
        "room_url": state.get("room_url"),
        "hosted_url": None,
        "room_provider": None,
    }


def map_from_one_time_meeting_state(
    one_time_state: OneTimeMeetingState, parent_state: InterviewState
) -> InterviewState:
    """
    Map OneTimeMeetingState back to InterviewState after subgraph execution.

    Args:
        one_time_state: OneTimeMeetingState from the subgraph
        parent_state: Original InterviewState to preserve other fields

    Returns:
        Updated InterviewState with room information from subgraph
    """
    # Update parent state with room information from subgraph
    parent_state["room_id"] = one_time_state.get("room_id")
    parent_state["room_name"] = one_time_state.get("room_name")
    parent_state["room_url"] = one_time_state.get("room_url")
    parent_state["hosted_url"] = one_time_state.get("hosted_url")  # Include hosted URL
    parent_state["processing_status"] = one_time_state.get(
        "processing_status", parent_state.get("processing_status")
    )
    parent_state["error"] = one_time_state.get("error")

    # Preserve room_provider if it was set by the subgraph
    room_provider = one_time_state.get("room_provider")
    if room_provider:
        parent_state["room_provider"] = room_provider

    # Preserve VAPI-related fields from subgraph
    if one_time_state.get("meeting_token"):
        parent_state["meeting_token"] = one_time_state.get("meeting_token")
    if one_time_state.get("dialin_code"):
        parent_state["dialin_code"] = one_time_state.get("dialin_code")
    if one_time_state.get("vapi_call_id"):
        parent_state["vapi_call_id"] = one_time_state.get("vapi_call_id")
    parent_state["vapi_call_created"] = one_time_state.get("vapi_call_created", False)

    return parent_state


async def one_time_meeting_subgraph_wrapper(
    state: InterviewState,
) -> InterviewState:
    """
    Wrapper to execute one_time_meeting workflow as a subgraph.

    This function:
    1. Maps InterviewState to OneTimeMeetingState
    2. Executes the one_time_meeting graph
    3. Maps the result back to InterviewState

    Args:
        state: Current InterviewState

    Returns:
        Updated InterviewState with room creation results
    """
    # Create the one_time_meeting workflow instance
    one_time_workflow = OneTimeMeetingWorkflow()

    # Map state to one_time_meeting format
    one_time_state = map_to_one_time_meeting_state(state)

    # Execute the subgraph
    result_state = await one_time_workflow.graph.ainvoke(one_time_state)

    # Check for errors from subgraph
    if result_state.get("error"):
        state["error"] = result_state.get("error")
        state["processing_status"] = "error"
        return state

    # Build hosted_url using the same logic as one_time_meeting workflow
    # (since it's not in the graph state, only in the response)
    room_name = result_state.get("room_name")
    if room_name:
        from urllib.parse import urlencode

        base_url = os.getenv("MEET_BASE_URL", "http://localhost:8001")
        interview_config = state.get("interview_config", {})
        meeting_config = interview_config  # Use interview_config as meeting_config

        # Build query parameters
        query_params = {}
        auto_record = meeting_config.get(
            "autoRecord", meeting_config.get("auto_record", True)
        )
        auto_transcribe = meeting_config.get(
            "autoTranscribe", meeting_config.get("auto_transcribe", True)
        )

        # If bot is enabled, disable client-side autoTranscribe
        # because TranscriptProcessor handles transcription automatically (both user and bot)
        bot_enabled = meeting_config.get("bot", {}).get("enabled", False)
        if bot_enabled:
            auto_transcribe = False
            logger.info(
                "🤖 Bot enabled - disabling client-side autoTranscribe "
                "(TranscriptProcessor will handle transcription)"
            )

        if auto_record:
            query_params["autoRecord"] = "true"
        if auto_transcribe:
            query_params["autoTranscribe"] = "true"

        # Add meeting token if available
        meeting_token = result_state.get("meeting_token")
        if meeting_token:
            query_params["token"] = meeting_token

        # Add bot parameter if enabled
        if meeting_config.get("bot", {}).get("enabled"):
            query_params["bot"] = "true"

        # Add branding parameters
        if "theme" in meeting_config:
            query_params["theme"] = meeting_config["theme"]
        if "accentColor" in meeting_config or "accent_color" in meeting_config:
            query_params["accentColor"] = meeting_config.get(
                "accentColor"
            ) or meeting_config.get("accent_color")
        if "logoText" in meeting_config or "logo_text" in meeting_config:
            query_params["logoText"] = meeting_config.get(
                "logoText"
            ) or meeting_config.get("logo_text")

        # Build hosted URL
        if query_params:
            hosted_url = f"{base_url}/meet/{room_name}?{urlencode(query_params)}"
        else:
            hosted_url = f"{base_url}/meet/{room_name}"

        result_state["hosted_url"] = hosted_url

    # Map results back to InterviewState
    return map_from_one_time_meeting_state(result_state, state)


# ============================================================================
# Workflow Class
# ============================================================================


class AIInterviewerWorkflow:
    """
    AI Interviewer Workflow using LangGraph and modular steps.

    This workflow uses one_time_meeting.py as a subgraph and orchestrates
    a complete AI-powered interview process:
    1. Creates a video room using one_time_meeting workflow as a subgraph
       (with auto-start recording/transcription via URL parameters)
    2. Configures an AI interviewer persona
    3. Generates questions from a question bank
    4. Conducts the interview (AI-led)
    5. Processes the transcript
    6. Extracts insights and assesses competencies
    7. Generates a candidate summary
    8. Packages all results

    Note: Recording and transcription are now handled client-side in meeting.html
    using Daily.co's callFrame.startRecording() and callFrame.startTranscription()
    methods, triggered automatically via URL parameters (autoRecord=true, autoTranscribe=true).
    """

    name = "ai_interviewer"
    description = "Conduct AI-powered interviews with automated question generation, recording, transcription, and candidate assessment"

    def __init__(self):
        """Initialize the workflow and build the LangGraph graph."""
        # Initialize step instances (excluding create_room, which is handled by subgraph)
        # Recording and transcription are now handled client-side in meeting.html
        self.steps = {
            "call_vapi": CallVAPIStep(),  # Step 2: Make VAPI outbound call (if enabled)
            "configure_agent": ConfigureAgentStep(),  # Step 3: Configure AI interviewer
            "generate_questions": GenerateQuestionsStep(),  # Step 4: Generate interview questions
            "conduct_interview": ConductInterviewStep(),  # Step 5: Conduct the interview
            "process_transcript": ProcessTranscriptStep(),  # Step 6: Process transcript into Q&A pairs
            "extract_insights": ExtractInsightsStep(),  # Step 7: Extract insights and assessments
            "generate_summary": GenerateSummaryStep(),  # Step 8: Generate candidate summary
            "package_results": PackageResultsStep(),  # Step 9: Package final results
        }

        # Use shared checkpointer for workflow state persistence
        # This allows workflows to be resumed across different instances
        self.checkpointer = get_shared_checkpointer()

        # Build the workflow graph
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        """
        Build the LangGraph workflow graph with one_time_meeting as a subgraph.

        Returns:
            Compiled LangGraph workflow
        """
        # Create the state graph
        workflow = StateGraph(InterviewState)

        # Add one_time_meeting workflow as a subgraph node
        # This handles room creation using the one_time_meeting workflow
        workflow.add_node("create_room", one_time_meeting_subgraph_wrapper)

        # Add all other workflow nodes using step wrappers
        for step_name, step_instance in self.steps.items():
            workflow.add_node(step_name, create_step_wrapper(step_instance))

        # Define the flow - connect nodes in order
        # Flow starts with one_time_meeting subgraph for room creation
        # Recording and transcription are handled client-side via URL parameters
        workflow.set_entry_point("create_room")  # Start with one_time_meeting subgraph
        workflow.add_edge(
            "create_room", "call_vapi"
        )  # After room creation, make VAPI call (if enabled)
        workflow.add_edge(
            "call_vapi", "configure_agent"
        )  # Then configure agent (or skip if using VAPI)
        workflow.add_edge("configure_agent", "generate_questions")
        workflow.add_edge("generate_questions", "conduct_interview")
        # After conduct_interview, we need to pause and wait for transcript webhook
        # The workflow will interrupt here and wait for transcript_id
        workflow.add_edge("conduct_interview", "process_transcript")
        workflow.add_edge("process_transcript", "extract_insights")
        workflow.add_edge("extract_insights", "generate_summary")
        workflow.add_edge("generate_summary", "package_results")
        workflow.add_edge("package_results", END)

        # Compile with interrupt after conduct_interview and checkpointing
        # This pauses the workflow until transcript_id is available (via webhook)
        # Checkpointing allows us to resume using a thread_id
        return workflow.compile(
            interrupt_after=["conduct_interview"],
            checkpointer=self.checkpointer,
        )

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

            # Generate session ID and thread ID for tracking
            import uuid

            session_id = str(uuid.uuid4())
            thread_id = (
                f"interview_{session_id}"  # Unique thread ID for this workflow instance
            )

            # Prepare initial state
            initial_state: InterviewState = {
                "candidate_info": candidate_info,
                "interview_config": interview_config,
                "provider_keys": provider_keys,
                "processing_status": "starting",
                "error": None,
                "room_id": None,
                "room_url": None,
                "hosted_url": None,
                "room_name": None,
                "room_provider": None,
                "meeting_token": None,
                "dialin_code": None,
                "vapi_call_id": None,
                "vapi_call_created": False,
                "session_id": session_id,
                "interviewer_persona": None,
                "interviewer_context": None,
                "recording_id": None,
                "transcription_id": None,
                "transcription_session_id": None,
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

            # Execute the workflow with thread_id (will pause at interrupt_after conduct_interview)
            # The thread_id allows us to resume this specific workflow instance later
            config = {"configurable": {"thread_id": thread_id}}
            result = await self.graph.ainvoke(initial_state, config=config)

            # Check for errors
            if result.get("error"):
                return {
                    "success": False,
                    "error": result["error"],
                    "processing_status": result.get("processing_status"),
                    "workflow": self.name,
                }

            # Check if workflow paused (waiting for transcript)
            # If transcript_id is not in state, workflow is paused waiting for webhook
            if not result.get("transcript_id") and result.get("processing_status") in [
                "interview_completed",
                "waiting_for_transcript",
            ]:
                # Workflow is paused - store thread_id for resuming later
                room_name = result.get("room_name")
                if room_name:
                    from flow.db import get_session_data, save_session_data

                    # Store thread_id in session data so we can resume this workflow
                    session_data = get_session_data(room_name) or {}
                    session_data["workflow_thread_id"] = thread_id
                    session_data["workflow_paused"] = True
                    save_session_data(room_name, session_data)
                    logger.info(f"💾 Stored thread_id {thread_id} for room {room_name}")

                # Return paused state with all room info
                return {
                    "success": True,
                    "response": "Interview workflow paused - waiting for transcript",
                    "room_url": result.get("room_url"),
                    "hosted_url": result.get("hosted_url"),  # Include hosted URL
                    "room_name": result.get("room_name"),
                    "session_id": result.get("session_id"),
                    "thread_id": thread_id,
                    "processing_status": "waiting_for_transcript",
                    "workflow": self.name,
                    "note": "Workflow will resume automatically when transcript is ready",
                    # Include the full result state so endpoint can access hosted_url
                    "_state": result,
                }

            # Workflow completed
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

            # Extract required parameters - support both old and new field names
            candidate_info = params.get("candidate_info") or params.get(
                "participant_info", {}
            )
            interview_config = params.get("interview_config") or params.get(
                "meeting_config", {}
            )
            provider_keys = params.get("provider_keys", {})

            # Validate required parameters
            if not candidate_info:
                return {
                    "success": False,
                    "error": "Missing required parameter: candidate_info or participant_info",
                }

            if not interview_config:
                return {
                    "success": False,
                    "error": "Missing required parameter: interview_config or meeting_config",
                }

            # Prepare context - include both old and new field names for compatibility
            context = {
                "candidate_info": candidate_info,  # Old name for backwards compatibility
                "participant_info": candidate_info,  # New generic name
                "interview_config": interview_config,  # Old name for backwards compatibility
                "meeting_config": interview_config,  # New generic name
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
