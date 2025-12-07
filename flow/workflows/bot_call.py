# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Bot Call Workflow

This workflow orchestrates the complete bot call process:
1. Join bot to the room (via bot_service.start_bot())
2. Wait for bot to finish (participant_left event)
3. Process transcript using ProcessTranscriptStep (includes email/webhook)

The workflow uses LangGraph to pause after joining the bot and automatically
resume when the bot finishes, ensuring the full transcript processing pipeline
runs (including email sending and webhook triggering).
"""

import logging
import uuid
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from flow.db import get_postgres_checkpointer
from flow.steps.interview.bot_service import bot_service
from flow.steps.interview.process_transcript import ProcessTranscriptStep

logger = logging.getLogger(__name__)

# Simple Explanation: Shared checkpointer instance for all workflow instances
# This uses Supabase (PostgreSQL) to persist workflow state, so checkpoints
# survive server restarts and work across multiple instances (like Fly.io).
# Falls back to MemorySaver if Supabase is not configured.
_shared_checkpointer = None


def _get_checkpointer():
    """
    Get the shared checkpointer instance, creating it if needed.

    Simple Explanation: This function returns a checkpointer that stores
    workflow state. It tries to use Supabase (PostgreSQL) first, and falls
    back to in-memory storage if Supabase is not configured.
    """
    global _shared_checkpointer

    if _shared_checkpointer is None:
        # Try to get Postgres checkpointer from Supabase
        checkpointer = get_postgres_checkpointer()

        if checkpointer is None:
            # Fallback to MemorySaver if Supabase is not configured
            logger.warning(
                "⚠️ Supabase checkpointer not available - using in-memory checkpointer. "
                "Workflow state will not persist across server restarts. "
                "Set SUPABASE_DB_URL or SUPABASE_DB_PASSWORD to enable persistent checkpoints."
            )
            from langgraph.checkpoint.memory import MemorySaver

            checkpointer = MemorySaver()

        _shared_checkpointer = checkpointer

    return _shared_checkpointer


# Simple Explanation: BotCallState defines what data the workflow tracks
# This includes room information, bot configuration, and workflow thread ID
class BotCallState(TypedDict):
    """State for the bot call workflow."""

    room_url: str  # Full Daily.co room URL
    token: str | None  # Optional meeting token
    room_name: str  # Room name extracted from URL
    bot_config: dict[str, Any]  # Bot configuration (prompt, name, video mode, etc.)
    bot_id: str | None  # Bot ID for tracking the session
    workflow_thread_id: str | None  # Thread ID for workflow resumption
    transcript_text: str | None  # Transcript text (from bot or Daily.co)
    error: str | None  # Error message if something goes wrong


class BotCallWorkflow:
    """
    Bot Call Workflow using LangGraph.

    This workflow orchestrates:
    1. Starting a bot in a Daily.co room
    2. Waiting for the bot to finish
    3. Processing the transcript (Q&A parsing, insights, email, webhook)

    The workflow pauses after starting the bot and resumes automatically
    when the bot finishes (via participant_left event handler).
    """

    name = "bot_call"
    description = "Orchestrate bot call: join bot → process transcript"

    def __init__(self):
        """Initialize the workflow with a shared checkpointer for state persistence."""
        # Simple Explanation: We use a shared checkpointer instance so that
        # checkpoints created when starting a workflow are available when
        # resuming the workflow later (even from a different workflow instance).
        # The checkpointer uses Supabase (PostgreSQL) to persist state, so it
        # works across server restarts and multiple instances.
        self.checkpointer = _get_checkpointer()
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        """
        Build the LangGraph workflow graph.

        Simple Explanation: This creates a workflow with two steps:
        1. join_bot: Start the bot (this pauses the workflow)
        2. process_transcript: Process the transcript when bot finishes

        The workflow automatically pauses after join_bot and resumes when
        the bot finishes (participant_left event).
        """
        # Create the workflow graph
        workflow = StateGraph(BotCallState)

        # Add nodes (steps in the workflow)
        workflow.add_node("join_bot", self._join_bot_node)
        workflow.add_node("process_transcript", self._process_transcript_node)

        # Set the entry point (where the workflow starts)
        workflow.set_entry_point("join_bot")

        # Define the flow: join_bot → process_transcript → END
        workflow.add_edge("join_bot", "process_transcript")
        workflow.add_edge("process_transcript", END)

        # Compile the graph with checkpointer and interrupt after join_bot
        # Simple Explanation: interrupt_after means the workflow will pause
        # after the join_bot step completes. It will resume when we call
        # graph.ainvoke() again with the same thread_id.
        return workflow.compile(
            interrupt_after=["join_bot"],
            checkpointer=self.checkpointer,
        )

    async def _join_bot_node(self, state: BotCallState) -> BotCallState:
        """
        Join bot node: Start the bot in the room.

        Simple Explanation: This step starts the bot by calling bot_service.start_bot().
        The bot will join the room and start transcribing. After this step,
        the workflow pauses and waits for the bot to finish.

        Args:
            state: Current workflow state

        Returns:
            Updated state with bot_id and workflow_thread_id
        """
        logger.info("🤖 Starting bot in join_bot node")
        logger.info(f"   Room: {state.get('room_name')}")

        try:
            # Generate a unique thread_id for this workflow instance
            # Simple Explanation: The thread_id is like a unique ID for this
            # workflow run. We'll use it to resume the workflow later.
            thread_id = state.get("workflow_thread_id")
            if not thread_id:
                thread_id = str(uuid.uuid4())
                logger.info(f"   Generated workflow_thread_id: {thread_id}")

            # Store thread_id in session data so we can resume the workflow
            # when the bot finishes
            from flow.db import get_session_data, save_session_data

            room_name = state.get("room_name")
            if room_name:
                session_data = get_session_data(room_name) or {}
                session_data["workflow_thread_id"] = thread_id
                session_data["workflow_paused"] = True
                save_session_data(room_name, session_data)
                logger.info("   ✅ Saved workflow_thread_id to session data")

            # Start the bot
            # Simple Explanation: bot_service.start_bot() starts the bot in the
            # background. The bot will join the room and start transcribing.
            bot_id = state.get("bot_id")
            success = await bot_service.start_bot(
                room_url=state["room_url"],
                token=state.get("token") or "",
                bot_config=state["bot_config"],
                room_name=room_name,
                bot_id=bot_id,
            )

            if not success:
                error_msg = "Failed to start bot"
                logger.error(f"   ❌ {error_msg}")
                state["error"] = error_msg
                return state

            logger.info(f"   ✅ Bot started successfully (bot_id: {bot_id})")

            # Update state with thread_id
            state["workflow_thread_id"] = thread_id
            state["bot_id"] = bot_id

            # The workflow will pause here (interrupt_after=["join_bot"])
            # It will resume when we call graph.ainvoke() again with the same thread_id
            logger.info("   ⏸️  Workflow paused - waiting for bot to finish")

            return state

        except Exception as e:
            error_msg = f"Error in join_bot node: {str(e)}"
            logger.error(f"   ❌ {error_msg}", exc_info=True)
            state["error"] = error_msg
            return state

    async def _process_transcript_node(self, state: BotCallState) -> BotCallState:
        """
        Process transcript node: Run the full transcript processing pipeline.

        Simple Explanation: This step processes the transcript after the bot finishes.
        It calls ProcessTranscriptStep.execute() which handles:
        - Parsing transcript to Q&A pairs
        - Extracting insights
        - Generating summary
        - Sending email (if configured)
        - Triggering webhook (if configured)

        Args:
            state: Current workflow state

        Returns:
            Updated state with processing results
        """
        logger.info("📝 Processing transcript in process_transcript node")
        logger.info(f"   Room: {state.get('room_name')}")

        try:
            room_name = state.get("room_name")
            if not room_name:
                error_msg = "Missing room_name in state"
                logger.error(f"   ❌ {error_msg}")
                state["error"] = error_msg
                return state

            # Create state for ProcessTranscriptStep
            # Simple Explanation: ProcessTranscriptStep expects a state dictionary
            # with room_name. It will automatically check the database for transcript_text
            # (the bot saves it there as it transcribes). We don't need to pass the
            # transcript in the state - ProcessTranscriptStep handles retrieving it.
            process_state = {
                "room_name": room_name,
                # ProcessTranscriptStep will check database for transcript_text automatically
                # If transcript_text is in DB (bot case), it uses that
                # If not, it can download from Daily.co using transcript_id (non-bot case)
            }

            # Execute ProcessTranscriptStep
            # Simple Explanation: This runs the complete transcript processing
            # pipeline: Q&A parsing, insights, summary, email, webhook.
            logger.info("   🔄 Calling ProcessTranscriptStep.execute()...")
            process_step = ProcessTranscriptStep()
            result = await process_step.execute(process_state)

            # Check for errors
            if result.get("error"):
                error_msg = result.get("error")
                logger.error(f"   ❌ ProcessTranscriptStep error: {error_msg}")
                state["error"] = error_msg
                return state

            # Update state with results
            # Simple Explanation: ProcessTranscriptStep returns the processed transcript
            # and other results. We update our state with these results.
            if result.get("transcript_text"):
                state["transcript_text"] = result.get("transcript_text")
            logger.info("   ✅ Transcript processing complete")

            # Clear workflow_paused flag
            if room_name:
                from flow.db import get_session_data, save_session_data

                session_data = get_session_data(room_name) or {}
                session_data["workflow_paused"] = False
                save_session_data(room_name, session_data)

            return state

        except Exception as e:
            error_msg = f"Error in process_transcript node: {str(e)}"
            logger.error(f"   ❌ {error_msg}", exc_info=True)
            state["error"] = error_msg
            return state

    async def execute_async(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the workflow asynchronously.

        Simple Explanation: This starts the workflow. It creates a new workflow
        run with a unique thread_id and begins execution. The workflow will
        pause after starting the bot and can be resumed later.

        Args:
            context: Workflow context containing:
                - room_url: Full Daily.co room URL
                - token: Optional meeting token
                - bot_config: Bot configuration dictionary
                - bot_id: Optional bot ID for tracking

        Returns:
            Result dictionary with status and workflow information
        """
        try:
            # Extract context
            room_url = context.get("room_url")
            if not room_url:
                return {
                    "success": False,
                    "error": "Missing required field: room_url",
                }

            token = context.get("token")
            room_name = context.get("room_name") or room_url.split("/")[-1]
            bot_config = context.get("bot_config", {})
            bot_id = context.get("bot_id")

            # Create initial state
            # Simple Explanation: This is the starting state for the workflow.
            # It contains all the information needed to start the bot.
            initial_state: BotCallState = {
                "room_url": room_url,
                "token": token,
                "room_name": room_name,
                "bot_config": bot_config,
                "bot_id": bot_id,
                "workflow_thread_id": None,
                "transcript_text": None,
                "error": None,
            }

            # Generate thread_id for this workflow run
            thread_id = str(uuid.uuid4())
            initial_state["workflow_thread_id"] = thread_id

            # Create config for LangGraph
            # Simple Explanation: The config tells LangGraph which thread_id
            # to use for this workflow run. This allows us to resume it later.
            config = {"configurable": {"thread_id": thread_id}}

            # Start the workflow
            # Simple Explanation: This begins the workflow execution. It will
            # run the join_bot node and then pause (because of interrupt_after).
            logger.info(f"🚀 Starting BotCallWorkflow (thread_id: {thread_id})")
            result = await self.graph.ainvoke(initial_state, config=config)

            # Check for errors
            if result.get("error"):
                return {
                    "success": False,
                    "error": result.get("error"),
                    "thread_id": thread_id,
                }

            # Return success
            return {
                "success": True,
                "thread_id": thread_id,
                "room_name": room_name,
                "room_url": room_url,
                "bot_id": bot_id,
                "message": "Bot started - workflow paused. Will resume when bot finishes.",
            }

        except Exception as e:
            logger.error(f"❌ Error executing BotCallWorkflow: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
            }
