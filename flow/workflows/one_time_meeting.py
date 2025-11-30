# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""One-Time Meeting Workflow - Creates a video meeting room and returns URLs."""

import base64
import json
import logging
import os
from typing import Any, Dict, TypedDict
from urllib.parse import urlencode

from langgraph.graph import END, StateGraph

from flow.steps.interview import CallVAPIStep, CreateRoomStep
from flow.steps.interview.join_bot import JoinBotStep

logger = logging.getLogger(__name__)


class OneTimeMeetingState(TypedDict, total=False):
    """State dictionary for the one-time meeting workflow."""

    meeting_config: Dict[str, Any]
    provider_keys: Dict[str, str]
    session_id: str
    meet_base_url: str
    room_id: str | None
    room_name: str | None
    room_url: str | None
    hosted_url: str | None
    room_provider: str | None
    meeting_token: str | None
    dialin_code: str | None  # Daily.co PIN code for dial-in
    vapi_call_id: str | None
    vapi_call_created: bool
    session_data_to_set: Dict[str, Any] | None  # Session data to set on join
    processing_status: str
    error: str | None
    participant_info: Dict[
        str, Any
    ]  # Participant information (name, email, role, etc.)


def create_step_wrapper(step_instance: Any):
    """Create a wrapper function for a step instance to use in LangGraph."""

    async def step_wrapper(state: OneTimeMeetingState) -> OneTimeMeetingState:
        return await step_instance.execute(state)

    return step_wrapper


