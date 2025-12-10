# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Pricing Module for LLM Cost Calculation

Provides model pricing information and cost calculation utilities.
"""

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
