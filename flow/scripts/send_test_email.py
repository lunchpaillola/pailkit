#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Send a test email to verify the HTML email styling.

This script sends a test email with sample data to verify the email formatting.
"""

import asyncio
import json
import os
import sys

# Add project root to path
script_dir = os.path.dirname(os.path.abspath(__file__))
flow_dir = os.path.dirname(script_dir)
project_root = os.path.dirname(flow_dir)
sys.path.insert(0, project_root)

# Sample test data - JSON format like lead qualification produces
TEST_SUMMARY_JSON = {
    "call_name": "Lead Qualification Call",
    "lead": {
        "name": "John Smith",
        "problem": "I want to bake a cake for my daughter's birthday party this weekend.",
        "current_workaround": "I've tried following recipes online but they keep turning out wrong.",
        "timeline": "This weekend (urgent)",
        "budget": "$50-100",
        "decision_maker": "Just me",
        "quick_fit_score": 7.5,
    },
    "recommendation": "Schedule a discovery call to learn more about our baking solutions.",
}

TEST_SUMMARY = json.dumps(TEST_SUMMARY_JSON, indent=2)

TEST_TRANSCRIPT = """[2025-12-01T10:00:00.000+00:00] assistant: Hi! I'm going to ask you a few quick questions to see how we can help. This will only take a couple of minutes.

[2025-12-01T10:00:05.000+00:00] user: Yeah. That sounds great, actually.

[2025-12-01T10:00:10.000+00:00] assistant: What problem are you trying to solve?

[2025-12-01T10:00:15.000+00:00] user: I want to bake a cake for my daughter's birthday party this weekend. I've never been great at baking and I want it to turn out perfect.

[2025-12-01T10:00:25.000+00:00] assistant: I see, so you need to figure out how to bake a cake by today. Can you tell me more about what challenges you're facing with that?

[2025-12-01T10:00:30.000+00:00] user: I've tried following recipes online but they keep turning out wrong. The cakes are either too dry or don't rise properly.

[2025-12-01T10:00:40.000+00:00] assistant: What have you tried so far to solve this?

[2025-12-01T10:00:45.000+00:00] user: I've tried following recipes online but they keep turning out wrong. The cakes are either too dry or don't rise properly.

[2025-12-01T10:00:55.000+00:00] assistant: How soon do you need this solved?

[2025-12-01T10:01:00.000+00:00] user: This weekend - her birthday is on Saturday, so I need to have it ready by then.

[2025-12-01T10:01:10.000+00:00] assistant: What's your budget range for solving this?

[2025-12-01T10:01:15.000+00:00] user: I'm willing to spend around $50-100 to make sure it turns out well.

[2025-12-01T10:01:25.000+00:00] assistant: Who is involved in the decision-making process?

[2025-12-01T10:01:30.000+00:00] user: Just me - I'm the one making the cake, so it's my decision.

[2025-12-01T10:01:40.000+00:00] assistant: Perfect! I have everything I need. I'll send you a summary via email shortly. Thanks for your time!

[2025-12-01T10:01:45.000+00:00] user: Thanks for the call. Talk later. Bye bye.
"""


async def main():
    """Send test email using standalone script."""
    # Import the standalone version instead
    import subprocess

    print(f"\n{'='*80}")
    print("📧 Running standalone test email script...")
    print(f"{'='*80}\n")

    # Run the standalone script
    script_path = os.path.join(
        os.path.dirname(__file__), "send_test_email_standalone.py"
    )
    result = subprocess.run(
        [sys.executable, script_path],
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        capture_output=False,
    )

    sys.exit(result.returncode)


if __name__ == "__main__":
    asyncio.run(main())