class OneTimeMeetingWorkflow:
    """One-Time Meeting Workflow - Creates a video meeting room and returns URLs."""

    name = "one_time_meeting"
    description = "Create a one-time video meeting room with hosted page"

    def __init__(self):
        self.steps = {
            "create_room": CreateRoomStep(),
            "call_vapi": CallVAPIStep(),
            "join_bot": JoinBotStep(),
        }
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        workflow = StateGraph(OneTimeMeetingState)
        workflow.add_node("create_room", create_step_wrapper(self.steps["create_room"]))
        workflow.add_node("call_vapi", create_step_wrapper(self.steps["call_vapi"]))
        workflow.add_node("join_bot", create_step_wrapper(self.steps["join_bot"]))
        workflow.set_entry_point("create_room")
        workflow.add_edge("create_room", "join_bot")
        # IMPORTANT: Join bot BEFORE calling VAPI
        # **Simple Explanation:** According to Daily.co docs, PIN dial-in requires
        # the meeting session to have started (when someone joins). By joining the bot first,
        # we start the meeting session, which enables PIN dial-in functionality.
        # Then VAPI can successfully dial the phone number and enter the PIN to join the room.
        workflow.add_edge("join_bot", "call_vapi")
        workflow.add_edge("call_vapi", END)
        return workflow.compile()

    async def execute_async(self, context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            import uuid

            meeting_config = context.get("meeting_config", {})
            provider_keys = context.get("provider_keys", {})
            # Get participant_info from context
            participant_info = context.get("participant_info", {})
            base_url = os.getenv("MEET_BASE_URL", "http://localhost:8001")
            daily_domain = os.getenv(
                "DAILY_DOMAIN", "https://your-domain.daily.co"
            ).rstrip("/")

            initial_state: OneTimeMeetingState = {
                "meeting_config": meeting_config,
                "provider_keys": provider_keys,
                "processing_status": "starting",
                "error": None,
                "room_id": None,
                "room_name": None,
                "room_url": None,
                "hosted_url": None,
                "room_provider": None,
                "meeting_token": None,
                "dialin_code": None,
                "vapi_call_id": None,
                "vapi_call_created": False,
                "session_id": context.get("session_id", str(uuid.uuid4())),
                "meet_base_url": base_url,
            }

            # Add participant_info to state if provided
            if participant_info:
                initial_state["participant_info"] = participant_info

            result = await self.graph.ainvoke(initial_state)

            room_name = result.get("room_name")

            # If room was created, return room info even if later steps failed
            # **Simple Explanation:** Room creation is the main goal - VAPI can be retried
            if room_name:
                # Room was created successfully - return room info even if VAPI failed
                pass  # Continue to build response with room info
            elif result.get("error"):
                # Room creation failed - return error
                return {
                    "success": False,
                    "error": result["error"],
                    "processing_status": result.get("processing_status"),
                    "workflow": self.name,
                }
            else:
                # No room name and no error - something went wrong
                return {
                    "success": False,
                    "error": "Room created but no room_name returned",
                    "processing_status": result.get("processing_status"),
                    "workflow": self.name,
                }

            # Generate room URL from room name using Daily domain
            room_url = f"{daily_domain}/{room_name}"

            # Build hosted URL with optional auto-start parameters
            # Check meeting_config for autoRecord and autoTranscribe settings
            # These can be set in meeting_config or default to True for interviews
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

            # Build URL with query parameters
            query_params = {}
            if auto_record:
                query_params["autoRecord"] = "true"
            if auto_transcribe:
                query_params["autoTranscribe"] = "true"

            # Add meeting token if available (for transcription admin permissions)
            meeting_token = result.get("meeting_token")
            if meeting_token:
                query_params["token"] = meeting_token

            # Add bot parameter if enabled
            if meeting_config.get("bot", {}).get("enabled"):
                query_params["bot"] = "true"

            # Add any other URL parameters from meeting_config (theme, accentColor, etc.)
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

            # Add session data if available (for setting on join)
            # **Simple Explanation:** If the create_room step prepared session data,
            # we encode it as base64 JSON and add it to the URL. The frontend will
            # decode it and call our API to set it in Daily.co when someone joins.
            session_data_to_set = result.get("session_data_to_set")
            if session_data_to_set:
                try:
                    # Encode session data as base64 JSON
                    session_json = json.dumps(session_data_to_set)
                    session_b64 = base64.b64encode(session_json.encode()).decode()
                    query_params["sessionData"] = session_b64
                    logger.info(
                        f"📦 Added session data to meeting URL ({len(session_json)} chars)"
                    )
                except Exception as e:
                    logger.warning(f"Failed to encode session data for URL: {e}")

            if query_params:
                hosted_url = f"{base_url}/meet/{room_name}?{urlencode(query_params)}"
            else:
                hosted_url = f"{base_url}/meet/{room_name}"

            response = {
                "success": True,
                "room_url": room_url,
                "hosted_url": hosted_url,
                "room_name": room_name,
                "room_id": result.get("room_id"),
                "processing_status": result.get("processing_status"),
                "workflow": self.name,
            }

            # Include VAPI info if available (even if call failed)
            if "dialin_code" in result:
                response["dialin_code"] = result.get("dialin_code")
            if "vapi_call_created" in result:
                response["vapi_call_created"] = result.get("vapi_call_created")
            if "vapi_call_id" in result:
                response["vapi_call_id"] = result.get("vapi_call_id")
            if "vapi_call_error" in result:
                response["vapi_call_error"] = result.get("vapi_call_error")
            if result.get("error"):
                # Include error as warning if room was still created
                response["warning"] = result.get("error")

            return response
        except Exception as e:
            logger.error(f"Error in One-Time Meeting workflow: {e}", exc_info=True)
            return {"success": False, "error": str(e), "workflow": self.name}

    async def execute(
        self, message: str, user_id: str | None = None, channel_id: str | None = None
    ) -> Dict[str, Any]:
        try:
            params = json.loads(message)
            meeting_config = params.get("meeting_config", {})
            provider_keys = params.get("provider_keys", {})

            if not provider_keys or not provider_keys.get("room_provider_key"):
                return {
                    "success": False,
                    "error": "Missing required parameter: provider_keys.room_provider_key",
                }

            context = {
                "meeting_config": meeting_config,
                "provider_keys": provider_keys,
            }

            return await self.execute_async(context)

        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid JSON: {str(e)}"}
        except Exception as e:
            logger.error(f"Error executing workflow: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
