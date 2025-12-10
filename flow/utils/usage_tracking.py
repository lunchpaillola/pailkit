# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Usage Tracking Utilities

Simple helper functions for tracking LLM usage costs per workflow.
PostHog stores all detailed events - we only store aggregated totals here.
"""

import logging
from typing import Dict, Any

from flow.db import (
    get_workflow_thread_data,
    save_workflow_thread_data,
)

logger = logging.getLogger(__name__)


def update_workflow_usage_cost(
    workflow_thread_id: str, cost_usd: float, posthog_trace_id: str | None = None
) -> bool:
    """
    Update the total cost for a workflow thread.

    **Simple Explanation:**
    This function adds a cost amount to the total cost stored for a workflow.
    It reads the current total from the database, adds the new cost, and saves
    it back. This allows us to track how much money was spent on AI calls for
    each workflow run.

    Args:
        workflow_thread_id: Unique identifier for the workflow run
        cost_usd: Cost in USD to add to the total (can be 0.0 if no cost)
        posthog_trace_id: Optional PostHog trace ID to store for correlation

    Returns:
        True if updated successfully, False otherwise

    Example:
        ```python
        # After an LLM call that cost $0.05
        update_workflow_usage_cost("workflow_123", 0.05, "trace_456")
        ```
    """
    if not workflow_thread_id:
        logger.warning("⚠️ Cannot update usage cost: workflow_thread_id is required")
        return False

    try:
        # Get current workflow thread data
        thread_data = get_workflow_thread_data(workflow_thread_id)
        if not thread_data:
            logger.warning(
                f"⚠️ Workflow thread not found: {workflow_thread_id} - cannot update usage cost"
            )
            return False

        # Get current usage_stats or initialize with defaults
        # Simple Explanation: usage_stats is a JSON object stored in the database
        # It has fields like total_cost_usd and posthog_trace_id
        usage_stats: Dict[str, Any] = thread_data.get("usage_stats") or {}

        # Initialize if empty
        if not usage_stats:
            usage_stats = {
                "total_cost_usd": 0.0,
                "posthog_trace_id": None,
            }

        # Add the new cost to the existing total
        # Simple Explanation: We keep a running total of all costs for this workflow
        current_total = usage_stats.get("total_cost_usd", 0.0)
        new_total = current_total + cost_usd
        usage_stats["total_cost_usd"] = new_total

        # Update posthog_trace_id if provided (only set once, or update if needed)
        if posthog_trace_id:
            usage_stats["posthog_trace_id"] = posthog_trace_id

        # Save updated usage_stats back to database
        thread_data["usage_stats"] = usage_stats
        success = save_workflow_thread_data(workflow_thread_id, thread_data)

        if success:
            logger.debug(
                f"✅ Updated usage cost for {workflow_thread_id}: "
                f"${cost_usd:.6f} (total: ${new_total:.6f})"
            )
        else:
            logger.warning(
                f"⚠️ Failed to save usage cost update for {workflow_thread_id}"
            )

        return success

    except Exception as e:
        logger.error(
            f"❌ Error updating usage cost for {workflow_thread_id}: {e}",
            exc_info=True,
        )
        return False
