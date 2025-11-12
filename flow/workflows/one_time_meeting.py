# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""One-Time Meeting Workflow - Creates a video meeting room and returns URLs."""

import asyncio
import json
import logging
import os
from typing import Any, Dict, TypedDict

from langgraph.graph import END, StateGraph

from flow.steps.interview import CreateRoomStep

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
    processing_status: str
    error: str | None
    interview_config: Dict[str, Any]


def create_step_wrapper(step_instance: CreateRoomStep):
    async def step_wrapper(state: OneTimeMeetingState) -> OneTimeMeetingState:
        return await step_instance.execute(state)

    return step_wrapper


class OneTimeMeetingWorkflow:
    """One-Time Meeting Workflow - Creates a video meeting room and returns URLs."""

    name = "one_time_meeting"
    description = "Create a one-time video meeting room with hosted page"

    def __init__(self):
        self.steps = {"create_room": CreateRoomStep()}
        self.graph = self._build_graph()

    def _build_graph(self) -> Any:
        workflow = StateGraph(OneTimeMeetingState)
        workflow.add_node("create_room", create_step_wrapper(self.steps["create_room"]))
        workflow.set_entry_point("create_room")
        workflow.add_edge("create_room", END)
        return workflow.compile()

    async def execute_async(self, context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            import uuid

            meeting_config = context.get("meeting_config", {})
            provider_keys = context.get("provider_keys", {})
            base_url = os.getenv("MEET_BASE_URL", "http://localhost:8001")

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
                "session_id": str(uuid.uuid4()),
                "interview_config": {
                    "profile": meeting_config.get("profile", "conversation"),
                    "overrides": meeting_config.get("overrides"),
                    "branding": meeting_config.get("branding"),
                },
                "meet_base_url": base_url,
            }

            result = await self.graph.ainvoke(initial_state)

            if result.get("error"):
                return {
                    "success": False,
                    "error": result["error"],
                    "processing_status": result.get("processing_status"),
                    "workflow": self.name,
                }

            hosted_url = None
            if result.get("room_name") and result.get("room_url"):
                hosted_url = f"{base_url}/meet/{result['room_name']}?room_url={result['room_url']}"

            return {
                "success": True,
                "room_url": result.get("room_url"),
                "hosted_url": hosted_url,
                "room_name": result.get("room_name"),
                "room_id": result.get("room_id"),
                "processing_status": result.get("processing_status"),
                "workflow": self.name,
            }
        except Exception as e:
            logger.error(f"Error in One-Time Meeting workflow: {e}", exc_info=True)
            return {"success": False, "error": str(e), "workflow": self.name}

    def execute(
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

            try:
                asyncio.get_running_loop()
                import concurrent.futures

                def run_in_thread():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(self.execute_async(context))
                    finally:
                        new_loop.close()

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    return executor.submit(run_in_thread).result()
            except RuntimeError:
                return asyncio.run(self.execute_async(context))
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid JSON: {str(e)}"}
        except Exception as e:
            logger.error(f"Error executing workflow: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
