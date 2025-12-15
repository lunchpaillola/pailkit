# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Pricing Module for LLM Cost Calculation

Provides model pricing information and cost calculation utilities.
"""

import os

# Deepgram STT Pricing (per minute)
DEEPGRAM_NOVA2_PER_MIN = 0.0058  # Nova-2 model pricing
DEEPGRAM_DIARIZATION_PER_MIN = 0.0020  # Speaker diarization pricing
DEEPGRAM_TOTAL_PER_MIN = (
    DEEPGRAM_NOVA2_PER_MIN + DEEPGRAM_DIARIZATION_PER_MIN
)  # Total: $0.0078/min

MODEL_PRICING = {
    # GPT-5 Series (Standard tier)
    "gpt-5.1": {
        "input": 1.25,  # dollars per 1,000,000 tokens
        "output": 10.00,
        "cached_input": 0.125,
        "unit": 1000000,
    },
    "gpt-5": {
        "input": 1.25,
        "output": 10.00,
        "cached_input": 0.125,
        "unit": 1000000,
    },
    "gpt-5-mini": {
        "input": 0.25,
        "output": 2.00,
        "cached_input": 0.025,
        "unit": 1000000,
    },
    "gpt-5-nano": {
        "input": 0.05,
        "output": 0.40,
        "cached_input": 0.005,
        "unit": 1000000,
    },
    "gpt-5.1-chat-latest": {
        "input": 1.25,
        "output": 10.00,
        "cached_input": 0.125,
        "unit": 1000000,
    },
    "gpt-5-chat-latest": {
        "input": 1.25,
        "output": 10.00,
        "cached_input": 0.125,
        "unit": 1000000,
    },
    "gpt-5.1-codex-max": {
        "input": 1.25,
        "output": 10.00,
        "cached_input": 0.125,
        "unit": 1000000,
    },
    "gpt-5.1-codex": {
        "input": 1.25,
        "output": 10.00,
        "cached_input": 0.125,
        "unit": 1000000,
    },
    "gpt-5-codex": {
        "input": 1.25,
        "output": 10.00,
        "cached_input": 0.125,
        "unit": 1000000,
    },
    "gpt-5-pro": {
        "input": 15.00,
        "output": 120.00,
        "unit": 1000000,
    },
    "gpt-5.1-codex-mini": {
        "input": 0.25,
        "output": 2.00,
        "cached_input": 0.025,
        "unit": 1000000,
    },
    "gpt-5-search-api": {
        "input": 1.25,
        "output": 10.00,
        "cached_input": 0.125,
        "unit": 1000000,
    },
    # GPT-4.1 Series (Standard tier)
    "gpt-4.1": {
        "input": 2.00,
        "output": 8.00,
        "cached_input": 0.50,
        "unit": 1000000,
    },
    "gpt-4.1-mini": {
        "input": 0.40,
        "output": 1.60,
        "cached_input": 0.10,
        "unit": 1000000,
    },
    "gpt-4.1-nano": {
        "input": 0.10,
        "output": 0.40,
        "cached_input": 0.025,
        "unit": 1000000,
    },
    # GPT-4o Series (Standard tier)
    "gpt-4o": {
        "input": 2.50,
        "output": 10.00,
        "cached_input": 1.25,
        "unit": 1000000,
    },
    "gpt-4o-2024-05-13": {
        "input": 5.00,
        "output": 15.00,
        "unit": 1000000,
    },
    "gpt-4o-mini": {
        "input": 0.15,
        "output": 0.60,
        "cached_input": 0.075,
        "unit": 1000000,
    },
    # GPT Realtime Series (Standard tier)
    "gpt-realtime": {
        "input": 4.00,
        "output": 16.00,
        "cached_input": 0.40,
        "unit": 1000000,
    },
    "gpt-realtime-mini": {
        "input": 0.60,
        "output": 2.40,
        "cached_input": 0.06,
        "unit": 1000000,
    },
    "gpt-4o-realtime-preview": {
        "input": 5.00,
        "output": 20.00,
        "cached_input": 2.50,
        "unit": 1000000,
    },
    "gpt-4o-mini-realtime-preview": {
        "input": 0.60,
        "output": 2.40,
        "cached_input": 0.30,
        "unit": 1000000,
    },
    # GPT Audio Series (Standard tier)
    "gpt-audio": {
        "input": 2.50,
        "output": 10.00,
        "unit": 1000000,
    },
    "gpt-audio-mini": {
        "input": 0.60,
        "output": 2.40,
        "unit": 1000000,
    },
    "gpt-4o-audio-preview": {
        "input": 2.50,
        "output": 10.00,
        "unit": 1000000,
    },
    "gpt-4o-mini-audio-preview": {
        "input": 0.15,
        "output": 0.60,
        "unit": 1000000,
    },
    # O-Series Models (Standard tier)
    "o1": {
        "input": 15.00,
        "output": 60.00,
        "cached_input": 7.50,
        "unit": 1000000,
    },
    "o1-pro": {
        "input": 150.00,
        "output": 600.00,
        "unit": 1000000,
    },
    "o1-mini": {
        "input": 1.10,
        "output": 4.40,
        "cached_input": 0.55,
        "unit": 1000000,
    },
    "o3": {
        "input": 2.00,
        "output": 8.00,
        "cached_input": 0.50,
        "unit": 1000000,
    },
    "o3-pro": {
        "input": 20.00,
        "output": 80.00,
        "unit": 1000000,
    },
    "o3-mini": {
        "input": 1.10,
        "output": 4.40,
        "cached_input": 0.55,
        "unit": 1000000,
    },
    "o3-deep-research": {
        "input": 10.00,
        "output": 40.00,
        "cached_input": 2.50,
        "unit": 1000000,
    },
    "o4-mini": {
        "input": 1.10,
        "output": 4.40,
        "cached_input": 0.275,
        "unit": 1000000,
    },
    "o4-mini-deep-research": {
        "input": 2.00,
        "output": 8.00,
        "cached_input": 0.50,
        "unit": 1000000,
    },
    # Other Models (Standard tier)
    "codex-mini-latest": {
        "input": 1.50,
        "output": 6.00,
        "cached_input": 0.375,
        "unit": 1000000,
    },
    "computer-use-preview": {
        "input": 3.00,
        "output": 12.00,
        "unit": 1000000,
    },
    # Legacy Models (Standard tier)
    "chatgpt-4o-latest": {
        "input": 5.00,
        "output": 15.00,
        "unit": 1000000,
    },
    "gpt-4-turbo-2024-04-09": {
        "input": 10.00,
        "output": 30.00,
        "unit": 1000000,
    },
    "gpt-4-0125-preview": {
        "input": 10.00,
        "output": 30.00,
        "unit": 1000000,
    },
    "gpt-4-1106-preview": {
        "input": 10.00,
        "output": 30.00,
        "unit": 1000000,
    },
    "gpt-4-1106-vision-preview": {
        "input": 10.00,
        "output": 30.00,
        "unit": 1000000,
    },
    "gpt-4-0613": {
        "input": 30.00,
        "output": 60.00,
        "unit": 1000000,
    },
    "gpt-4-0314": {
        "input": 30.00,
        "output": 60.00,
        "unit": 1000000,
    },
    "gpt-4-32k": {
        "input": 60.00,
        "output": 120.00,
        "unit": 1000000,
    },
    "gpt-3.5-turbo": {
        "input": 0.50,
        "output": 1.50,
        "unit": 1000000,
    },
    "gpt-3.5-turbo-0125": {
        "input": 0.50,
        "output": 1.50,
        "unit": 1000000,
    },
    "gpt-3.5-turbo-1106": {
        "input": 1.00,
        "output": 2.00,
        "unit": 1000000,
    },
    "gpt-3.5-turbo-0613": {
        "input": 1.50,
        "output": 2.00,
        "unit": 1000000,
    },
    "gpt-3.5-0301": {
        "input": 1.50,
        "output": 2.00,
        "unit": 1000000,
    },
    "gpt-3.5-turbo-instruct": {
        "input": 1.50,
        "output": 2.00,
        "unit": 1000000,
    },
    "gpt-3.5-turbo-16k-0613": {
        "input": 3.00,
        "output": 4.00,
        "unit": 1000000,
    },
    "davinci-002": {
        "input": 2.00,
        "output": 2.00,
        "unit": 1000000,
    },
    "babbage-002": {
        "input": 0.40,
        "output": 0.40,
        "unit": 1000000,
    },
}


def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """
    Calculate the cost of an LLM API call based on token usage.

    **Simple Explanation:**
    This function calculates how much money an LLM API call cost based on:
    - The model used (different models have different prices)
    - How many tokens were in the prompt (input)
    - How many tokens were in the response (output)

    Args:
        model: The model name (e.g., "gpt-4o", "gpt-4.1")
        prompt_tokens: Number of tokens in the input/prompt
        completion_tokens: Number of tokens in the output/completion

    Returns:
        Cost in USD (rounded to 6 decimal places)

    Example:
        ```python
        cost = calculate_cost("gpt-4o", 1000, 500)
        # Returns: 0.007500 (for gpt-4o: $2.50/1M input, $10/1M output)

        cost = calculate_cost("gpt-5", 1000, 500)
        # Returns: 0.006250 (for gpt-5: $1.25/1M input, $10/1M output)
        ```

    Raises:
        KeyError: If the model is not found in MODEL_PRICING
    """
    if model not in MODEL_PRICING:
        raise KeyError(
            f"Model '{model}' not found in MODEL_PRICING. "
            f"Available models: {list(MODEL_PRICING.keys())}"
        )

    pricing = MODEL_PRICING[model]
    unit = pricing["unit"]

    # Calculate cost: (tokens / unit) * price_per_unit
    input_cost = (prompt_tokens / unit) * pricing["input"]
    output_cost = (completion_tokens / unit) * pricing["output"]

    total_cost = input_cost + output_cost
    return round(total_cost, 6)


def calculate_deepgram_cost(duration_seconds: int) -> float:
    """
    Calculate the cost of Deepgram STT usage based on duration.

    **Simple Explanation:**
    This function calculates how much money Deepgram STT cost based on:
    - The duration of audio transcribed (in seconds)
    - Deepgram pricing: $0.0078 per minute (Nova-2 + diarization)

    Args:
        duration_seconds: Duration of audio in seconds

    Returns:
        Cost in USD (rounded to 6 decimal places)

    Example:
        ```python
        # 60 seconds (1 minute) of audio
        cost = calculate_deepgram_cost(60)
        # Returns: 0.007800

        # 120 seconds (2 minutes) of audio
        cost = calculate_deepgram_cost(120)
        # Returns: 0.015600
        ```
    """
    if duration_seconds < 0:
        raise ValueError("duration_seconds must be non-negative")

    # Convert seconds to minutes and multiply by per-minute rate
    duration_minutes = duration_seconds / 60.0
    cost = duration_minutes * DEEPGRAM_TOTAL_PER_MIN
    return round(cost, 6)


def calculate_bot_call_cost(duration_seconds: int) -> float:
    """
    Calculate the customer cost for a bot call based on duration.

    **Simple Explanation:**
    This function calculates how much to charge customers for bot call usage based on:
    - The duration of the call (in seconds)
    - Configurable rate per minute (default: $0.15/min, set via BOT_CALL_RATE_PER_MINUTE env var)

    Args:
        duration_seconds: Duration of the bot call in seconds

    Returns:
        Customer cost in USD (rounded to 6 decimal places)

    Example:
        ```python
        # 60 seconds (1 minute) of call at default $0.15/min
        cost = calculate_bot_call_cost(60)
        # Returns: 0.150000

        # 120 seconds (2 minutes) of call
        cost = calculate_bot_call_cost(120)
        # Returns: 0.300000
        ```
    """
    if duration_seconds < 0:
        raise ValueError("duration_seconds must be non-negative")

    # Get rate from environment variable, default to $0.15 per minute
    rate_per_minute = float(os.getenv("BOT_CALL_RATE_PER_MINUTE", "0.15"))

    # Convert seconds to minutes and multiply by per-minute rate
    duration_minutes = duration_seconds / 60.0
    cost = duration_minutes * rate_per_minute
    return round(cost, 6)
