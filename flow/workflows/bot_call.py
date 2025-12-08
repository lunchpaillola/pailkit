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

# Note: We import get_async_postgres_checkpointer in _get_checkpointer() to avoid circular imports
from flow.steps.interview.bot_service import bot_service
from flow.steps.interview.process_transcript import ProcessTranscriptStep

logger = logging.getLogger(__name__)

# Simple Explanation: Shared async checkpointer instance for all workflow instances
# This uses Supabase (PostgreSQL) to persist workflow state, so checkpoints
# survive server restarts and work across multiple instances (like Fly.io).
# Falls back to MemorySaver if Supabase is not configured.
# The checkpointer is created asynchronously and kept alive for the application lifecycle.
_shared_checkpointer = None
_checkpointer_lock = None


async def _get_checkpointer():
    """
    Get the shared checkpointer instance, creating it if needed.

    Simple Explanation: This function returns a checkpointer that stores
    workflow state. It tries to use Supabase (PostgreSQL) first, and falls
    back to in-memory storage if Supabase is not configured.
    """
    global _shared_checkpointer, _checkpointer_lock

    # Import asyncio only when needed
    if _checkpointer_lock is None:
        import asyncio

        _checkpointer_lock = asyncio.Lock()

    # Use lock to ensure only one checkpointer is created
    async with _checkpointer_lock:
        if _shared_checkpointer is None:
            # Try to get async Postgres checkpointer from Supabase
            from flow.db import get_async_postgres_checkpointer

            checkpointer = await get_async_postgres_checkpointer()

            if checkpointer is None:
                # Fallback to MemorySaver if Supabase is not configured
                logger.warning(
                    "⚠️ Supabase async checkpointer not available - using in-memory checkpointer. "
                    "Workflow state will not persist across server restarts. "
                    "Set SUPABASE_DB_URL or SUPABASE_DB_PASSWORD to enable persistent checkpoints."
                )
                from langgraph.checkpoint.memory import MemorySaver

                checkpointer = MemorySaver()

            _shared_checkpointer = checkpointer
            logger.info("✅ Async checkpointer initialized")

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

    def __init__(self, checkpointer=None):
        """
        Initialize the workflow with a checkpointer for state persistence.

        **Simple Explanation:**
        We use a shared checkpointer instance so that checkpoints created when
        starting a workflow are available when resuming the workflow later
        (even from a different workflow instance). The checkpointer uses
        Supabase (PostgreSQL) to persist state, so it works across server
        restarts and multiple instances.

        Args:
            checkpointer: Optional checkpointer instance. If not provided,
                will be created asynchronously when needed.
        """
        # Store checkpointer - will be set asynchronously if not provided
        self._checkpointer = checkpointer
        self._graph = None  # Will be built asynchronously

    async def _ensure_checkpointer(self):
        """
        Ensure the checkpointer is initialized.

        **Simple Explanation:**
        This method ensures the checkpointer is created and ready to use.
        It's called before building the graph or executing the workflow.
        """
        if self._checkpointer is None:
            self._checkpointer = await _get_checkpointer()

    async def _ensure_graph(self):
        """
        Ensure the graph is built with the checkpointer.

        **Simple Explanation:**
        This method ensures the graph is built with the checkpointer.
        It's called before executing the workflow.
        """
        if self._graph is None:
            await self._ensure_checkpointer()
            self._graph = self._build_graph()

    @property
    async def checkpointer(self):
        """Get the checkpointer, initializing it if needed."""
        await self._ensure_checkpointer()
        return self._checkpointer

    @property
    async def graph(self):
        """Get the graph, building it if needed."""
        await self._ensure_graph()
        return self._graph

    def _build_graph(self) -> Any:
        """
        Build the LangGraph workflow graph.

        **Simple Explanation:**
        This creates a workflow with two steps:
        1. join_bot: Start the bot (this pauses the workflow)
        2. process_transcript: Process the transcript when bot finishes

        The workflow automatically pauses after join_bot and resumes when
        the bot finishes (participant_left event).

        **Note:** This method assumes self._checkpointer is already set.
        Use _ensure_checkpointer() before calling this.
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
            checkpointer=self._checkpointer,
        )

    async def _join_bot_node(self, state: BotCallState) -> BotCallState:
        """
        Join bot node: Start the bot in the room.

        **Simple Explanation:**
        This step starts the bot by calling bot_service.start_bot().
        The bot will join the room and start transcribing. After this step,
        the workflow pauses and waits for the bot to finish.

        **Note:** When resuming from a checkpoint, LangGraph will automatically
        skip to the next step (process_transcript) after the interrupt point.
        We don't need to check for resume here - LangGraph handles it automatically.

        Args:
            state: Current workflow state

        Returns:
            Updated state with bot_id and workflow_thread_id
        """
        logger.info("🤖 Starting bot in join_bot node")
        logger.info(f"   Room: {state.get('room_name')}")

        try:
            # Use the thread_id from state (set by execute_async when starting a new workflow)
            # Simple Explanation: Each API call generates a NEW thread_id in execute_async,
            # ensuring each workflow run is independent. We use that thread_id here.
            thread_id = state.get("workflow_thread_id")
            if not thread_id:
                # Fallback: generate one if not set (shouldn't happen in normal flow)
                thread_id = str(uuid.uuid4())
                logger.warning(f"   ⚠️ No thread_id in state, generated: {thread_id}")
            else:
                logger.info(f"   Using workflow_thread_id from state: {thread_id}")

            # Store thread_id in session data so we can resume the workflow
            # when the bot finishes. Also copy important fields from session_data
            # into the workflow state so they're available in the checkpoint.
            from flow.db import (
                get_session_data,
                save_session_data,
                save_workflow_thread_data,
            )

            room_name = state.get("room_name")
            if room_name:
                # Load session data and update with NEW workflow_thread_id
                # Simple Explanation: We save the NEW thread_id to session_data so we can
                # resume this specific workflow when the bot finishes. This overwrites any
                # old workflow_thread_id from previous runs, ensuring each API call starts fresh.
                session_data = get_session_data(room_name) or {}
                old_thread_id = session_data.get("workflow_thread_id")
                if old_thread_id and old_thread_id != thread_id:
                    logger.info(
                        f"   🔄 Replacing old workflow_thread_id: {old_thread_id} with new: {thread_id}"
                    )
                session_data["workflow_thread_id"] = thread_id
                session_data["workflow_paused"] = True
                save_session_data(room_name, session_data)
                logger.info("   ✅ Saved NEW workflow_thread_id to session data")

                # Copy important fields from session_data into workflow_thread_data
                # Simple Explanation: This ensures email_results_to, candidate_name, etc.
                # are available in the workflow checkpoint, so they're available when resuming.
                # We save to workflow_threads table so the data persists with the workflow.
                workflow_thread_data = {
                    "workflow_thread_id": thread_id,
                    "room_name": room_name,
                    "room_url": state.get("room_url"),
                    "bot_id": state.get("bot_id"),
                    "bot_config": state.get("bot_config"),
                    # Copy from session_data so they're in the checkpoint
                    "email_results_to": session_data.get("email_results_to"),
                    "webhook_callback_url": session_data.get("webhook_callback_url"),
                    "candidate_name": session_data.get("candidate_name"),
                    "candidate_email": session_data.get("candidate_email"),
                    "interview_type": session_data.get("interview_type"),
                    "position": session_data.get("position"),
                    "interviewer_context": session_data.get("interviewer_context"),
                    "analysis_prompt": session_data.get("analysis_prompt"),
                    "summary_format_prompt": session_data.get("summary_format_prompt"),
                }
                save_workflow_thread_data(thread_id, workflow_thread_data)
                logger.info(
                    "   ✅ Copied session_data fields to workflow_thread_data (email, candidate_name, etc.)"
                )

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
            # We also pass workflow_thread_id so processing status can be tracked per workflow run.
            process_state = {
                "room_name": room_name,
                "workflow_thread_id": state.get("workflow_thread_id"),
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
            graph = await self.graph
            result = await graph.ainvoke(initial_state, config=config)

            # Check for errors
            if result.get("error"):
                return {
                    "success": False,
                    "error": result.get("error"),
                    "thread_id": thread_id,
                }

            # After the workflow pauses, get the current state to extract checkpoint_id
            # Simple Explanation: When the workflow pauses after join_bot, LangGraph
            # creates a checkpoint. We need to get the checkpoint_id from the state
            # so we can resume from the exact same checkpoint later.
            try:
                # Get the state after the workflow pauses
                # Simple Explanation: graph.get_state() returns the current state snapshot
                # which includes the checkpoint_id in its config. This is a synchronous call.
                state = graph.get_state(config)

                # Extract checkpoint_id from the state's config
                # Simple Explanation: The checkpoint_id is stored in state.config["configurable"]["checkpoint_id"]
                # This tells LangGraph exactly which checkpoint to resume from.
                checkpoint_id = state.config["configurable"]["checkpoint_id"]

                if checkpoint_id:
                    logger.info(f"   ✅ Captured checkpoint_id: {checkpoint_id}")

                    # Save checkpoint_id to session_data so it's available when resuming
                    # Simple Explanation: We save the checkpoint_id alongside workflow_thread_id
                    # so when the bot finishes, we can resume from the exact checkpoint.
                    from flow.db import get_session_data, save_session_data

                    session_data = get_session_data(room_name) or {}
                    session_data["checkpoint_id"] = checkpoint_id
                    save_session_data(room_name, session_data)
                    logger.info("   ✅ Saved checkpoint_id to session_data")
                else:
                    logger.warning(
                        "   ⚠️ No checkpoint_id found in state - workflow may restart from beginning"
                    )
            except Exception as e:
                logger.warning(
                    f"   ⚠️ Error capturing checkpoint_id: {e} - workflow may restart from beginning",
                    exc_info=True,
                )

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
