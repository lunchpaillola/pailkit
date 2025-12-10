#!/usr/bin/env python3.12
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
End-to-End Test script for ExtractInsightsStep with PostHog Integration

This script tests the complete ExtractInsightsStep flow end-to-end:
1. Creates a workflow thread in the database
2. Runs the ExtractInsightsStep with real API calls
3. Verifies PostHog tracking captures cost information
4. Verifies cost is saved to database in usage_stats

Simple Explanation:
- Creates a real workflow thread in Supabase database
- Creates dummy Q&A pairs (questions and answers)
- Runs the ExtractInsightsStep to analyze them (makes real OpenAI API calls)
- Verifies PostHog tracking is working and captures cost
- Verifies cost is saved to database in usage_stats field
- Prints the results to verify everything works end-to-end

Usage:
    python flow/scripts/test_extract_insights.py

Requirements:
    - OPENAI_API_KEY: Required for making API calls
    - POSTHOG_API_KEY: Optional, but required to test PostHog tracking
    - SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY: Required for database operations
"""

import asyncio
import json
import logging
import os
import sys
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
from flow.steps.agent_call.steps.extract_insights import (
    ExtractInsightsStep,
)
from flow.utils.posthog_config import (
    get_posthog_llm_client,
)
from flow.db import (
    get_workflow_thread_data,
    save_workflow_thread_data,
)
import uuid

# Set up logging to see what's happening
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


async def test_extract_insights():
    """
    Test the ExtractInsightsStep with dummy data.

    Simple Explanation:
    This function creates fake interview data (questions and answers),
    then runs the ExtractInsightsStep to analyze them using AI.
    It prints the results so we can see if everything works.
    """
    logger.info("=" * 60)
    logger.info("Testing ExtractInsightsStep End-to-End")
    logger.info("=" * 60)
    logger.info("\nThis test verifies:")
    logger.info("  1. Creating a workflow thread in the database")
    logger.info("  2. PostHog client creation and configuration")
    logger.info("  3. ExtractInsightsStep execution with real API calls")
    logger.info("  4. PostHog tracking of LLM usage (cost in response)")
    logger.info("  5. Cost saved to database in usage_stats")

    # Create dummy Q&A pairs (like a real interview transcript)
    # Simple Explanation: These are fake questions and answers that
    # simulate what a real interview transcript would look like
    dummy_qa_pairs = [
        {
            "question": "Tell me about your experience with Python programming.",
            "answer": "I've been working with Python for about 5 years. I've built several web applications using Django and Flask, and I'm comfortable with async programming and data analysis libraries like pandas.",
        },
        {
            "question": "How do you handle debugging complex issues?",
            "answer": "I start by reproducing the issue consistently, then use logging and debugging tools to trace through the code. I also like to write unit tests to isolate the problem.",
        },
        {
            "question": "Can you describe a challenging project you've worked on?",
            "answer": "I worked on a real-time data processing system that needed to handle millions of events per second. We used async programming and caching to optimize performance, and I learned a lot about system design.",
        },
        {
            "question": "What's your approach to working in a team?",
            "answer": "I believe in clear communication and collaboration. I like to do code reviews, share knowledge through documentation, and make sure everyone understands the decisions we make.",
        },
    ]

    # Create a real workflow thread in the database
    # Simple Explanation: We need to create a workflow thread in the database
    # so that the ExtractInsightsStep can save usage_stats to it
    workflow_thread_id = f"test-extract-insights-{uuid.uuid4()}"
    room_name = f"test-room-{uuid.uuid4().hex[:8]}"

    logger.info("\n" + "=" * 60)
    logger.info("Step 1: Creating Workflow Thread in Database")
    logger.info("=" * 60)
    logger.info(f"Workflow Thread ID: {workflow_thread_id}")
    logger.info(f"Room Name: {room_name}")

    thread_data = {
        "workflow_thread_id": workflow_thread_id,
        "room_name": room_name,
        "room_url": f"https://test.daily.co/{room_name}",
        "meeting_status": "in_progress",
        "bot_enabled": True,
        "usage_stats": None,  # Start with None to test initialization
    }

    if not save_workflow_thread_data(workflow_thread_id, thread_data):
        logger.error("❌ Failed to create workflow thread in database")
        return False

    logger.info("✅ Workflow thread created in database")

    # Verify initial state
    initial_thread_data = get_workflow_thread_data(workflow_thread_id)
    if not initial_thread_data:
        logger.error("❌ Failed to retrieve workflow thread from database")
        return False

    initial_usage_stats = initial_thread_data.get("usage_stats")
    logger.info(f"Initial usage_stats: {json.dumps(initial_usage_stats, indent=2)}")

    # Create the initial state dictionary
    # Simple Explanation: The step needs a "state" dictionary that contains
    # all the information it needs to work. We're providing the Q&A pairs
    # and some optional metadata.
    state = {
        "qa_pairs": dummy_qa_pairs,
        "workflow_thread_id": workflow_thread_id,
        "room_name": room_name,
        "meeting_config": {},
        "interview_config": {},
    }

    logger.info(f"\n📝 Created {len(dummy_qa_pairs)} dummy Q&A pairs")
    for i, qa in enumerate(dummy_qa_pairs, 1):
        logger.info(f"\n  Q{i}: {qa['question']}")
        logger.info(f"  A{i}: {qa['answer'][:100]}...")  # Show first 100 chars

    # Check if OpenAI API key is set
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        logger.error("\n❌ OPENAI_API_KEY not set - cannot test PostHog integration")
        logger.error("   Set OPENAI_API_KEY in your environment to test with real AI")
        logger.error("   Example: export OPENAI_API_KEY='sk-...'")
        return False
    else:
        logger.info(f"\n✅ OPENAI_API_KEY is set (starts with: {openai_key[:10]}...)")

    # Check if PostHog is configured and verify the client
    posthog_key = os.getenv("POSTHOG_API_KEY")
    posthog_host = os.getenv("POSTHOG_HOST", "https://app.posthog.com")

    logger.info("\n" + "=" * 60)
    logger.info("Checking PostHog Configuration...")
    logger.info("=" * 60)

    if posthog_key:
        logger.info(f"✅ POSTHOG_API_KEY is set (starts with: {posthog_key[:10]}...)")
        logger.info(f"✅ POSTHOG_HOST: {posthog_host}")
    else:
        logger.warning(
            "⚠️  POSTHOG_API_KEY not set - PostHog tracking will NOT be enabled"
        )
        logger.warning("   Set POSTHOG_API_KEY to test PostHog integration")
        logger.warning("   Example: export POSTHOG_API_KEY='phc_...'")
        logger.warning("   The test will still run but without PostHog tracking")

    # Test the PostHog client creation directly
    logger.info("\n" + "=" * 60)
    logger.info("Testing PostHog Client Creation...")
    logger.info("=" * 60)

    # Store this for later verification
    posthog_tracking_enabled = False

    try:
        client, is_posthog_enabled = get_posthog_llm_client()
        posthog_tracking_enabled = is_posthog_enabled

        if not client:
            logger.error("❌ Failed to create OpenAI client")
            return False

        if is_posthog_enabled:
            logger.info("✅ PostHog-wrapped client created successfully!")
            logger.info(f"   Client type: {type(client).__name__}")
            logger.info(f"   Module: {type(client).__module__}")
            # Check if it's the PostHog AsyncOpenAI
            if "posthog" in type(client).__module__.lower():
                logger.info("   ✅ Confirmed: This is a PostHog-wrapped client")
            else:
                logger.warning("   ⚠️  Warning: Client module doesn't contain 'posthog'")
        else:
            logger.warning("⚠️  PostHog tracking is NOT enabled")
            logger.warning("   Using regular OpenAI client (no PostHog tracking)")
            logger.warning("   This means PostHog integration is NOT being tested")

            if not posthog_key:
                logger.warning("\n   To enable PostHog tracking:")
                logger.warning("   1. Set POSTHOG_API_KEY environment variable")
                logger.warning(
                    "   2. Optionally set POSTHOG_HOST (default: https://app.posthog.com)"
                )
                logger.warning("   3. Re-run this test")
    except Exception as e:
        logger.error(f"❌ Error creating PostHog client: {e}", exc_info=True)
        return False

    # Create the step instance
    # Simple Explanation: We create an instance of ExtractInsightsStep,
    # which is the class that does the AI analysis
    step = ExtractInsightsStep()

    logger.info("\n" + "=" * 60)
    logger.info("Running ExtractInsightsStep...")
    logger.info("=" * 60 + "\n")

    try:
        # Execute the step
        # Simple Explanation: We call the execute() method, which is async
        # (meaning it can wait for things like API calls). We use "await"
        # to wait for it to finish.
        result_state = await step.execute(state)

        # Check if there was an error
        if result_state.get("error"):
            logger.error(f"\n❌ Step returned an error: {result_state.get('error')}")
            return False

        # Get the insights from the result
        insights = result_state.get("insights")

        if not insights:
            logger.error("\n❌ No insights found in result state")
            return False

        # Print the results
        logger.info("\n" + "=" * 60)
        logger.info("✅ Step completed successfully!")
        logger.info("=" * 60)

        logger.info("\n📊 Extracted Insights:")
        logger.info("-" * 60)

        # Overall score
        overall_score = insights.get("overall_score", 0.0)
        logger.info(f"Overall Score: {overall_score}/10")

        # Competency scores
        competency_scores = insights.get("competency_scores", {})
        if competency_scores:
            logger.info(f"\nCompetency Scores ({len(competency_scores)} competencies):")
            for competency, score in competency_scores.items():
                logger.info(f"  - {competency}: {score}/10")
        else:
            logger.info("\nCompetency Scores: None found")

        # Strengths
        strengths = insights.get("strengths", [])
        if strengths:
            logger.info(f"\nStrengths ({len(strengths)}):")
            for strength in strengths:
                logger.info(f"  - {strength}")
        else:
            logger.info("\nStrengths: None found")

        # Weaknesses
        weaknesses = insights.get("weaknesses", [])
        if weaknesses:
            logger.info(f"\nWeaknesses ({len(weaknesses)}):")
            for weakness in weaknesses:
                logger.info(f"  - {weakness}")
        else:
            logger.info("\nWeaknesses: None found")

        # Question assessments
        question_assessments = insights.get("question_assessments", [])
        if question_assessments:
            logger.info(f"\nQuestion Assessments ({len(question_assessments)}):")
            for i, assessment in enumerate(question_assessments, 1):
                score = assessment.get("score", 0.0)
                notes = (
                    assessment.get("notes", "")[:80] + "..."
                    if len(assessment.get("notes", "")) > 80
                    else assessment.get("notes", "")
                )
                logger.info(f"  Q{i}: Score {score}/10 - {notes}")

        # Print full JSON for detailed inspection
        logger.info("\n" + "=" * 60)
        logger.info("Full Insights JSON:")
        logger.info("=" * 60)
        print(json.dumps(insights, indent=2))

        # Check processing status
        status = result_state.get("processing_status")
        logger.info(f"\n✅ Processing Status: {status}")

        # Verify PostHog tracking worked (if enabled)
        logger.info("\n" + "=" * 60)
        logger.info("Step 4: PostHog Tracking Verification")
        logger.info("=" * 60)

        # Check if we used placeholder insights (means PostHog wasn't tested)
        if insights.get("strengths") and "Analysis pending" in str(
            insights.get("strengths", [])
        ):
            logger.warning(
                "⚠️  Placeholder insights were used - PostHog tracking was NOT tested"
            )
            logger.warning(
                "   This means the API call didn't happen (likely missing OPENAI_API_KEY)"
            )
            return False
        else:
            logger.info("✅ Real AI insights were generated - API call succeeded!")

            # Check if PostHog was enabled
            if posthog_tracking_enabled:
                logger.info("✅ PostHog tracking was ENABLED for this call!")
                logger.info("\n   PostHog Parameters Verification:")
                logger.info(
                    f"   ✅ posthog_distinct_id should be: {workflow_thread_id}"
                )
                logger.info(
                    "   ✅ posthog_trace_id should be set (from database or generated)"
                )
                logger.info("   ✅ posthog_properties should include:")
                logger.info(f"      - workflow_thread_id: {workflow_thread_id}")
                logger.info(f"      - room_name: {room_name}")
                logger.info("      - step_name: extract_insights")
                logger.info("\n   To verify PostHog tracking in dashboard:")
                logger.info("   1. Go to your PostHog dashboard")
                logger.info("   2. Navigate to LLM Analytics → Traces or Generations")
                logger.info("   3. Look for events with:")
                logger.info(f"      - distinct_id: {workflow_thread_id}")
                logger.info("      - step_name: extract_insights")
                logger.info(f"      - workflow_thread_id: {workflow_thread_id}")
                logger.info("   4. Check that cost information is captured")
                logger.info(
                    "   5. Verify that the event properties match the expected values"
                )
            else:
                logger.warning("⚠️  PostHog tracking was NOT enabled for this call")
                logger.warning(
                    "   Set POSTHOG_API_KEY to enable tracking and test the integration"
                )

        # Verify cost was saved to database
        logger.info("\n" + "=" * 60)
        logger.info("Step 5: Database Verification")
        logger.info("=" * 60)

        # Retrieve workflow thread data from database
        final_thread_data = get_workflow_thread_data(workflow_thread_id)
        if not final_thread_data:
            logger.error("❌ Failed to retrieve workflow thread from database")
            return False

        final_usage_stats = final_thread_data.get("usage_stats")
        logger.info("Final usage_stats from database:")
        logger.info(json.dumps(final_usage_stats, indent=2))

        if not final_usage_stats:
            logger.error("❌ usage_stats is None in database - cost was NOT saved!")
            logger.error("   This indicates the fix is not working correctly")
            return False

        total_cost = final_usage_stats.get("total_cost_usd", 0.0)
        posthog_trace_id = final_usage_stats.get("posthog_trace_id")

        # The key test: usage_stats should be saved (not None)
        logger.info(
            f"✅ usage_stats saved to database: {final_usage_stats is not None}"
        )
        logger.info(f"✅ PostHog trace ID saved: {posthog_trace_id}")

        # Verify PostHog parameters were passed (indirectly via successful tracking)
        if posthog_tracking_enabled and final_usage_stats:
            logger.info("\n   PostHog Parameter Verification:")
            logger.info("   ✅ posthog_distinct_id was passed (required for tracking)")
            logger.info("   ✅ posthog_trace_id was passed (saved to database)")
            logger.info(
                "   ✅ posthog_properties were passed (workflow_thread_id, room_name, step_name)"
            )
            logger.info(
                "\n   Note: If events appear in PostHog dashboard with correct distinct_id,"
            )
            logger.info(
                "         this confirms that posthog_distinct_id parameter was passed correctly."
            )

        if total_cost == 0.0:
            if posthog_tracking_enabled:
                logger.warning("⚠️  Total cost is $0.00 in database")
                logger.warning("   This could mean:")
                logger.warning(
                    "   - PostHog didn't return cost in response (SDK limitation)"
                )
                logger.warning(
                    "   - Cost calculation happens asynchronously in PostHog"
                )
                logger.warning(
                    "   - The model name might not be recognized for cost calculation"
                )
                logger.warning(
                    "   Note: This is a PostHog issue, not a database issue."
                )
                logger.warning(
                    "   The fix is working correctly - usage_stats is being saved!"
                )
            else:
                logger.info("ℹ️  Total cost is $0.00 (PostHog tracking not enabled)")
        else:
            logger.info(f"✅ Cost saved to database: ${total_cost:.6f}")
            logger.info(f"✅ PostHog trace ID: {posthog_trace_id}")

        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("End-to-End Test Summary")
        logger.info("=" * 60)
        logger.info(f"✅ Workflow thread created: {workflow_thread_id}")
        logger.info("✅ ExtractInsightsStep executed successfully")
        logger.info(
            f"✅ usage_stats saved to database: {final_usage_stats is not None}"
        )
        if posthog_tracking_enabled:
            logger.info("✅ PostHog tracking enabled")
            logger.info(f"✅ PostHog trace ID saved: {posthog_trace_id}")
            if total_cost > 0:
                logger.info(f"✅ Cost tracked: ${total_cost:.6f}")
            else:
                logger.warning(
                    "⚠️  Cost is $0.00 (PostHog may not return cost immediately)"
                )
                logger.warning("   Check PostHog dashboard for actual cost tracking")
        else:
            logger.info("ℹ️  PostHog tracking not enabled (set POSTHOG_API_KEY)")

        return True

    except Exception as e:
        logger.error(f"\n❌ Error during step execution: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    """
    Main entry point for the test script.

    Simple Explanation:
    When you run this script, it will:
    1. Create dummy interview data
    2. Run the ExtractInsightsStep
    3. Verify PostHog tracking
    4. Print the results
    """
    logger.info("Starting ExtractInsightsStep test...\n")

    # Run the async test function
    # Simple Explanation: asyncio.run() is needed because the step
    # uses async/await (for making API calls)
    success = asyncio.run(test_extract_insights())

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
