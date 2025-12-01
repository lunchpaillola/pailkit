# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Standalone bot script for running in a separate container.

**Simple Explanation:**
This script runs a Pipecat bot in its own container. It's designed to be
launched by Fly.io machines when a new bot session starts. The bot connects
to a Daily.co room and handles the conversation.

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
# **Simple Explanation:**
# We need to add the project root to Python's path so we can import modules
# from the flow package. This allows us to reuse code from bot_service.py.
project_root = os.path.join(os.path.dirname(__file__), "../../../")
sys.path.insert(0, os.path.abspath(project_root))

# Import shared components from bot_service
# **Simple Explanation:**
# We reuse the same transcript handler, animation, and video frame loading
# logic from bot_service.py to keep the code consistent.
from flow.steps.interview.bot_service import (  # noqa: E402
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

    **Simple Explanation:**
    This function sets up and runs the bot pipeline. It:
    1. Creates a Daily.co transport to connect to the room
    2. Sets up speech-to-text (Deepgram), LLM (OpenAI), and text-to-speech (OpenAI)
    3. Creates a pipeline that processes audio and generates responses
    4. Runs until the participant leaves

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
                "system_message",  # Fallback to old field name for backwards compatibility
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
        stt = DeepgramSTTService(api_key=os.getenv("DEEPGRAM_API_KEY"))

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

        # Create transcript handler that saves to database
        transcript_handler = TranscriptHandler(room_name=room_name)
        logger.info(
            f"📝 Transcript will be saved to database for room: {room_name}\n"
            "   - User speech: Deepgram STT (from pipeline)\n"
            "   - Bot speech: TranscriptProcessor (from TTS input)"
        )

        # Load video frames based on bot configuration
        quiet_frame, talking_frame = load_bot_video_frames(bot_config)
        ta = TalkingAnimation(quiet_frame=quiet_frame, talking_frame=talking_frame)

        # Build pipeline with Deepgram STT and TranscriptProcessor
        pipeline_components = [
            transport.input(),  # Transport user input
            stt,  # Deepgram STT - converts user speech to text
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
            """Log when any participant (including bot) joins."""
            participant_id = participant.get("id", "unknown")
            participant_name = participant.get("user_name", "unknown")
            is_local = participant.get("local", False)
            logger.info(
                f"🔵 Participant joined - ID: {participant_id}, Name: {participant_name}, Local: {is_local}"
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
                if hasattr(transport, "cleanup") and callable(transport.cleanup):
                    await transport.cleanup()
                elif hasattr(transport, "close") and callable(transport.close):
                    await transport.close()
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
