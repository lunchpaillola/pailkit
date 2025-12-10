#!/usr/bin/env python3.12
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Test script for ExtractInsightsStep with PostHog Integration

This script tests the ExtractInsightsStep with dummy data to verify
that the PostHog OpenAI API integration works correctly.

Simple Explanation:
- Creates dummy Q&A pairs (questions and answers)
- Runs the ExtractInsightsStep to analyze them
- Verifies PostHog tracking is working
- Prints the results to verify everything works

Usage:
    python flow/scripts/test_extract_insights.py
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
    logger.info("Testing ExtractInsightsStep with PostHog Integration")
    logger.info("=" * 60)
    logger.info("\nThis test verifies:")
    logger.info("  1. PostHog client creation and configuration")
    logger.info("  2. ExtractInsightsStep execution with real API calls")
    logger.info("  3. PostHog tracking of LLM usage")

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

    # Create the initial state dictionary
    # Simple Explanation: The step needs a "state" dictionary that contains
    # all the information it needs to work. We're providing the Q&A pairs
    # and some optional metadata.
    state = {
        "qa_pairs": dummy_qa_pairs,
        "workflow_thread_id": "test_workflow_123",
        "room_name": "test_room",
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
        logger.info("PostHog Tracking Verification")
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
        else:
            logger.info("✅ Real AI insights were generated - API call succeeded!")

            # Check if PostHog was enabled
            if posthog_tracking_enabled:
                logger.info("✅ PostHog tracking was ENABLED for this call!")
                logger.info("   The LLM call should be tracked in PostHog")
                logger.info("\n   To verify PostHog tracking:")
                logger.info("   1. Go to your PostHog dashboard")
                logger.info("   2. Navigate to LLM Analytics → Traces or Generations")
                logger.info("   3. Look for events with:")
                logger.info(
                    "      - distinct_id: test_workflow_123 (or unkey_key_id if available)"
                )
                logger.info("      - step_name: extract_insights")
                logger.info("      - workflow_thread_id: test_workflow_123")
                logger.info("   4. Check that cost information is captured")
            else:
                logger.warning("⚠️  PostHog tracking was NOT enabled for this call")
                logger.warning(
                    "   Set POSTHOG_API_KEY to enable tracking and test the integration"
                )

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
