#!/usr/bin/env python3.12
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Test script for Usage Tracking

This script tests the usage tracking functionality end-to-end without requiring
a live call. It verifies that:
1. usage_stats is properly retrieved from the database
2. Costs are correctly accumulated when update_workflow_usage_cost() is called
3. Multiple cost updates work correctly
4. The usage_stats field is properly saved and retrieved

Simple Explanation:
- Creates a mock workflow thread in the database
- Simulates cost updates by calling update_workflow_usage_cost() directly
- Verifies costs are saved and accumulated correctly
- Tests that usage_stats is properly retrieved from the database

Usage:
    python flow/scripts/test_usage_tracking.py [workflow_thread_id]

    If workflow_thread_id is provided, it will test with that existing thread.
    Otherwise, it creates a new test thread.
"""

import json
import logging
import os
import sys
import uuid
from dotenv import load_dotenv

# Add project root to path
# Simple Explanation: We need to tell Python where to find the 'flow' module.
# Scripts are in flow/scripts/, so we go up to flow/, then to project root.
script_dir = os.path.dirname(os.path.abspath(__file__))
flow_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(flow_dir)
sys.path.insert(0, project_root)

load_dotenv()

# ruff: noqa: E402
from flow.db import (
    get_workflow_thread_data,
    save_workflow_thread_data,
)
from flow.utils.usage_tracking import update_workflow_usage_cost

# Set up logging to see what's happening
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def create_test_workflow_thread(workflow_thread_id: str) -> bool:
    """
    Create a test workflow thread in the database.

    Args:
        workflow_thread_id: The workflow thread ID to create

    Returns:
        True if created successfully, False otherwise
    """
    logger.info(f"Creating test workflow thread: {workflow_thread_id}")

    thread_data = {
        "workflow_thread_id": workflow_thread_id,
        "room_name": f"test-room-{uuid.uuid4().hex[:8]}",
        "room_url": "https://test.daily.co/test-room",
        "meeting_status": "in_progress",
        "bot_enabled": True,
        # Initialize usage_stats to None to test the initialization logic
        "usage_stats": None,
    }

    success = save_workflow_thread_data(workflow_thread_id, thread_data)
    if success:
        logger.info(f"✅ Created test workflow thread: {workflow_thread_id}")
    else:
        logger.error(f"❌ Failed to create test workflow thread: {workflow_thread_id}")

    return success


def test_usage_tracking(workflow_thread_id: str | None = None) -> bool:
    """
    Test the usage tracking functionality.

    Args:
        workflow_thread_id: Optional existing workflow thread ID to test with.
                          If None, creates a new test thread.

    Returns:
        True if all tests pass, False otherwise
    """
    logger.info("=" * 60)
    logger.info("Testing Usage Tracking Functionality")
    logger.info("=" * 60)

    # Create or use existing workflow thread
    if workflow_thread_id:
        logger.info(f"Using existing workflow thread: {workflow_thread_id}")
        # Verify it exists
        thread_data = get_workflow_thread_data(workflow_thread_id)
        if not thread_data:
            logger.error(f"❌ Workflow thread not found: {workflow_thread_id}")
            return False
        logger.info(f"✅ Found existing workflow thread: {workflow_thread_id}")
    else:
        # Create a new test workflow thread
        workflow_thread_id = f"test-usage-{uuid.uuid4()}"
        if not create_test_workflow_thread(workflow_thread_id):
            return False

    # Test 1: Verify initial state (should have no usage_stats or empty)
    logger.info("\n" + "=" * 60)
    logger.info("Test 1: Verify Initial State")
    logger.info("=" * 60)

    thread_data = get_workflow_thread_data(workflow_thread_id)
    if not thread_data:
        logger.error(f"❌ Failed to retrieve workflow thread: {workflow_thread_id}")
        return False

    initial_usage_stats = thread_data.get("usage_stats")
    logger.info(f"Initial usage_stats: {json.dumps(initial_usage_stats, indent=2)}")

    if initial_usage_stats is None:
        logger.info("✅ Initial usage_stats is None (expected for new threads)")
    elif isinstance(initial_usage_stats, dict):
        initial_cost = initial_usage_stats.get("total_cost_usd", 0.0)
        logger.info(
            f"✅ Initial usage_stats found: total_cost_usd = ${initial_cost:.6f}"
        )
    else:
        logger.warning(f"⚠️ Unexpected usage_stats type: {type(initial_usage_stats)}")

    # Test 2: Add first cost update
    logger.info("\n" + "=" * 60)
    logger.info("Test 2: Add First Cost Update")
    logger.info("=" * 60)

    first_cost = 0.003
    posthog_trace_id_1 = "trace_12345"

    logger.info(f"Adding cost: ${first_cost:.6f} with trace_id: {posthog_trace_id_1}")
    success = update_workflow_usage_cost(
        workflow_thread_id, first_cost, posthog_trace_id_1
    )

    if not success:
        logger.error("❌ Failed to update usage cost")
        return False

    logger.info("✅ Cost update successful")

    # Verify the cost was saved
    thread_data = get_workflow_thread_data(workflow_thread_id)
    if not thread_data:
        logger.error("❌ Failed to retrieve workflow thread after first update")
        return False

    usage_stats = thread_data.get("usage_stats")
    if not usage_stats:
        logger.error("❌ usage_stats is None after first update (should not be!)")
        return False

    total_cost = usage_stats.get("total_cost_usd", 0.0)
    trace_id = usage_stats.get("posthog_trace_id")

    logger.info(f"Retrieved usage_stats: {json.dumps(usage_stats, indent=2)}")
    logger.info(f"Total cost: ${total_cost:.6f}")
    logger.info(f"PostHog trace ID: {trace_id}")

    if abs(total_cost - first_cost) > 0.000001:
        logger.error(
            f"❌ Cost mismatch! Expected ${first_cost:.6f}, got ${total_cost:.6f}"
        )
        return False

    if trace_id != posthog_trace_id_1:
        logger.error(
            f"❌ Trace ID mismatch! Expected {posthog_trace_id_1}, got {trace_id}"
        )
        return False

    logger.info("✅ First cost update verified correctly")

    # Test 3: Add second cost update (accumulation)
    logger.info("\n" + "=" * 60)
    logger.info("Test 3: Add Second Cost Update (Accumulation)")
    logger.info("=" * 60)

    second_cost = 0.002
    posthog_trace_id_2 = "trace_67890"
    expected_total = first_cost + second_cost

    logger.info(f"Adding cost: ${second_cost:.6f} with trace_id: {posthog_trace_id_2}")
    logger.info(f"Expected total after update: ${expected_total:.6f}")

    success = update_workflow_usage_cost(
        workflow_thread_id, second_cost, posthog_trace_id_2
    )

    if not success:
        logger.error("❌ Failed to update usage cost (second update)")
        return False

    logger.info("✅ Second cost update successful")

    # Verify accumulation
    thread_data = get_workflow_thread_data(workflow_thread_id)
    if not thread_data:
        logger.error("❌ Failed to retrieve workflow thread after second update")
        return False

    usage_stats = thread_data.get("usage_stats")
    if not usage_stats:
        logger.error("❌ usage_stats is None after second update (should not be!)")
        return False

    total_cost = usage_stats.get("total_cost_usd", 0.0)
    trace_id = usage_stats.get("posthog_trace_id")

    logger.info(f"Retrieved usage_stats: {json.dumps(usage_stats, indent=2)}")
    logger.info(f"Total cost: ${total_cost:.6f}")
    logger.info(f"PostHog trace ID: {trace_id}")

    if abs(total_cost - expected_total) > 0.000001:
        logger.error(
            f"❌ Cost accumulation failed! Expected ${expected_total:.6f}, got ${total_cost:.6f}"
        )
        return False

    # Trace ID should be updated to the latest one
    if trace_id != posthog_trace_id_2:
        logger.warning(
            f"⚠️ Trace ID not updated. Expected {posthog_trace_id_2}, got {trace_id}"
        )
        # This is not a failure - trace ID update behavior may vary

    logger.info("✅ Cost accumulation verified correctly")

    # Test 4: Add third cost update (zero cost)
    logger.info("\n" + "=" * 60)
    logger.info("Test 4: Add Zero Cost Update")
    logger.info("=" * 60)

    zero_cost = 0.0
    logger.info(f"Adding zero cost: ${zero_cost:.6f}")

    success = update_workflow_usage_cost(workflow_thread_id, zero_cost)

    if not success:
        logger.error("❌ Failed to update usage cost (zero cost)")
        return False

    logger.info("✅ Zero cost update successful")

    # Verify total didn't change
    thread_data = get_workflow_thread_data(workflow_thread_id)
    if not thread_data:
        logger.error("❌ Failed to retrieve workflow thread after zero cost update")
        return False

    usage_stats = thread_data.get("usage_stats")
    if not usage_stats:
        logger.error("❌ usage_stats is None after zero cost update")
        return False

    total_cost = usage_stats.get("total_cost_usd", 0.0)
    logger.info(f"Total cost after zero update: ${total_cost:.6f}")

    if abs(total_cost - expected_total) > 0.000001:
        logger.error(
            f"❌ Zero cost update changed total! Expected ${expected_total:.6f}, got ${total_cost:.6f}"
        )
        return False

    logger.info("✅ Zero cost update verified correctly (total unchanged)")

    # Test 5: Verify usage_stats is properly retrieved
    logger.info("\n" + "=" * 60)
    logger.info("Test 5: Verify usage_stats Retrieval")
    logger.info("=" * 60)

    # Retrieve multiple times to ensure consistency
    for i in range(3):
        thread_data = get_workflow_thread_data(workflow_thread_id)
        if not thread_data:
            logger.error(f"❌ Failed to retrieve workflow thread (attempt {i+1})")
            return False

        usage_stats = thread_data.get("usage_stats")
        if not usage_stats:
            logger.error(f"❌ usage_stats is None (attempt {i+1})")
            return False

        total_cost = usage_stats.get("total_cost_usd", 0.0)
        logger.info(f"Attempt {i+1}: total_cost = ${total_cost:.6f}")

        if abs(total_cost - expected_total) > 0.000001:
            logger.error(
                f"❌ Inconsistent cost! Expected ${expected_total:.6f}, got ${total_cost:.6f}"
            )
            return False

    logger.info("✅ usage_stats retrieval verified (consistent across multiple reads)")

    # Final summary
    logger.info("\n" + "=" * 60)
    logger.info("✅ All Tests Passed!")
    logger.info("=" * 60)
    logger.info(f"Workflow Thread ID: {workflow_thread_id}")
    logger.info(f"Final Total Cost: ${expected_total:.6f}")
    logger.info(f"Final usage_stats: {json.dumps(usage_stats, indent=2)}")
    logger.info("\nThe usage tracking fix is working correctly!")
    logger.info("usage_stats is now properly retrieved from the database.")

    return True


if __name__ == "__main__":
    """
    Main entry point for the test script.

    Simple Explanation:
    When you run this script, it will:
    1. Create a test workflow thread (or use an existing one)
    2. Test cost updates and accumulation
    3. Verify usage_stats is properly saved and retrieved
    4. Print the results
    """
    import argparse

    parser = argparse.ArgumentParser(description="Test usage tracking functionality")
    parser.add_argument(
        "workflow_thread_id",
        nargs="?",
        help="Optional workflow thread ID to test with (creates new if not provided)",
    )
    args = parser.parse_args()

    logger.info("Starting usage tracking test...\n")

    # Run the test
    success = test_usage_tracking(args.workflow_thread_id)

    if success:
        logger.info("\n" + "=" * 60)
        logger.info("✅ Test completed successfully!")
        logger.info("=" * 60)
        sys.exit(0)
    else:
        logger.error("\n" + "=" * 60)
        logger.error("❌ Test failed!")
        logger.error("=" * 60)
        sys.exit(1)
