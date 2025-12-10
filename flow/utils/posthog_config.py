# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
PostHog Configuration Module

Provides PostHog client initialization and helper functions for LLM analytics tracking.
Handles graceful degradation when PostHog is not configured (dev/local environments).
"""

import logging
import os
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Global PostHog client instance (singleton)
_posthog_client: Optional[Any] = None


def get_posthog_client() -> Optional[Any]:
    """
    Get the PostHog client instance (singleton pattern).

    **Simple Explanation:**
    This function returns a PostHog client that can track LLM usage. If PostHog
    is not configured (missing environment variables), it returns None and tracking
    is gracefully skipped.

    Returns:
        PostHog client instance if configured, None otherwise
    """
    global _posthog_client

    # Return existing client if already initialized
    if _posthog_client is not None:
        return _posthog_client

    # Check if PostHog is configured
    posthog_api_key = os.getenv("POSTHOG_API_KEY")
    posthog_host = os.getenv("POSTHOG_HOST", "https://app.posthog.com")

    if not posthog_api_key:
        logger.debug(
            "PostHog not configured (POSTHOG_API_KEY not set) - LLM tracking disabled"
        )
        return None

    try:
        from posthog import Posthog

        # Initialize PostHog client
        _posthog_client = Posthog(
            project_api_key=posthog_api_key,
            host=posthog_host,
        )
        logger.info(f"✅ PostHog client initialized (host: {posthog_host})")
        return _posthog_client
    except ImportError:
        logger.warning(
            "⚠️ PostHog package not installed. Install with: pip install posthog>=3.0.0"
        )
        return None
    except Exception as e:
        logger.error(f"❌ Error initializing PostHog client: {e}", exc_info=True)
        return None


def capture_llm_generation(
    distinct_id: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    cost_usd: float,
    latency_ms: Optional[float] = None,
    properties: Optional[dict] = None,
) -> bool:
    """
    Manually capture an LLM generation event to PostHog.

    **Simple Explanation:**
    This function sends LLM usage data to PostHog for tracking. It's used for
    LLM calls that can't be automatically tracked (like Pipecat-ai bot calls).

    Args:
        distinct_id: Unique identifier for the user/API key (e.g., api_key_id)
        model: LLM model name (e.g., "gpt-4o")
        prompt_tokens: Number of tokens in the prompt
        completion_tokens: Number of tokens in the completion
        total_tokens: Total tokens used
        cost_usd: Cost in USD
        latency_ms: Latency in milliseconds (optional)
        properties: Additional properties to include (optional)

    Returns:
        True if event was captured, False otherwise
    """
    client = get_posthog_client()
    if not client:
        return False

    try:
        event_properties = {
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_usd": cost_usd,
        }

        if latency_ms is not None:
            event_properties["latency_ms"] = latency_ms

        if properties:
            event_properties.update(properties)

        # Capture the event
        client.capture(
            distinct_id=distinct_id,
            event="llm_generation",
            properties=event_properties,
        )

        logger.debug(
            f"✅ Captured LLM generation to PostHog: {model}, {total_tokens} tokens, ${cost_usd:.6f}"
        )
        return True
    except Exception as e:
        logger.error(
            f"❌ Error capturing LLM generation to PostHog: {e}", exc_info=True
        )
        return False


def get_posthog_llm_client(
    openai_api_key: Optional[str] = None,
) -> Tuple[Any, bool]:
    """
    Get a PostHog-wrapped OpenAI client for automatic LLM usage tracking.

    **Simple Explanation:**
    This function returns an OpenAI client that automatically tracks all LLM calls
    to PostHog. If PostHog is not configured, it returns a regular OpenAI client
    without tracking (graceful degradation).

    The PostHog-wrapped client automatically:
    - Tracks all LLM API calls (tokens, latency, costs)
    - Calculates costs using OpenRouter pricing data
    - Stores detailed events in PostHog for analysis
    - Returns cost information in the response

    Args:
        openai_api_key: OpenAI API key. If not provided, reads from OPENAI_API_KEY
                        environment variable.

    Returns:
        Tuple of (client, is_posthog_enabled):
        - client: PostHog-wrapped AsyncOpenAI client if PostHog is configured,
                  otherwise regular AsyncOpenAI client
        - is_posthog_enabled: True if PostHog tracking is active, False otherwise

    Example:
        ```python
        client, is_tracking = get_posthog_llm_client()
        if is_tracking:
            # PostHog is tracking - use client.responses.create()
            # PostHog uses responses.create() with input parameter (not messages)
            response = await client.responses.create(
                model="gpt-4o",
                input=[{"role": "user", "content": "Hello"}],
                posthog_distinct_id="user_123",
                posthog_trace_id="trace_456",
                posthog_properties={"workflow_id": "abc123"},
            )
            # Access response text using output_text attribute
            content = response.output_text
            # Extract cost from response
            cost = getattr(response, "$ai_total_cost_usd", 0.0)
        else:
            # Fallback to regular API (standard OpenAI API)
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": "Hello"}],
            )
            content = response.choices[0].message.content
        ```
    """
    # Get OpenAI API key
    if not openai_api_key:
        openai_api_key = os.getenv("OPENAI_API_KEY")

    if not openai_api_key:
        logger.warning("⚠️ OPENAI_API_KEY not set - cannot create OpenAI client")
        # Return None client and False for tracking
        return None, False

    # Try to get PostHog client
    posthog_client = get_posthog_client()

    if not posthog_client:
        # PostHog not configured - return regular AsyncOpenAI client
        logger.debug(
            "PostHog not configured - using regular AsyncOpenAI client (no tracking)"
        )
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=openai_api_key)
            return client, False
        except ImportError:
            logger.error(
                "❌ OpenAI package not installed. Install with: pip install openai"
            )
            return None, False

    # PostHog is configured - return PostHog-wrapped client
    try:
        from posthog.ai.openai import AsyncOpenAI

        # Create PostHog-wrapped AsyncOpenAI client
        # Simple Explanation: This wraps the regular OpenAI client with PostHog
        # tracking. All API calls will be automatically tracked.
        client = AsyncOpenAI(
            api_key=openai_api_key,
            posthog_client=posthog_client,
        )

        logger.debug("✅ PostHog-wrapped OpenAI client created (LLM tracking enabled)")
        return client, True
    except ImportError:
        logger.warning(
            "⚠️ PostHog LLM Analytics SDK not available. "
            "Install with: pip install 'posthog[ai]>=3.0.0'. "
            "Falling back to regular AsyncOpenAI client."
        )
        # Fallback to regular client
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=openai_api_key)
            return client, False
        except ImportError:
            logger.error(
                "❌ OpenAI package not installed. Install with: pip install openai"
            )
            return None, False
    except Exception as e:
        logger.error(
            f"❌ Error creating PostHog-wrapped OpenAI client: {e}",
            exc_info=True,
        )
        # Fallback to regular client
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=openai_api_key)
            logger.debug("✅ Fallback to regular AsyncOpenAI client")
            return client, False
        except ImportError:
            logger.error(
                "❌ OpenAI package not installed. Install with: pip install openai"
            )
            return None, False
