# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""Result processor for handling bot completion and transcript processing."""

import logging
from datetime import datetime
from typing import Any, Dict

from flow.steps.agent_call.bot.transcript_handler import TranscriptHandler

logger = logging.getLogger(__name__)


class BotResultProcessor:
    """
    Processes bot results after completion.

    Simple Explanation: After a bot finishes transcribing, this class handles
    processing the transcript, extracting insights, and storing results.
    """

    def __init__(
        self, bot_config_map: Dict[str, Dict[str, Any]], bot_id_map: Dict[str, str]
    ):
        """
        Initialize the result processor.

        Args:
            bot_config_map: Map of room_name -> bot_config for checking processing options
            bot_id_map: Map of room_name -> bot_id for saving results to bot_sessions table
        """
        self.bot_config_map = bot_config_map
        self.bot_id_map = bot_id_map

    async def process_full_pipeline(
        self, room_name: str, transcript_handler: TranscriptHandler
    ) -> None:
        """
        Process transcript using the full ProcessTranscriptStep pipeline.

        Simple Explanation: After the bot finishes transcribing, we run the complete
        ProcessTranscriptStep which handles:
        1. Parsing transcript to extract Q&A pairs
        2. Extracting insights using AI analysis (if enabled)
        3. Generating candidate summary
        4. Sending email (if configured)
        5. Triggering webhook (if configured)
        6. Storing results in the database

        Args:
            room_name: Room name for this bot session
            transcript_handler: The transcript handler that collected the transcript
        """
        try:
            logger.info(
                f"🔄 Processing results with full pipeline for bot in room: {room_name}"
            )

            # Get transcript text from handler
            transcript_text = transcript_handler.transcript_text

            if not transcript_text:
                logger.warning(f"⚠️ No transcript text found for room {room_name}")
                return

            # Use ProcessTranscriptStep for the full pipeline
            # Simple Explanation: ProcessTranscriptStep.execute() handles the complete
            # processing pipeline including Q&A parsing, insights, summary, email, and webhook
            from flow.steps.agent_call.steps.process_transcript import (
                ProcessTranscriptStep,
            )

            # Create state for ProcessTranscriptStep
            # Simple Explanation: ProcessTranscriptStep expects room_name and will
            # automatically retrieve transcript_text from the database if not provided.
            # We also pass workflow_thread_id if available so processing status can be tracked per workflow run.
            from flow.db import get_session_data

            session_data = get_session_data(room_name) or {}
            workflow_thread_id = session_data.get("workflow_thread_id")

            state = {
                "room_name": room_name,
                "workflow_thread_id": workflow_thread_id,
                # ProcessTranscriptStep will check database for transcript_text automatically
                # The bot saves it there as it transcribes
            }

            # Execute the full pipeline
            logger.info(
                "   🔄 Calling ProcessTranscriptStep.execute() for full pipeline..."
            )
            process_step = ProcessTranscriptStep()
            result = await process_step.execute(state)

            # Check for errors
            if result.get("error"):
                logger.error(f"❌ ProcessTranscriptStep error: {result.get('error')}")
                return

            logger.info("   ✅ Full transcript processing pipeline complete")
            logger.info(f"      - Email sent: {result.get('email_sent', False)}")
            logger.info(f"      - Webhook sent: {result.get('webhook_sent', False)}")

        except Exception as e:
            logger.error(
                f"❌ Error processing bot results with full pipeline for room {room_name}: {e}",
                exc_info=True,
            )
            # Don't raise - we don't want to fail the bot cleanup if processing fails

    async def process_legacy(
        self, room_name: str, transcript_handler: TranscriptHandler
    ) -> None:
        """
        Process transcript and extract insights after bot finishes (legacy method).

        Simple Explanation: After the bot finishes transcribing, we automatically:
        1. Process the transcript to extract Q&A pairs
        2. Extract insights using AI analysis (if enabled)
        3. Store results in the database so they can be retrieved via the status endpoint

        Note: This method does NOT send emails or webhooks. Use process_full_pipeline
        for the complete pipeline including email and webhook.

        Args:
            room_name: Room name for this bot session
            transcript_handler: The transcript handler that collected the transcript
        """
        try:
            logger.info(f"🔄 Processing results for bot in room: {room_name}")

            # Get bot config to check if insights processing is enabled
            bot_config = self.bot_config_map.get(room_name, {})
            process_insights = bot_config.get("process_insights", True)

            # Get transcript text from handler
            transcript_text = transcript_handler.transcript_text

            if not transcript_text:
                logger.warning(f"⚠️ No transcript text found for room {room_name}")
                return

            # Create state dictionary for processing steps
            # Simple Explanation: The ProcessTranscriptStep and ExtractInsightsStep
            # expect a state dictionary with transcript and other data. We create
            # this state object and pass it through the processing steps.
            from flow.steps.agent_call.steps.process_transcript import (
                parse_transcript_to_qa_pairs,
            )
            from flow.steps.agent_call.steps.extract_insights import ExtractInsightsStep

            state = {
                "room_name": room_name,
                "interview_transcript": transcript_text,
            }

            # Parse transcript to extract Q&A pairs
            logger.info("📝 Parsing transcript to extract Q&A pairs...")
            qa_pairs = parse_transcript_to_qa_pairs(transcript_text)
            state["qa_pairs"] = qa_pairs
            logger.info(f"✅ Extracted {len(qa_pairs)} Q&A pairs")

            # Extract insights if enabled
            if process_insights:
                logger.info("🧠 Extracting insights...")
                extract_insights_step = ExtractInsightsStep()
                state = await extract_insights_step.execute(state)

                if state.get("error"):
                    logger.error(f"❌ Error extracting insights: {state.get('error')}")
                else:
                    logger.info("✅ Insights extracted successfully")

            # Save results to database
            # Simple Explanation: We save the transcript, Q&A pairs, and insights
            # to the database so they can be retrieved via the status endpoint.
            from flow.db import (
                get_session_data,
                save_session_data,
                get_bot_session_by_room_name,
                save_bot_session,
            )

            # Save to rooms table (for backwards compatibility)
            session_data = get_session_data(room_name) or {}
            session_data["transcript_text"] = transcript_text
            session_data["qa_pairs"] = qa_pairs
            if process_insights and state.get("insights"):
                session_data["insights"] = state["insights"]

            save_session_data(room_name, session_data)
            logger.info(
                f"✅ Saved processing results to rooms table for room: {room_name}"
            )

            # Also save to bot_sessions table if we have a bot_id
            # Simple Explanation: We also save results to the bot_sessions table
            # so the status endpoint can retrieve them directly by bot_id
            if room_name in self.bot_id_map:
                bot_id = self.bot_id_map[room_name]
                bot_session = get_bot_session_by_room_name(room_name)

                if bot_session and bot_session.get("bot_id") == bot_id:
                    # Update bot session with results
                    bot_session["status"] = "completed"
                    bot_session["completed_at"] = datetime.utcnow().isoformat() + "Z"
                    bot_session["transcript_text"] = transcript_text
                    bot_session["qa_pairs"] = qa_pairs
                    if process_insights and state.get("insights"):
                        bot_session["insights"] = state["insights"]

                    save_bot_session(bot_id, bot_session)
                    logger.info(
                        f"✅ Saved processing results to bot_sessions table for bot_id: {bot_id}"
                    )

        except Exception as e:
            logger.error(
                f"❌ Error processing bot results for room {room_name}: {e}",
                exc_info=True,
            )
            # Don't raise - we don't want to fail the bot cleanup if processing fails
