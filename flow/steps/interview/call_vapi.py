# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Call VAPI Step

Makes an outbound call using VAPI to dial a Daily.co phone number and enter a PIN via DTMF.
This enables the AI interviewer (via VAPI) to join the room via phone dial-in.
"""

import logging
import os
from typing import Any, Dict

import httpx

from flow.steps.interview.base import InterviewStep

logger = logging.getLogger(__name__)


class CallVAPIStep(InterviewStep):
    """
    Step to make an outbound call using VAPI with DTMF PIN dialing.

    **Simple Explanation:**
    This step calls VAPI's API to make an outbound call. VAPI will:
    1. Use the phoneNumberId to make an outbound call to the Daily.co phone number
    2. Once connected, use DTMF to dial the PIN code
    3. This allows VAPI to join the Daily.co room via phone dial-in
    4. Once in the room, VAPI acts as the AI interviewer

    Note: The VAPI assistant must be configured to use the "dial-keypad-dtmf" tool
    (https://docs.vapi.ai/tools/default-tools#dial-keypad-dtmf) to dial the PIN
    after connecting to the phone number. The PIN is passed in call metadata.
    """

    def __init__(self):
        super().__init__(
            name="call_vapi",
            description="Make outbound call using VAPI to join room via PIN dial-in with DTMF",
        )

    def _get_vapi_headers(self, api_key: str) -> Dict[str, str]:
        """Get HTTP headers for VAPI API requests."""
        auth_header = api_key.strip()
        if not auth_header.startswith("Bearer "):
            auth_header = f"Bearer {auth_header}"

        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": auth_header,
        }

    async def _create_vapi_call(
        self,
        api_key: str,
        assistant_id: str,
        phone_number_id: str,
        daily_phone_number: str,
        dialin_code: str,
        customer_name: str | None = None,
    ) -> Dict[str, Any]:
        """
        Create an outbound call using VAPI's API with DTMF PIN dialing.

        **Simple Explanation:**
        This calls VAPI's API to start an outbound call. VAPI will:
        1. Use the phoneNumberId to make an outbound call to the Daily.co phone number
        2. Once connected, use DTMF (Dual-Tone Multi-Frequency) to dial the PIN code
        3. This allows VAPI to join the Daily.co room via phone dial-in

        Args:
            api_key: VAPI API key
            assistant_id: VAPI assistant ID to use for the call
            phone_number_id: VAPI phone number ID to use for outbound calling
            daily_phone_number: Daily.co phone number to dial (in E.164 format)
            dialin_code: PIN code to dial via DTMF after connecting
            customer_name: Optional name of the candidate

        Returns:
            Dictionary with call creation result
        """
        headers = self._get_vapi_headers(api_key)

        # Format phone number to E.164 format (ensure it has + prefix)
        # **Simple Explanation:** VAPI requires E.164 format (e.g., "+12092080701")
        # If the number doesn't have a +, we add it
        formatted_phone = daily_phone_number.strip()
        if not formatted_phone.startswith("+"):
            formatted_phone = f"+{formatted_phone}"

        # Build the request payload according to VAPI API documentation
        # **Simple Explanation:** Based on https://docs.vapi.ai/api-reference/calls/create
        # VAPI API expects:
        # - assistantId: Which AI assistant to use (required)
        # - phoneNumberId: Which phone number to call from (required)
        # - customer: Object with customer information
        #   - number: Phone number in E.164 format to dial (Daily.co phone number)
        #   - name: Optional customer name
        # - metadata: Optional metadata that can be accessed by the assistant
        #   - dialin_code: PIN code that the assistant should dial via DTMF
        #
        # The assistant must be configured to use the "dial-keypad-dtmf" tool
        # (https://docs.vapi.ai/tools/default-tools#dial-keypad-dtmf) to dial the PIN
        # after connecting to the phone number.
        # IMPORTANT: Append "#" (pound) key after PIN to submit it
        # **Simple Explanation:** Most phone systems require pressing # after entering a PIN
        # to submit it. We append "#" to the PIN so VAPI dials: PIN + # (e.g., "12345678987#")
        dialin_code_with_pound = f"{dialin_code}#"

        payload = {
            "assistantId": assistant_id,
            "phoneNumberId": phone_number_id,
            "customer": {
                "number": formatted_phone,  # Daily.co phone number to dial
            },
            "metadata": {
                "dialin_code": dialin_code_with_pound,  # PIN code + # for DTMF dialing
            },
            # Note: Check VAPI IVR navigation docs for automated DTMF:
            # https://docs.vapi.ai/ivr-navigation
            # May need additional IVR configuration fields for deterministic DTMF dialing
        }

        # Add customer name if available
        if customer_name:
            payload["customer"]["name"] = customer_name

        logger.info(
            f"📱 Creating VAPI call: Using phone {phone_number_id} to dial {formatted_phone}, "
            f"then DTMF PIN {dialin_code}#"
        )
        logger.debug(f"VAPI request payload: {payload}")

        try:
            async with httpx.AsyncClient() as client:
                # VAPI API endpoint: POST https://api.vapi.ai/call
                # **Simple Explanation:** According to VAPI docs at https://docs.vapi.ai/api-reference/calls/create
                # The endpoint is /call (singular) for creating a call
                response = await client.post(
                    "https://api.vapi.ai/call",
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()
                result = response.json()

                return {
                    "success": True,
                    "call_id": result.get("id"),
                    "status": result.get("status"),
                    "message": "VAPI call created successfully",
                }

        except httpx.HTTPStatusError as e:
            error_detail = "Unknown error"
            try:
                error_data = e.response.json()
                # Log the full error response for debugging
                logger.error(f"VAPI API error response: {error_data}")
                # Try to extract error message from various possible formats
                if isinstance(error_data, dict):
                    error_detail = (
                        error_data.get("error", {}).get("message")
                        or error_data.get("message")
                        or error_data.get("error")
                        or str(error_data)
                    )
                else:
                    error_detail = str(error_data)
                logger.error(
                    f"VAPI API error: {error_detail} (status: {e.response.status_code})"
                )
                # Also log the request payload for debugging
                logger.error(f"VAPI request payload was: {payload}")
            except Exception:
                # If we can't parse JSON, log the raw response text
                try:
                    error_text = e.response.text
                    logger.error(f"VAPI API error (raw response): {error_text}")
                    error_detail = error_text or str(e)
                except Exception:
                    error_detail = str(e)
                logger.error(f"VAPI API error: {error_detail}")

            return {
                "success": False,
                "call_id": None,
                "message": f"VAPI API error: {error_detail}",
            }
        except Exception as e:
            return {
                "success": False,
                "call_id": None,
                "message": f"Failed to create VAPI call: {str(e)}",
            }

    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute VAPI outbound call with DTMF PIN dialing.

        **Simple Explanation:**
        This checks if VAPI calling is enabled, gets the Daily.co phone number and PIN
        from the room creation step, and makes an outbound call. VAPI will dial the
        Daily.co phone number and then use DTMF to enter the PIN to join the room.
        """
        # Check if VAPI calling is enabled
        interview_config = state.get("interview_config") or state.get(
            "meeting_config", {}
        )
        vapi_config = interview_config.get("vapi", {})
        enable_vapi_calling = vapi_config.get("enabled", False)

        if not enable_vapi_calling:
            logger.info("VAPI calling not enabled, skipping call step")
            state["vapi_call_created"] = False
            return state

        # Validate required state - provider_keys is required
        if not self.validate_state(state, ["provider_keys"]):
            logger.warning("Missing required state for VAPI call - skipping")
            state["vapi_call_created"] = False
            return state

        provider_keys = state.get("provider_keys", {})
        vapi_api_key = provider_keys.get("vapi_api_key")

        if not vapi_api_key:
            # Try to get from environment variable as fallback
            vapi_api_key = os.getenv("VAPI_API_KEY")

        if not vapi_api_key:
            error_msg = "Missing VAPI API key in provider_keys or VAPI_API_KEY environment variable"
            logger.error(f"❌ {error_msg}")
            return self.set_error(state, error_msg)

        # Get assistant ID from config or environment
        assistant_id = vapi_config.get("assistant_id") or os.getenv("VAPI_ASSISTANT_ID")

        if not assistant_id:
            error_msg = "Missing VAPI assistant_id in vapi config or VAPI_ASSISTANT_ID environment variable"
            logger.error(f"❌ {error_msg}")
            return self.set_error(state, error_msg)

        # Get phone number ID from environment variable
        # **Simple Explanation:** This is the VAPI phone number that will be used to make the outbound call
        phone_number_id = os.getenv("VAPI_PHONE_NUMBER_ID")

        if not phone_number_id:
            error_msg = "Missing VAPI_PHONE_NUMBER_ID environment variable"
            logger.error(f"❌ {error_msg}")
            return self.set_error(state, error_msg)

        # Get Daily.co phone number from environment variable
        # **Simple Explanation:** This is the Daily.co phone number that VAPI will dial
        # to join the room via phone dial-in
        daily_phone_number = os.getenv("DAILY_PHONE_NUMBER")

        if not daily_phone_number:
            error_msg = "Missing DAILY_PHONE_NUMBER environment variable (required for PIN dial-in)"
            logger.error(f"❌ {error_msg}")
            return self.set_error(state, error_msg)

        # Get dial-in code (PIN) from state (set by create_room step)
        # **Simple Explanation:**
        # 1. CreateRoomStep enables PIN dial-in on the Daily.co room
        # 2. Daily.co returns a dial-in code (PIN) (e.g., "12345678987")
        # 3. CreateRoomStep stores this in state as "dialin_code"
        # 4. We read it here to use for DTMF dialing in the VAPI call
        dialin_code = state.get("dialin_code")

        logger.info(f"📋 Reading dialin_code from state: dialin_code={dialin_code}")

        if not dialin_code:
            error_msg = (
                f"Missing dialin_code in state (required for VAPI calling). "
                f"dialin_code={dialin_code}. "
                f"State keys: {list(state.keys())}"
            )
            logger.error(f"❌ {error_msg}")
            return self.set_error(state, error_msg)

        # Get candidate name if available
        candidate_info = state.get("candidate_info", {})
        customer_name = candidate_info.get("name") if candidate_info else None

        # Fallback to meeting_config display name if available
        if not customer_name:
            meeting_config = state.get("meeting_config") or state.get(
                "interview_config", {}
            )
            customer_name = (
                meeting_config.get("display_name") or "Interview Participant"
            )

        # IMPORTANT: Wait for meeting session to start before dialing
        # **Simple Explanation:** According to Daily.co docs, PIN dial-in requires
        # the meeting session to have started (when someone joins). The bot should join first
        # to start the meeting session, then we wait a bit before VAPI tries to dial.
        logger.info(
            "⏳ Waiting for meeting session to start (bot should have joined)..."
        )
        import asyncio

        await asyncio.sleep(
            3
        )  # Wait 3 seconds for meeting session to start after bot joins

        # Log what VAPI will do
        logger.info(
            f"📞 Creating VAPI call: Using phone {phone_number_id} to dial {daily_phone_number}, "
            f"then DTMF PIN {dialin_code}#"
        )

        try:
            result = await self._create_vapi_call(
                api_key=vapi_api_key,
                assistant_id=assistant_id,
                phone_number_id=phone_number_id,
                daily_phone_number=daily_phone_number,
                dialin_code=dialin_code,
                customer_name=customer_name,
            )

            if result.get("success"):
                state["vapi_call_id"] = result.get("call_id")
                state["vapi_call_created"] = True
                state = self.update_status(state, "vapi_call_created")
                logger.info(
                    f"✅ VAPI call created successfully: {result.get('call_id')}"
                )
            else:
                # VAPI call failure is non-fatal - room is still created and usable
                # **Simple Explanation:** Even if VAPI call fails, the room exists and can be used
                error_msg = result.get("message", "Unknown error creating VAPI call")
                logger.warning(f"⚠️ Failed to create VAPI call: {error_msg}")
                logger.warning(
                    "⚠️ Room is still available - VAPI call can be retried manually"
                )
                state["vapi_call_created"] = False
                state["vapi_call_error"] = error_msg
                # Don't fail the workflow - just mark VAPI as not created
                state = self.update_status(state, "vapi_call_failed")

        except Exception as e:
            error_msg = f"Failed to create VAPI call: {str(e)}"
            logger.error(f"❌ {error_msg}", exc_info=True)
            return self.set_error(state, error_msg)

        return state
