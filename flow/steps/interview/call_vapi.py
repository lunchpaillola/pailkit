# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Call VAPI Step

Makes an outbound call using VAPI to dial a SIP URI for joining a Daily.co room.
This enables the AI interviewer (via VAPI) to join the room via SIP.
"""

import logging
import os
from typing import Any, Dict

import httpx

from flow.steps.interview.base import InterviewStep

logger = logging.getLogger(__name__)


class CallVAPIStep(InterviewStep):
    """
    Step to make an outbound call using VAPI.

    **Simple Explanation:**
    This step calls VAPI's API to make an outbound call. VAPI will:
    1. Use the phoneNumberId to make an outbound call
    2. Dial the Daily.co SIP URI (customer.sipUri)
    3. This allows VAPI to join the Daily.co room via SIP
    4. Once in the room, VAPI acts as the AI interviewer
    """

    def __init__(self):
        super().__init__(
            name="call_vapi",
            description="Make outbound call using VAPI to join room via SIP",
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
        sip_uri: str,
        customer_name: str | None = None,
    ) -> Dict[str, Any]:
        """
        Create an outbound call using VAPI's API.

        **Simple Explanation:**
        This calls VAPI's API to start an outbound call. VAPI will:
        1. Use the phoneNumberId to make an outbound call
        2. Dial the Daily.co SIP URI (customer.sipUri)
        3. This allows VAPI to join the Daily.co room via SIP

        Args:
            api_key: VAPI API key
            assistant_id: VAPI assistant ID to use for the call
            phone_number_id: VAPI phone number ID to use for outbound calling
            sip_uri: Daily.co SIP URI endpoint (e.g., "sip:123456780@example.sip.daily.co")
            customer_name: Optional name of the candidate

        Returns:
            Dictionary with call creation result
        """
        headers = self._get_vapi_headers(api_key)

        # Ensure SIP URI has the "sip:" prefix (Daily.co may return it without prefix)
        # **Simple Explanation:** VAPI requires the full SIP URI format: "sip:username@domain"
        # Daily.co might return just "username@domain", so we add "sip:" if missing
        formatted_sip_uri = sip_uri.strip()
        if not formatted_sip_uri.startswith("sip:"):
            formatted_sip_uri = f"sip:{formatted_sip_uri}"

        # Get Daily.co phone number from environment variable
        # **Simple Explanation:** VAPI requires customer.number field for Twilio setup
        # When both number and sipUri are present, VAPI should use sipUri for the connection
        # The number field is used for Twilio routing but sipUri takes precedence for the actual dial
        daily_phone_number = os.getenv("DAILY_PHONE_NUMBER")

        # Format phone number to E.164 format (ensure it has + prefix)
        # **Simple Explanation:** VAPI requires E.164 format (e.g., "+12092080701")
        # If the number in .env doesn't have a +, we add it
        if daily_phone_number:
            formatted_phone = daily_phone_number.strip()
            if not formatted_phone.startswith("+"):
                formatted_phone = f"+{formatted_phone}"
        else:
            # Fallback to a valid placeholder if DAILY_PHONE_NUMBER not set
            # This should match your Twilio account's phone number format
            formatted_phone = "+12092080701"  # Default placeholder - update if needed

        # Build the request payload according to VAPI API documentation
        # **Simple Explanation:** Based on https://docs.vapi.ai/api-reference/calls/create
        # VAPI requires customer.number for Twilio setup, but when sipUri is present,
        # VAPI should use the SIP URI for the actual connection. The number is used for
        # Twilio routing/configuration but sipUri takes precedence.
        # VAPI API expects:
        # - assistantId: Which AI assistant to use (required)
        # - phoneNumberId: Which phone number to call from (required)
        # - customer: Object with customer information
        #   - sipUri: The SIP URI endpoint to dial (e.g., "sip:123456780@example.sip.daily.co")
        #   - number: Phone number in E.164 format (required by VAPI for Twilio setup)
        #   - name: Optional customer name
        # NOTE: When sipUri is present, VAPI should use it for the connection even if number is also provided
        payload = {
            "assistantId": assistant_id,
            "phoneNumberId": phone_number_id,
            "customer": {
                "sipUri": formatted_sip_uri,  # SIP URI endpoint - this should be used for the connection
                "number": formatted_phone,  # Required by VAPI for Twilio setup, but sipUri takes precedence
            },
        }

        # Add customer name if available
        if customer_name:
            payload["customer"]["name"] = customer_name

        logger.info(
            f"📱 Creating VAPI call: Using phone {phone_number_id} to dial SIP URI {formatted_sip_uri}"
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
        Execute VAPI outbound call.

        **Simple Explanation:**
        This checks if VAPI calling is enabled, gets the Daily.co SIP URI
        from the room creation step, and makes an outbound call. VAPI will dial the
        Daily.co SIP URI to join the room.
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

        # Get Daily.co SIP URI from state (set by create_room step)
        # **Simple Explanation:**
        # 1. CreateRoomStep enables SIP dial-in on the Daily.co room
        # 2. Daily.co returns a SIP URI endpoint (e.g., "sip:123456780@example.sip.daily.co")
        # 3. CreateRoomStep stores this in state as "sip_uri"
        # 4. We read it here to use for the VAPI call
        sip_uri = state.get("sip_uri")

        logger.info(f"📋 Reading SIP URI from state: sip_uri={sip_uri}")

        if not sip_uri:
            error_msg = (
                f"Missing sip_uri in state (required for VAPI calling). "
                f"sip_uri={sip_uri}. "
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

        # IMPORTANT: Wait for SIP worker to initialize after meeting session starts
        # **Simple Explanation:** According to Daily.co docs, the SIP worker starts after
        # the meeting session begins (when someone joins). The bot should join first to
        # start the meeting session, then we wait a bit for the SIP worker to initialize
        # and register the SIP URI with the SIP network before VAPI tries to dial.
        #
        # Daily.co docs: "Once the meeting session starts, the SIP worker(s) will startup
        # and when the SIP URIs are registered with the SIP network, dialin-ready will fire"
        logger.info(
            "⏳ Waiting for SIP worker to initialize (bot should have joined to start meeting)..."
        )
        import asyncio

        await asyncio.sleep(
            3
        )  # Wait 3 seconds for SIP worker to initialize after bot joins

        # Log what VAPI will do
        logger.info(
            f"📞 Creating VAPI call: Using phone {phone_number_id} to dial Daily.co SIP URI "
            f"{sip_uri}"
        )

        try:
            result = await self._create_vapi_call(
                api_key=vapi_api_key,
                assistant_id=assistant_id,
                phone_number_id=phone_number_id,
                sip_uri=sip_uri,
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
