# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Metrics Processor for Pipecat-ai Bot

Captures MetricsFrame events from Pipecat pipeline and aggregates usage statistics.
Sends usage data to PostHog and stores in workflow_threads table.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from pipecat.frames.frames import MetricsFrame
    from pipecat.processors.frame_processor import FrameProcessor
    from pipecat.metrics.metrics import LLMUsageMetricsData, TTSUsageMetricsData
except ImportError:
    logger.warning("⚠️ Pipecat not available - metrics processor will not work")
    MetricsFrame = None
    FrameProcessor = None
    LLMUsageMetricsData = None
    TTSUsageMetricsData = None


class UsageMetricsProcessor(FrameProcessor):
    """
    Frame processor that captures MetricsFrame events and aggregates usage statistics.

    **Simple Explanation:**
    This processor listens for metrics events from the Pipecat pipeline (like token usage)
    and saves them to the database. It's inserted into the pipeline after the LLM service
    so it can capture all LLM usage metrics.
    """

    def __init__(self, workflow_thread_id: Optional[str] = None):
        """
        Initialize the metrics processor.

        Args:
            workflow_thread_id: Workflow thread ID to associate usage stats with
        """
        if FrameProcessor is None:
            raise ImportError(
                "Pipecat not available - cannot create UsageMetricsProcessor"
            )

        super().__init__()
        self.workflow_thread_id = workflow_thread_id
        self._usage_data = []  # Store usage data for aggregation

    async def process_frame(self, frame: Any, direction: str) -> None:
        """
        Process frames and capture MetricsFrame events.

        **Simple Explanation:**
        This method is called for every frame in the pipeline. When it sees a MetricsFrame
        (which contains usage data), it extracts the usage information and saves it.
        """
        # Only process MetricsFrame events
        if not isinstance(frame, MetricsFrame):
            await self.push_frame(frame, direction)
            return

        # Extract metrics data
        metrics_data = frame.data

        # Process LLM usage metrics
        if isinstance(metrics_data, LLMUsageMetricsData):
            await self._process_llm_metrics(metrics_data)

        # Process TTS usage metrics if needed (optional)
        # if isinstance(metrics_data, TTSUsageMetricsData):
        #     await self._process_tts_metrics(metrics_data)

        # Pass the frame through to the next processor
        await self.push_frame(frame, direction)

    async def _process_llm_metrics(self, metrics_data: LLMUsageMetricsData) -> None:
        """
        Process LLM usage metrics and save to database.

        **Simple Explanation:**
        When the LLM is used, this method extracts the token counts and saves them
        to the database so we can track usage.
        """
        if not self.workflow_thread_id:
            logger.debug("No workflow_thread_id - skipping metrics capture")
            return

        try:
            prompt_tokens = metrics_data.prompt_tokens or 0
            completion_tokens = metrics_data.completion_tokens or 0
            total_tokens = prompt_tokens + completion_tokens

            # Get model name from metrics (if available)
            model = getattr(metrics_data, "model", "gpt-4o")  # Default to gpt-4o

            # Calculate cost (gpt-4o pricing as of 2025: $2.50/$10 per 1M tokens input/output)
            input_cost_per_1k = (
                2.50 / 1000
            )  # $2.50 per 1M tokens = $0.0025 per 1K tokens
            output_cost_per_1k = 10.0 / 1000  # $10 per 1M tokens = $0.01 per 1K tokens
            cost_usd = (prompt_tokens / 1000 * input_cost_per_1k) + (
                completion_tokens / 1000 * output_cost_per_1k
            )

            # Store usage data for aggregation
            usage_entry = {
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cost_usd": cost_usd,
            }
            self._usage_data.append(usage_entry)

            # Get workflow thread data to find unkey_key_id
            from flow.db import (
                aggregate_usage_stats,
                get_workflow_thread_data,
                save_workflow_thread_data,
            )

            thread_data = get_workflow_thread_data(self.workflow_thread_id)
            if not thread_data:
                logger.warning(
                    f"⚠️ Could not find workflow_thread_data for {self.workflow_thread_id} - skipping usage tracking"
                )
                return

            unkey_key_id = thread_data.get("unkey_key_id")
            if not unkey_key_id:
                logger.debug(
                    f"No unkey_key_id found for workflow_thread_id {self.workflow_thread_id}"
                )
                return

            # Aggregate usage stats
            existing_stats = thread_data.get("usage_stats")
            aggregated_stats = aggregate_usage_stats(existing_stats, usage_entry)

            # Update workflow_thread_data
            thread_data["usage_stats"] = aggregated_stats
            save_workflow_thread_data(self.workflow_thread_id, thread_data)

            # Send to PostHog
            from flow.utils.posthog_config import capture_llm_generation

            capture_llm_generation(
                distinct_id=unkey_key_id,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost_usd=cost_usd,
                properties={
                    "workflow_thread_id": self.workflow_thread_id,
                    "step": "bot_llm",
                },
            )

            logger.debug(
                f"✅ Captured LLM usage: {model}, {total_tokens} tokens, ${cost_usd:.6f}"
            )

        except Exception as e:
            logger.error(
                f"❌ Error processing LLM metrics: {e}",
                exc_info=True,
            )
