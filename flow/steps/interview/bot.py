# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Standalone bot script for running in a separate container.

Usage:
    python bot.py -u <room_url> -t <token> [--bot-config <json>]

The bot_config can also be provided via BOT_CONFIG environment variable.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict

# Add parent directory to path so we can import from flow.steps.interview
project_root = os.path.join(os.path.dirname(__file__), "../../../")
sys.path.insert(0, os.path.abspath(project_root))

# Import shared components from bot_service
from flow.steps.interview.bot_service import (  # noqa: E402
    SpeakerTrackingProcessor,
    TranscriptHandler,
    TalkingAnimation,
    load_bot_video_frames,
)

from pipecat.audio.interruptions.min_words_interruption_strategy import (  # noqa: E402
    MinWordsInterruptionStrategy,
)
from pipecat.audio.turn.smart_turn.base_smart_turn import SmartTurnParams  # noqa: E402
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import (  # noqa: E402
    LocalSmartTurnAnalyzerV3,
)
from pipecat.audio.vad.silero import SileroVADAnalyzer  # noqa: E402
from pipecat.audio.vad.vad_analyzer import VADParams  # noqa: E402
from pipecat.frames.frames import (  # noqa: E402
    LLMRunFrame,
)
from pipecat.pipeline.pipeline import Pipeline  # noqa: E402
from pipecat.pipeline.runner import PipelineRunner  # noqa: E402
from pipecat.pipeline.task import PipelineParams, PipelineTask  # noqa: E402
from pipecat.processors.aggregators.llm_context import LLMContext  # noqa: E402
from pipecat.processors.aggregators.llm_response_universal import (  # noqa: E402
    LLMContextAggregatorPair,
)
from pipecat.processors.transcript_processor import TranscriptProcessor  # noqa: E402
from pipecat.services.deepgram.stt import DeepgramSTTService  # noqa: E402
from pipecat.services.openai.llm import OpenAILLMService  # noqa: E402
from pipecat.services.openai.tts import OpenAITTSService  # noqa: E402
from pipecat.transports.daily.transport import DailyParams, DailyTransport  # noqa: E402

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_bot(room_url: str, token: str, bot_config: Dict[str, Any]) -> None:
    """
    Run the Pipecat bot.

    Args:
        room_url: Full Daily.co room URL
        token: Meeting token for authentication
        bot_config: Bot configuration dictionary
    """
    try:
        # Extract room name from URL
        room_name = room_url.split("/")[-1]

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

        # Create Daily.co transport
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

        logger.info(
            f"Bot transport initialized for room: {room_url}, bot_name: {bot_name}"
        )

        # Use OpenAI for both LLM and TTS
        llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"), model="gpt-4o")
        tts = OpenAITTSService(
            api_key=os.getenv("OPENAI_API_KEY"),
            voice="alloy",
            interruptions_allowed=True,
            interruption_strategies=[MinWordsInterruptionStrategy(min_words=3)],
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
        context_aggregator = LLMContextAggregatorPair(context)

        # Create transcript processor and handler
        transcript = TranscriptProcessor()

        # Create transcript handler first (needed for speaker tracker)
        transcript_handler = TranscriptHandler(
            room_name=room_name,
            bot_name=bot_name,
            speaker_tracker=None,  # Will be set after creation
            transport=transport,
        )

        # Create speaker tracking processor to extract speaker IDs from frames
        # Pass transcript_handler reference for participant order mapping
        speaker_tracker = SpeakerTrackingProcessor(
            transcript_handler=transcript_handler
        )

        # Now set the speaker_tracker reference in transcript_handler
        transcript_handler.speaker_tracker = speaker_tracker
        logger.info(
            f"📝 Transcript will be saved to database for room: {room_name}\n"
            "   - User speech: Deepgram STT (from pipeline) with speaker diarization\n"
            "   - Bot speech: TranscriptProcessor (from TTS input)"
        )

        # Load video frames based on bot configuration
        quiet_frame, talking_frame = load_bot_video_frames(bot_config)
        ta = TalkingAnimation(quiet_frame=quiet_frame, talking_frame=talking_frame)

        # Build pipeline with Deepgram STT and TranscriptProcessor
        pipeline_components = [
            transport.input(),  # Transport user input
            stt,  # Deepgram STT - converts user speech to text
            speaker_tracker,  # Track speaker IDs from frames
            transcript.user(),  # User transcripts (from STT)
            context_aggregator.user(),  # User responses
            llm,  # LLM
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
            except Exception as e:
                logger.warning(f"⚠️ Error updating participants map: {e}", exc_info=True)

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

            # Get current/recent Deepgram speaker ID from tracker
            deepgram_speaker_id = speaker_tracker.get_current_speaker_id()

            if deepgram_speaker_id is not None:
                # Map Deepgram speaker ID to Daily.co session_id
                speaker_tracker.map_speaker_to_participant(deepgram_speaker_id, peer_id)
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
            # Kick off the conversation with a greeting first
            messages.append(
                {
                    "role": "system",
                    "content": "Please introduce yourself warmly to the user. Greet them and let them know you're here to conduct an interview. Wait for them to respond before starting with the interview questions.",
                }
            )
            logger.info("📤 Queuing LLMRunFrame to start conversation...")
            await task.queue_frames([LLMRunFrame()])
            logger.info("✅ LLMRunFrame queued successfully")

        @transport.event_handler("on_participant_left")
        async def on_participant_left(transport, participant, reason):
            logger.info(f"Participant left: {participant['id']}, reason: {reason}")
            await task.cancel()

        # Create pipeline runner
        runner = PipelineRunner()

        logger.info("Starting bot pipeline runner...")
        logger.info(f"   Transport created: {transport}")
        logger.info(f"   Task created: {task}")
        logger.info(f"   Runner created: {runner}")

        # Run the bot - this will block until the task completes
        try:
            logger.info("🚀 Calling runner.run(task)...")
            await runner.run(task)
            logger.info("✅ runner.run(task) completed")
        finally:
            # Clean up the transport
            try:
                await transport.cleanup()
                logger.info("✅ Transport cleaned up successfully")
            except (RuntimeError, asyncio.CancelledError) as cleanup_error:
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
                logger.debug(f"Transport cleanup warning: {cleanup_error}")

    except asyncio.CancelledError:
        logger.info("🛑 Bot task was cancelled (participant left)")
        raise
    except Exception as e:
        logger.error(f"❌ Bot process error: {e}", exc_info=True)
        raise


def main():
    """Main entry point for the standalone bot script."""
    parser = argparse.ArgumentParser(
        description="Run a Pipecat bot in a separate container"
    )
    parser.add_argument(
        "-u", "--url", dest="room_url", required=True, help="Daily.co room URL"
    )
    parser.add_argument("-t", "--token", required=True, help="Daily.co meeting token")
    parser.add_argument(
        "--bot-config",
        help="Bot configuration as JSON string (or use BOT_CONFIG env var)",
    )

    args = parser.parse_args()

    # Get bot config from command line or environment variable
    bot_config_str = args.bot_config or os.getenv("BOT_CONFIG", "{}")
    try:
        bot_config = json.loads(bot_config_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse bot_config JSON: {e}")
        sys.exit(1)

    logger.info(f"Starting bot for room: {args.room_url}")
    logger.info(f"Bot config: {bot_config}")

    # Run the bot
    try:
        asyncio.run(run_bot(args.room_url, args.token, bot_config))
    except KeyboardInterrupt:
        logger.info("Bot interrupted by user")
    except Exception as e:
        logger.error(f"Bot failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
