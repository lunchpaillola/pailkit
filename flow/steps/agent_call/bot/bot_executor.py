# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""Bot executor for running the Pipecat bot pipeline."""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from pipecat.transports.daily.transport import DailyTransport

from pipecat.audio.interruptions.min_words_interruption_strategy import (
    MinWordsInterruptionStrategy,
)
from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import (
    LocalSmartTurnAnalyzerV3,
)
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
)
from pipecat.processors.aggregators.llm_response import (
    LLMUserAggregatorParams,
)
from pipecat.processors.transcript_processor import TranscriptProcessor
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.openai.tts import OpenAITTSService
from pipecat.transports.daily.transport import DailyParams, DailyTransport

from flow.steps.agent_call.bot.animation import TalkingAnimation
from flow.steps.agent_call.bot.metrics_processor import UsageMetricsProcessor
from flow.steps.agent_call.bot.result_processor import BotResultProcessor
from flow.steps.agent_call.bot.speaker_tracking import SpeakerTrackingProcessor
from flow.steps.agent_call.bot.transcript_handler import TranscriptHandler
from flow.steps.agent_call.bot.video_frames import load_bot_video_frames

logger = logging.getLogger(__name__)


class BotExecutor:
    """
    Executes the bot pipeline and handles bot runtime.

    Simple Explanation: This class sets up and runs the complete bot pipeline,
    including transport, STT, LLM, TTS, and event handlers. It manages the
    bot's lifecycle from start to finish.
    """

    def __init__(
        self,
        result_processor: BotResultProcessor,
        transport_map: Dict[str, "DailyTransport"],
    ):
        """
        Initialize the bot executor.

        Args:
            result_processor: Processor for handling bot results after completion
            transport_map: Map to store transport references for cleanup
        """
        self.result_processor = result_processor
        self.transport_map = transport_map

    async def run(
        self,
        room_url: str,
        token: str,
        bot_config: Dict[str, Any],
        room_name: str,
        workflow_thread_id: Optional[str] = None,
    ) -> None:
        """
        Run the Pipecat bot directly without subprocess.

        Args:
            room_url: Full Daily.co room URL
            token: Meeting token for authentication
            bot_config: Bot configuration dictionary
            room_name: Room name for saving transcript to database
            workflow_thread_id: Optional workflow thread ID to associate with this bot session
        """
        # Initialize bot_join_time to None - will be set when bot actually starts
        bot_join_time = None

        try:

            # Get bot prompt from config - this defines what the bot should do/say
            # If not provided, use a generic default
            bot_prompt = bot_config.get(
                "bot_prompt",
                bot_config.get(
                    "system_message",
                    "You are a helpful AI assistant. "
                    "Your output will be spoken aloud, so keep language natural and easy to say. "
                    "Do not use special characters. "
                    "Have a natural conversation with the participant.",
                ),
            )

            # Add voice-specific instructions to any prompt
            system_message = f"""{bot_prompt}

IMPORTANT: Your output will be spoken aloud, so:
- Keep language natural and conversational
- Do not use special characters, markdown, or formatting
- Speak in complete sentences
- Wait for the participant to finish speaking before responding
- Keep responses concise and clear"""

            bot_name = bot_config.get("name", "PailBot")

            transport = DailyTransport(
                room_url,
                token,
                bot_name,
                DailyParams(
                    audio_in_enabled=True,
                    audio_out_enabled=True,
                    video_out_enabled=True,  # Enable video output (static or animated based on config)
                    video_out_width=1280,  # Match reference implementation
                    video_out_height=720,  # Match reference implementation
                    transcription_enabled=False,  # We use Deepgram STT instead of Daily.co transcription
                    vad_analyzer=SileroVADAnalyzer(params=VADParams(stop_secs=0.2)),
                    turn_analyzer=LocalSmartTurnAnalyzerV3(params=SmartTurnParams()),
                ),
            )

            # Store transport reference so we can explicitly leave the room during cleanup
            self.transport_map[room_name] = transport

            logger.info(
                f"Bot transport initialized for room: {room_url}, bot_name: {bot_name}"
            )

            # Load participants immediately after transport creation
            # This ensures we know all participants even if they joined before the bot
            initial_participants = transport.participants() or {}
            participants_map = {}
            for pid, pdata in initial_participants.items():
                if pid == "local":
                    continue
                session_id = pdata.get("session_id") or pid
                # Extract name from nested info object - Daily.co always provides info.userName
                info = pdata.get("info", {})
                name = info.get("userName") or f"Participant {session_id}"
                participants_map[session_id] = {
                    "session_id": session_id,
                    "name": name,
                    "user_id": pdata.get("user_id"),
                }
            logger.info(f"📋 Participants loaded at startup: {participants_map}")

            # Use OpenAI for both LLM and TTS
            llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"), model="gpt-4.1")
            tts = OpenAITTSService(
                api_key=os.getenv("OPENAI_API_KEY"),
                voice="alloy",
                interruptions_allowed=True,
                interruption_strategies=[MinWordsInterruptionStrategy(min_words=1)],
            )

            # Use Deepgram for Speech-to-Text (STT) to transcribe user speech
            # Enable speaker diarization to identify different speakers
            # utterances=True is required for proper speaker segments
            stt = DeepgramSTTService(
                api_key=os.getenv("DEEPGRAM_API_KEY"),
                model="nova-2",
                diarize=True,
                utterances=True,
            )
            logger.info("🎤 Deepgram STT initialized with diarization and utterances")
            logger.info("   🔍 DEBUG: Deepgram STT configuration:")
            logger.info("      - model: nova-2")
            logger.info("      - diarize: True")
            logger.info("      - utterances: True")
            logger.info(f"      - STT service type: {type(stt)}")

            messages = [
                {
                    "role": "system",
                    "content": system_message,
                },
            ]

            context = LLMContext(messages)
            # Configure aggregation parameters to prevent bot repetition
            # Simple Explanation: Deepgram STT sends partial transcripts as the user speaks.
            # Without proper aggregation, each partial transcript triggers an LLM call,
            # causing the bot to repeat responses. These parameters increase the wait time
            # before sending transcripts to the LLM, ensuring only complete user turns are processed.
            user_aggregator_params = LLMUserAggregatorParams(
                aggregation_timeout=1.0,  # Wait 1 second for additional transcription content (default: 0.5)
                turn_emulated_vad_timeout=1.0,  # Wait 1 second for emulated VAD (default: 0.8)
                enable_emulated_vad_interruptions=False,  # Don't allow emulated VAD to interrupt bot
            )
            context_aggregator = LLMContextAggregatorPair(
                context, user_params=user_aggregator_params
            )

            # Create transcript processor and handler
            transcript = TranscriptProcessor()

            # Get workflow_thread_id for this room (if workflow is running)
            # Simple Explanation: We need to find the workflow_thread_id so we can save
            # the transcript to workflow_threads table. Use the passed parameter if available,
            # otherwise look for a paused workflow for this room as fallback.
            if not workflow_thread_id:
                try:
                    from flow.db import get_workflow_threads_by_room_name

                    threads = get_workflow_threads_by_room_name(room_name)
                    # Get the most recent paused workflow thread
                    for thread in threads:
                        if thread.get("workflow_paused"):
                            workflow_thread_id = thread.get("workflow_thread_id")
                            break
                except Exception as e:
                    logger.debug(
                        f"Could not find workflow_thread_id for room {room_name}: {e}"
                    )

            # Create transcript handler first (needed for speaker tracker)
            transcript_handler = TranscriptHandler(
                room_name=room_name,
                bot_name=bot_name,
                speaker_tracker=None,  # Will be set after creation
                transport=transport,
                workflow_thread_id=workflow_thread_id,
            )

            # Create speaker tracking processor to extract speaker IDs from frames
            # Pass transcript_handler reference for participant order mapping
            speaker_tracker = SpeakerTrackingProcessor(
                transcript_handler=transcript_handler
            )

            # Now set the speaker_tracker reference in transcript_handler
            transcript_handler.speaker_tracker = speaker_tracker
            # Set participants_map that was loaded at startup
            transcript_handler.participants_map = participants_map
            logger.info(
                f"📝 Transcript will be saved to database for room: {room_name}\n"
                "   - User speech: Deepgram STT (from pipeline) with speaker diarization\n"
                "   - Bot speech: TranscriptProcessor (from TTS input)"
            )

            # Load video frames based on bot configuration
            quiet_frame, talking_frame = load_bot_video_frames(bot_config)
            ta = TalkingAnimation(quiet_frame=quiet_frame, talking_frame=talking_frame)

            # Create metrics processor to track LLM usage costs in real-time
            metrics_processor = UsageMetricsProcessor(
                workflow_thread_id=workflow_thread_id
            )

            # Build pipeline with Deepgram STT and TranscriptProcessor
            pipeline_components = [
                transport.input(),  # Transport user input
                stt,  # Deepgram STT - converts user speech to text
                speaker_tracker,  # Track speaker IDs from frames
                transcript.user(),  # User transcripts (from STT)
                context_aggregator.user(),  # User responses
                llm,  # LLM
                metrics_processor,  # Track LLM usage metrics and costs
                tts,  # TTS
                ta,  # Talking animation (for video output)
                transport.output(),  # Transport bot output
                transcript.assistant(),  # Assistant transcripts (after transport.output())
                context_aggregator.assistant(),  # Assistant spoken responses
            ]

            pipeline = Pipeline(pipeline_components)

            task = PipelineTask(
                pipeline,
                params=PipelineParams(
                    enable_metrics=True,
                    enable_usage_metrics=True,
                ),
            )
            # Queue the initial frame if available
            if ta.quiet_frame is not None:
                await task.queue_frame(ta.quiet_frame)

            @transport.event_handler("on_participant_joined")
            async def on_participant_joined(transport, participant):
                """Log when any participant (including bot) joins and update participants map."""
                participant_id = participant.get("id", "unknown")
                participant_name = participant.get("user_name", "unknown")
                is_local = participant.get("local", False)
                session_id = participant.get("session_id") or participant_id

                logger.info(
                    f"🔵 Participant joined - ID: {participant_id}, Name: {participant_name}, Local: {is_local}, Session ID: {session_id}"
                )

                # Update participants map
                # Get all participants from Daily.co
                try:
                    participants = transport.participants()
                    if not participants:
                        logger.warning(
                            "⚠️ No participants returned from transport.participants()"
                        )
                        return

                    # Identify bot's session_id (local participant or match by bot_name)
                    bot_session_id = None
                    if is_local:
                        bot_session_id = session_id
                    else:
                        # Check if this participant matches bot_name
                        if participant_name == bot_name:
                            bot_session_id = session_id

                    if bot_session_id:
                        transcript_handler.bot_session_id = bot_session_id

                    # Build participants_map for all NON-bot participants
                    participants_map = {}
                    for pid, pdata in participants.items():
                        if pid == "local":
                            # Skip local participant (it's the bot)
                            continue
                        p_session_id = pdata.get("session_id") or pid
                        # Skip bot if we've identified it
                        if bot_session_id and p_session_id == bot_session_id:
                            continue
                        # Skip if this is the bot by name
                        # Extract name from nested info object - Daily.co always provides info.userName
                        info = pdata.get("info", {})
                        p_name = info.get("userName") or ""
                        if p_name == bot_name:
                            continue

                        participants_map[p_session_id] = {
                            "name": p_name,
                            "user_name": p_name,  # Add for consistency/backward compatibility
                            "user_id": pdata.get("user_id"),
                            "session_id": p_session_id,
                            "id": pid,
                        }

                    transcript_handler.participants_map = participants_map
                    # Update participant join order (preserve existing order, add new participants)
                    for session_id in participants_map.keys():
                        if session_id not in transcript_handler.participant_join_order:
                            transcript_handler.participant_join_order.append(session_id)
                    logger.info(
                        f"📋 Participants map updated: {len(participants_map)} participant(s)"
                    )

                    # Log participant counts after updating participants map
                    try:
                        counts = transport.participant_counts()
                        if counts:
                            present = counts.get("present", 0)
                            hidden = counts.get("hidden", 0)
                            total = present + hidden
                            logger.info(
                                f"👥 Participant counts after join - Present: {present}, Hidden: {hidden}, Total: {total}"
                            )
                        else:
                            logger.debug("Participant counts not available after join")
                    except Exception as count_error:
                        logger.warning(
                            f"⚠️ Error getting participant counts after join: {count_error}"
                        )
                except Exception as e:
                    logger.warning(
                        f"⚠️ Error updating participants map: {e}", exc_info=True
                    )

            # Register event handler for active speaker changes
            @transport.event_handler("on_active_speaker_changed")
            async def on_active_speaker_changed(transport, event):
                """Handle active speaker change events to map Deepgram speaker IDs to Daily.co participants."""
                active_speaker = (
                    event.get("activeSpeaker", {})
                    if isinstance(event, dict)
                    else getattr(event, "activeSpeaker", {})
                )

                # Try to get peer_id from activeSpeaker.peerId first
                peer_id = (
                    active_speaker.get("peerId")
                    if isinstance(active_speaker, dict)
                    else getattr(active_speaker, "peerId", None)
                )

                # Fallback: Use event.id (Daily.co participant ID) if peerId not available
                if not peer_id:
                    event_id = (
                        event.get("id")
                        if isinstance(event, dict)
                        else getattr(event, "id", None)
                    )
                    if event_id:
                        peer_id = event_id
                    else:
                        logger.debug(
                            "No peerId or event.id in on_active_speaker_changed event"
                        )
                        return

                # Get current Deepgram speaker ID
                deepgram_speaker_id = speaker_tracker.get_current_speaker_id()

                if deepgram_speaker_id is not None:
                    speaker_tracker.map_speaker_to_participant(
                        deepgram_speaker_id, peer_id
                    )
                    logger.debug(
                        f"Mapped Deepgram speaker {deepgram_speaker_id} → Daily.co session_id {peer_id}"
                    )

            # Register event handler for transcript updates from TranscriptProcessor
            @transcript.event_handler("on_transcript_update")
            async def on_transcript_update(processor, frame):
                await transcript_handler.on_transcript_update(processor, frame)

            @transport.event_handler("on_first_participant_joined")
            async def on_first_participant_joined(transport, participant):
                participant_id = participant.get("id", "unknown")
                logger.info(f"🟢 FIRST participant joined: {participant_id}")
                # Note: We no longer use capture_participant_transcription here
                # because TranscriptProcessor handles transcription automatically
                # Kick off the conversation with a greeting first
                # This tells the LLM to introduce itself before starting the interview
                messages.append(
                    {
                        "role": "system",
                        "content": "Please introduce yourself warmly to the user. Greet them and let them know you're here to conduct an interview. Wait for them to respond before starting with the interview questions.",
                    }
                )
                logger.info("📤 Queuing LLMRunFrame to start conversation...")
                await task.queue_frames([LLMRunFrame()])
                logger.info("✅ LLMRunFrame queued successfully")

            @transport.event_handler("participant-counts-updated")
            async def on_participant_counts_updated(transport, event):
                """
                Handle participant-counts-updated event from Daily.co.

                Simple Explanation: This event fires when participants join or leave.
                We log the current participant counts for debugging and monitoring.
                """
                # Get participant counts from transport
                # Simple Explanation: participant_counts() returns information about
                # how many participants are currently in the room (present and hidden).
                counts = transport.participant_counts()
                if counts:
                    present = counts.get("present", 0)
                    hidden = counts.get("hidden", 0)
                    logger.info(
                        f"👥 Participant counts updated - Present: {present}, Hidden: {hidden}"
                    )
                else:
                    logger.debug("Participant counts not available")

            @transport.event_handler("on_participant_left")
            async def on_participant_left(transport, participant, reason):
                """
                Handle participant left event.

                Simple Explanation: When a participant (including the bot) leaves,
                we check if there's a workflow waiting to resume. If so, we resume
                it to continue processing the transcript. Otherwise, we process
                results directly (legacy behavior).
                """
                participant_id = participant.get("id", "unknown")
                logger.info(f"Participant left: {participant_id}, reason: {reason}")

                # Check participant counts before deciding whether to leave
                # Simple Explanation: We only want the bot to leave when it's the only
                # present participant remaining (present count = 1). If other participants
                # are still present, we should stay in the room and continue the conversation.
                # Hidden participants don't affect this decision - only present participants matter.
                try:
                    counts = transport.participant_counts()
                    if counts:
                        present = counts.get("present", 0)
                        hidden = counts.get("hidden", 0)
                        logger.info(
                            f"👥 Participant counts after leave - Present: {present}, Hidden: {hidden}"
                        )

                        # Only check present count for decision - hidden participants don't matter
                        # Simple Explanation: If present count > 1, it means there are other
                        # present participants besides the bot. We should stay in the room and not
                        # proceed with cleanup/workflow resume. Hidden participants are ignored.
                        if present > 1:
                            logger.info(
                                f"✅ Bot staying in room - {present} present participant(s) still in room (including bot)"
                            )
                            return  # Early return - don't proceed with cleanup
                        elif present == 1:
                            logger.info(
                                "🚪 Only bot remains as present participant - proceeding with cleanup and workflow resume"
                            )
                        else:
                            # Count is 0 or None - this shouldn't happen, but log a warning
                            logger.warning(
                                f"⚠️ Unexpected present participant count: {present} - proceeding with cleanup anyway"
                            )
                    else:
                        # If participant_counts() returns None, log warning but proceed (fail-safe)
                        logger.warning(
                            "⚠️ Could not get participant counts - proceeding with cleanup (fail-safe behavior)"
                        )
                except Exception as count_error:
                    # If there's an error getting counts, log warning but proceed (fail-safe)
                    logger.warning(
                        f"⚠️ Error getting participant counts: {count_error} - proceeding with cleanup (fail-safe behavior)"
                    )

                # Check if there's a workflow waiting to resume
                # Simple Explanation: If a workflow was started via the bot_call
                # workflow, it will have a workflow_thread_id. First try to use the
                # workflow_thread_id stored in transcript_handler (most reliable), then
                # check session_data (for backward compatibility), and finally lookup by room_name.
                from flow.db import get_session_data, get_workflow_thread_data

                # First try to use workflow_thread_id from transcript_handler (most reliable)
                workflow_thread_id = (
                    transcript_handler.workflow_thread_id
                    if transcript_handler.workflow_thread_id
                    else None
                )

                # If not found, try to get workflow_thread_id from session_data (for backward compatibility)
                if not workflow_thread_id:
                    session_data = get_session_data(room_name) or {}
                    workflow_thread_id = session_data.get("workflow_thread_id")

                # If still not found, try to find it from workflow_threads by room_name (fallback)
                if not workflow_thread_id:
                    from flow.db import get_workflow_threads_by_room_name

                    threads = get_workflow_threads_by_room_name(room_name)
                    # Get the most recent paused workflow thread
                    for thread in threads:
                        if thread.get("workflow_paused"):
                            workflow_thread_id = thread.get("workflow_thread_id")
                            break

                if workflow_thread_id:
                    # Resume the workflow
                    # Simple Explanation: The workflow paused after starting the bot.
                    # Now that the bot has finished, we resume it to continue to the
                    # process_transcript step.
                    logger.info(
                        f"🔄 Resuming workflow with thread_id: {workflow_thread_id}"
                    )
                    try:
                        from flow.workflows.bot_call import BotCallWorkflow

                        workflow = BotCallWorkflow()

                        # Retrieve checkpoint_id from workflow_threads if available
                        # Simple Explanation: The checkpoint_id tells LangGraph exactly which
                        # checkpoint to resume from. Without it, LangGraph might resume from
                        # the wrong checkpoint or restart from the beginning.
                        workflow_thread_data = get_workflow_thread_data(
                            workflow_thread_id
                        )
                        checkpoint_id = (
                            workflow_thread_data.get("checkpoint_id")
                            if workflow_thread_data
                            else None
                        )

                        # Build config with thread_id and checkpoint_id (if available)
                        config = {"configurable": {"thread_id": workflow_thread_id}}
                        if checkpoint_id:
                            config["configurable"]["checkpoint_id"] = checkpoint_id
                            logger.info(
                                f"   📍 Resuming from checkpoint_id: {checkpoint_id}"
                            )
                        else:
                            logger.warning(
                                "   ⚠️ No checkpoint_id found - workflow may restart from beginning"
                            )

                        # Simple Explanation: LangGraph automatically resumes from the specified
                        # checkpoint when you call ainvoke with a config containing both thread_id
                        # and checkpoint_id. When resuming from a static interrupt (interrupt_after),
                        # you should pass None - LangGraph will use the state from the checkpoint
                        # and continue to the next node (process_transcript). The checkpoint already
                        # has all the state from when the workflow paused, so we don't need to pass anything.
                        # Resume the workflow - it will continue to process_transcript node
                        graph = await workflow.graph

                        # Try to get the checkpoint state first to verify it exists
                        # Simple Explanation: This helps us detect if the checkpoint is missing
                        # (e.g., if using MemorySaver and server restarted, or if checkpointer isn't configured)
                        try:
                            state_snapshot = await graph.aget_state(config)
                            if not state_snapshot or not state_snapshot.values:
                                raise ValueError(
                                    "Checkpoint state not found. This may happen if: "
                                    "1) Using in-memory checkpointer and server restarted, "
                                    "2) SUPABASE_DB_PASSWORD is not set in .env file, "
                                    "3) Checkpoint was deleted or expired."
                                )
                            logger.info(
                                "   ✅ Checkpoint state found - resuming workflow"
                            )
                        except Exception as state_error:
                            logger.warning(
                                f"   ⚠️ Could not retrieve checkpoint state: {state_error}"
                            )
                            logger.warning(
                                "   This usually means the checkpointer isn't configured properly. "
                                "Check that SUPABASE_DB_PASSWORD is set in your .env file."
                            )
                            raise

                        # Pass None to resume from static interrupt - LangGraph will use checkpoint state and continue to next node
                        await graph.ainvoke(None, config=config)
                        logger.info("✅ Workflow resumed successfully")
                    except Exception as e:
                        error_msg = str(e)
                        logger.error(
                            f"❌ Error resuming workflow: {error_msg}", exc_info=True
                        )

                        # Provide helpful error message if it's a checkpointer issue
                        if (
                            "SUPABASE_DB" in error_msg.upper()
                            or "checkpoint" in error_msg.lower()
                        ):
                            logger.error(
                                "   💡 TIP: This error is likely due to missing Supabase database credentials. "
                                "Add SUPABASE_DB_PASSWORD to your .env file. "
                                "Run: python scripts/diagnose_supabase.py to check your configuration."
                            )

                        # Fallback to full transcript processing if workflow resume fails
                        # Simple Explanation: If workflow resume fails, we use ProcessTranscriptStep
                        # which includes the full pipeline: Q&A parsing, insights, email, webhook
                        logger.info("   Falling back to full transcript processing...")
                        await self.result_processor.process_full_pipeline(
                            room_name, transcript_handler
                        )
                else:
                    # No workflow - use full transcript processing pipeline
                    # Simple Explanation: Even without a workflow, we should run the full
                    # ProcessTranscriptStep pipeline to ensure emails and webhooks are sent
                    logger.info(
                        "   No workflow_thread_id - processing with full pipeline..."
                    )
                    await self.result_processor.process_full_pipeline(
                        room_name, transcript_handler
                    )

                # Cancel the task to clean up
                await task.cancel()

            # PipelineRunner tries to set up signal handlers in __init__, but this only works in the main thread.
            # Since we're running in a background task, we need to create the runner in a way that
            # skips signal handler setup. We'll monkey-patch the _setup_sigint method to be a no-op.
            import pipecat.pipeline.runner as runner_module

            original_setup_sigint = runner_module.PipelineRunner._setup_sigint

            # Temporarily disable signal handler setup
            def noop_setup_sigint(self):
                """No-op signal handler setup for background threads."""
                pass

            # Replace the method temporarily
            runner_module.PipelineRunner._setup_sigint = noop_setup_sigint
            try:
                runner = PipelineRunner()
                logger.info(
                    "✅ PipelineRunner created (signal handlers disabled for background thread)"
                )
            finally:
                # Restore original method
                runner_module.PipelineRunner._setup_sigint = original_setup_sigint

            logger.info("Starting bot pipeline runner...")
            logger.info(f"   Transport created: {transport}")
            logger.info(f"   Task created: {task}")
            logger.info(f"   Runner created: {runner}")

            # Track bot join time - when bot actually starts running
            bot_join_time = datetime.now(timezone.utc)
            logger.info(f"🤖 Bot join time: {bot_join_time.isoformat()}")

            # Save bot_join_time to database if workflow_thread_id is available
            if workflow_thread_id:
                try:
                    from flow.db import (
                        get_workflow_thread_data,
                        save_workflow_thread_data,
                    )

                    thread_data = get_workflow_thread_data(workflow_thread_id) or {}
                    thread_data["workflow_thread_id"] = workflow_thread_id
                    thread_data["bot_join_time"] = bot_join_time.isoformat()
                    if save_workflow_thread_data(workflow_thread_id, thread_data):
                        logger.debug(
                            f"✅ Saved bot_join_time to workflow_threads: {workflow_thread_id}"
                        )
                    else:
                        logger.warning(
                            f"⚠️ Failed to save bot_join_time for {workflow_thread_id}"
                        )
                except Exception as e:
                    logger.warning(f"⚠️ Error saving bot_join_time: {e}", exc_info=True)

            # **FOLLOW REFERENCE IMPLEMENTATION**: Use await runner.run(task) directly
            # This matches the reference implementation's blocking behavior exactly
            # The runner will block until the task completes (typically when participant leaves)
            try:
                logger.info("🚀 Calling runner.run(task)...")
                await runner.run(task)
                logger.info("✅ runner.run(task) completed")

                # Simple Explanation: After the bot finishes, the on_participant_left handler
                # will either resume the workflow (if workflow_thread_id exists) or process
                # results directly (legacy behavior). We don't need to call _process_bot_results
                # here anymore - it's handled in the event handler.
                # Note: The workflow resume happens in on_participant_left, so we don't need
                # to do anything here. If there's no workflow, on_participant_left will
                # call _process_bot_results directly.
            finally:
                # Track bot leave time and duration - when bot finishes running
                bot_leave_time = datetime.now(timezone.utc)
                logger.info(f"🤖 Bot leave time: {bot_leave_time.isoformat()}")

                # Calculate bot duration if we have both join and leave times
                bot_duration = None
                if workflow_thread_id and bot_join_time is not None:
                    try:
                        # Calculate duration in seconds
                        duration_delta = bot_leave_time - bot_join_time
                        bot_duration = int(duration_delta.total_seconds())
                        logger.info(f"🤖 Bot duration: {bot_duration} seconds")

                        # Save bot_leave_time and bot_duration to database
                        from flow.db import (
                            get_workflow_thread_data,
                            save_workflow_thread_data,
                        )

                        thread_data = get_workflow_thread_data(workflow_thread_id) or {}
                        thread_data["workflow_thread_id"] = workflow_thread_id
                        thread_data["bot_leave_time"] = bot_leave_time.isoformat()
                        thread_data["bot_duration"] = bot_duration
                        if save_workflow_thread_data(workflow_thread_id, thread_data):
                            logger.debug(
                                f"✅ Saved bot_leave_time and bot_duration to workflow_threads: {workflow_thread_id}"
                            )
                        else:
                            logger.warning(
                                f"⚠️ Failed to save bot_leave_time/bot_duration for {workflow_thread_id}"
                            )

                        # Calculate and save Deepgram STT cost
                        from flow.utils.pricing import calculate_deepgram_cost
                        from flow.utils.usage_tracking import update_workflow_usage_cost

                        try:
                            deepgram_cost = calculate_deepgram_cost(bot_duration)
                            success = update_workflow_usage_cost(
                                workflow_thread_id, deepgram_cost, cost_category="stt"
                            )
                            if success:
                                logger.debug(
                                    f"✅ Saved Deepgram STT cost: ${deepgram_cost:.6f} "
                                    f"for {bot_duration}s to workflow_threads: {workflow_thread_id}"
                                )
                            else:
                                logger.warning(
                                    f"⚠️ Failed to save Deepgram STT cost for {workflow_thread_id}"
                                )
                        except Exception as cost_error:
                            logger.warning(
                                f"⚠️ Error calculating/saving Deepgram STT cost: {cost_error}",
                                exc_info=True,
                            )

                        # Create usage transaction when bot leaves (fail-safe primary point)
                        # This ensures transaction is created even if process_transcript fails later
                        try:
                            from flow.db import (
                                get_workflow_thread_data,
                                create_usage_transaction,
                            )

                            # Get current usage stats to check if we have costs
                            thread_data = (
                                get_workflow_thread_data(workflow_thread_id) or {}
                            )
                            usage_stats = thread_data.get("usage_stats") or {}
                            total_cost_usd = usage_stats.get("total_cost_usd", 0.0)

                            if total_cost_usd > 0 and bot_duration:
                                logger.info(
                                    f"💰 Creating usage transaction when bot leaves: "
                                    f"workflow_thread_id={workflow_thread_id}, "
                                    f"cost=${total_cost_usd:.6f}, duration={bot_duration}s"
                                )
                                transaction_success = create_usage_transaction(
                                    workflow_thread_id=workflow_thread_id,
                                    amount_usd=total_cost_usd,
                                    duration_seconds=bot_duration,
                                )
                                if transaction_success:
                                    logger.info(
                                        f"✅ Successfully created usage transaction when bot left: {workflow_thread_id}"
                                    )
                                else:
                                    # Transaction might already exist (duplicate check), which is fine
                                    logger.debug(
                                        f"ℹ️ Usage transaction already exists or failed (may be duplicate): {workflow_thread_id}"
                                    )
                            elif total_cost_usd <= 0:
                                logger.debug(
                                    f"⏭️ Skipping usage transaction when bot leaves: "
                                    f"total_cost_usd is {total_cost_usd} (non-positive)"
                                )
                            elif not bot_duration:
                                logger.debug(
                                    "⏭️ Skipping usage transaction when bot leaves: "
                                    "bot_duration is not available"
                                )
                        except Exception as transaction_error:
                            logger.warning(
                                f"⚠️ Error creating usage transaction when bot leaves: {transaction_error}",
                                exc_info=True,
                            )
                    except Exception as e:
                        logger.warning(
                            f"⚠️ Error saving bot_leave_time/bot_duration: {e}",
                            exc_info=True,
                        )
                # When the bot task finishes, the Daily.co transport might still have pending callbacks
                # that try to post to the event loop. We need to properly clean up the transport
                # to prevent "Event loop is closed" errors and Rust panics.
                # Simple Explanation: The Daily.co audio renderer thread (Rust code) needs time
                # to finish its work before Python interpreter shuts down. We must:
                # 1. Clean up transport explicitly
                # 2. Wait for threads (especially audio renderer) to finish
                # 3. Then allow the event loop to close
                try:
                    # Explicitly leave the room before cleanup
                    logger.info(f"🚪 Leaving Daily.co room: {room_name}")
                    await transport.cleanup()
                    logger.info("✅ Transport cleaned up successfully")

                    # Critical: Add delay to allow audio renderer threads to finish
                    # Simple Explanation: The Rust audio renderer thread needs time to clean up
                    # before Python interpreter shuts down. Without this delay, the Rust thread
                    # tries to use Python APIs during shutdown, causing a panic.
                    logger.info("⏳ Waiting for audio renderer threads to finish...")
                    await asyncio.sleep(1.5)  # Wait 1.5 seconds for threads to finish
                    logger.info("✅ Delay completed - threads should be finished")
                except (RuntimeError, asyncio.CancelledError) as cleanup_error:
                    # Ignore cleanup errors - transport might already be closed
                    # These are expected when the event loop is closing
                    # "Event loop is closed" errors are common during cleanup
                    error_msg = str(cleanup_error)
                    if (
                        "Event loop is closed" in error_msg
                        or "loop is closed" in error_msg.lower()
                    ):
                        logger.debug(
                            f"Transport cleanup warning (expected during shutdown): {cleanup_error}"
                        )
                    else:
                        logger.warning(f"Transport cleanup warning: {cleanup_error}")
                except Exception as cleanup_error:
                    # Catch and log Rust panics during shutdown - don't crash on them
                    # Simple Explanation: Rust panics can occur if audio renderer threads
                    # are still running during shutdown. We log them but don't fail.
                    error_msg = str(cleanup_error)
                    if "panic" in error_msg.lower() or "rust" in error_msg.lower():
                        logger.warning(
                            f"⚠️ Rust panic during shutdown (non-fatal): {cleanup_error}"
                        )
                    else:
                        logger.warning(f"Transport cleanup warning: {cleanup_error}")
                finally:
                    # Remove transport from map after cleanup
                    self.transport_map.pop(room_name, None)

        except asyncio.CancelledError:
            # Task was cancelled - this is expected when participant leaves or during shutdown
            logger.info("🛑 Bot task was cancelled - ensuring bot leaves the room")

            # Track bot leave time on cancellation
            bot_leave_time = datetime.now(timezone.utc)
            logger.info(f"🤖 Bot leave time (cancelled): {bot_leave_time.isoformat()}")

            # Calculate and save bot duration if we have join time
            if workflow_thread_id and bot_join_time is not None:
                try:
                    duration_delta = bot_leave_time - bot_join_time
                    bot_duration = int(duration_delta.total_seconds())
                    logger.info(f"🤖 Bot duration (cancelled): {bot_duration} seconds")

                    from flow.db import (
                        get_workflow_thread_data,
                        save_workflow_thread_data,
                    )

                    thread_data = get_workflow_thread_data(workflow_thread_id) or {}
                    thread_data["workflow_thread_id"] = workflow_thread_id
                    thread_data["bot_leave_time"] = bot_leave_time.isoformat()
                    thread_data["bot_duration"] = bot_duration
                    save_workflow_thread_data(workflow_thread_id, thread_data)

                    # Calculate and save Deepgram STT cost
                    from flow.utils.pricing import calculate_deepgram_cost
                    from flow.utils.usage_tracking import update_workflow_usage_cost

                    try:
                        deepgram_cost = calculate_deepgram_cost(bot_duration)
                        update_workflow_usage_cost(
                            workflow_thread_id, deepgram_cost, cost_category="stt"
                        )
                    except Exception as cost_error:
                        logger.warning(
                            f"⚠️ Error calculating/saving Deepgram STT cost on cancellation: {cost_error}",
                            exc_info=True,
                        )
                except Exception as e:
                    logger.warning(
                        f"⚠️ Error saving bot_leave_time on cancellation: {e}",
                        exc_info=True,
                    )

            # Ensure transport is cleaned up even on cancellation - this is critical to leave the room
            try:
                if "transport" in locals():
                    logger.info(
                        f"🚪 Leaving Daily.co room on cancellation: {room_name}"
                    )
                    await transport.cleanup()
                    logger.info("✅ Transport cleaned up after cancellation")

                    # Add delay to allow audio renderer threads to finish before shutdown
                    logger.info("⏳ Waiting for audio renderer threads to finish...")
                    await asyncio.sleep(1.5)
                    logger.info("✅ Delay completed - threads should be finished")
            except (RuntimeError, asyncio.CancelledError) as e:
                # Ignore "Event loop is closed" errors during cancellation - these are expected
                if "Event loop is closed" not in str(e):
                    logger.debug(f"Transport cleanup during cancellation: {e}")
            except Exception as e:
                # Catch and log Rust panics during cancellation - don't crash on them
                error_msg = str(e)
                if "panic" in error_msg.lower() or "rust" in error_msg.lower():
                    logger.warning(f"⚠️ Rust panic during cancellation (non-fatal): {e}")
                else:
                    logger.warning(
                        f"Error during transport cleanup on cancellation: {e}"
                    )
            finally:
                # Remove transport from map after cleanup
                self.transport_map.pop(room_name, None)
            raise
        except Exception as e:
            logger.error(f"❌ Bot process error: {e}", exc_info=True)
            logger.error(f"   Error type: {type(e).__name__}")
            logger.error(f"   Error message: {str(e)}")

            # Track bot leave time on error
            bot_leave_time = datetime.now(timezone.utc)
            logger.info(f"🤖 Bot leave time (error): {bot_leave_time.isoformat()}")

            # Calculate and save bot duration if we have join time
            if workflow_thread_id and bot_join_time is not None:
                try:
                    duration_delta = bot_leave_time - bot_join_time
                    bot_duration = int(duration_delta.total_seconds())
                    logger.info(f"🤖 Bot duration (error): {bot_duration} seconds")

                    from flow.db import (
                        get_workflow_thread_data,
                        save_workflow_thread_data,
                    )

                    thread_data = get_workflow_thread_data(workflow_thread_id) or {}
                    thread_data["workflow_thread_id"] = workflow_thread_id
                    thread_data["bot_leave_time"] = bot_leave_time.isoformat()
                    thread_data["bot_duration"] = bot_duration
                    save_workflow_thread_data(workflow_thread_id, thread_data)

                    # Calculate and save Deepgram STT cost
                    from flow.utils.pricing import calculate_deepgram_cost
                    from flow.utils.usage_tracking import update_workflow_usage_cost

                    try:
                        deepgram_cost = calculate_deepgram_cost(bot_duration)
                        update_workflow_usage_cost(
                            workflow_thread_id, deepgram_cost, cost_category="stt"
                        )
                    except Exception as cost_error:
                        logger.warning(
                            f"⚠️ Error calculating/saving Deepgram STT cost on error: {cost_error}",
                            exc_info=True,
                        )
                except Exception as save_error:
                    logger.warning(
                        f"⚠️ Error saving bot_leave_time on error: {save_error}",
                        exc_info=True,
                    )

            # Ensure transport is cleaned up even on error - must leave the room
            try:
                if "transport" in locals():
                    logger.info(f"🚪 Leaving Daily.co room after error: {room_name}")
                    await transport.cleanup()
                    logger.info("✅ Transport cleaned up after error")

                    # Add delay to allow audio renderer threads to finish before shutdown
                    logger.info("⏳ Waiting for audio renderer threads to finish...")
                    await asyncio.sleep(1.5)
                    logger.info("✅ Delay completed - threads should be finished")
            except (RuntimeError, asyncio.CancelledError) as cleanup_e:
                # Ignore "Event loop is closed" errors during error handling - these are expected
                if "Event loop is closed" not in str(cleanup_e):
                    logger.debug(f"Transport cleanup during error: {cleanup_e}")
            except Exception as cleanup_e:
                # Catch and log Rust panics during error handling - don't crash on them
                error_msg = str(cleanup_e)
                if "panic" in error_msg.lower() or "rust" in error_msg.lower():
                    logger.warning(
                        f"⚠️ Rust panic during error cleanup (non-fatal): {cleanup_e}"
                    )
                else:
                    logger.warning(
                        f"Error during transport cleanup after error: {cleanup_e}"
                    )
            finally:
                # Remove transport from map after cleanup
                self.transport_map.pop(room_name, None)
            raise
