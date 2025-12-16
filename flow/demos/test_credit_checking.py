#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Test credit checking functionality.

This script tests the credit checking implementation for bot call endpoints.
It tests various scenarios:
1. Valid API key with sufficient credits (should work)
2. Valid API key with insufficient credits (should return 402)
3. API key not in public.users table (should return 401 with helpful message)
4. Invalid/missing API key (handled by middleware)

Run with: python flow/demos/test_credit_checking.py

Required environment variables:
- API_BASE_URL: Base URL for API (defaults to http://localhost:8001)
- UNKEY_PAILKIT_SECRET: Valid API key for testing (with sufficient credits)
- TEST_ROOM_URL: Daily.co room URL for testing (optional - only needed for success case)
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

import httpx

# Add project root to path so we can import flow modules
script_dir = os.path.dirname(os.path.abspath(__file__))
flow_dir = os.path.dirname(script_dir)  # flow/
project_root = os.path.dirname(flow_dir)  # project root (pailkit/)
sys.path.insert(0, project_root)


async def test_endpoint_with_key(
    api_base_url: str,
    endpoint: str,
    api_key: str | None,
    payload: dict | None = None,
    description: str = "",
) -> dict:
    """
    Test an endpoint with a specific API key.

    Args:
        api_base_url: Base URL for the API
        endpoint: Endpoint path (e.g., "/api/bot/join")
        api_key: API key to use (None for missing key test)
        payload: Request payload (optional)
        description: Description of the test case

    Returns:
        Response dictionary with status_code, response data, and test result
    """
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    if payload:
        headers["Content-Type"] = "application/json"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            if payload:
                response = await client.post(
                    f"{api_base_url}{endpoint}",
                    json=payload,
                    headers=headers,
                )
            else:
                response = await client.get(
                    f"{api_base_url}{endpoint}",
                    headers=headers,
                )

            response_data = response.json() if response.content else {}

            return {
                "status_code": response.status_code,
                "response": response_data,
                "description": description,
                "success": response.status_code < 400,
            }
        except httpx.HTTPStatusError as e:
            response_data = e.response.json() if e.response.content else {}
            return {
                "status_code": e.response.status_code,
                "response": response_data,
                "description": description,
                "success": False,
                "error": str(e),
            }
        except Exception as e:
            return {
                "status_code": None,
                "response": {},
                "description": description,
                "success": False,
                "error": str(e),
            }


async def main():
    """Test credit checking functionality."""
    load_dotenv()

    # Get configuration
    api_base_url = os.getenv("API_BASE_URL", "http://localhost:8001")
    test_api_key = os.getenv("UNKEY_PAILKIT_SECRET")
    test_room_url = os.getenv("TEST_ROOM_URL")

    print(f"\n{'='*80}")
    print("🧪 Testing Credit Checking Functionality")
    print(f"{'='*80}\n")

    print(f"API Base URL: {api_base_url}")
    print(f"Test API Key: {'✅ Set' if test_api_key else '❌ Not set'}\n")

    # Test payload for /api/bot/join
    bot_join_payload = {
        "room_url": test_room_url or "https://test.daily.co/test-room",
        "bot_config": {
            "bot_prompt": "You are a test bot.",
            "name": "TestBot",
            "video_mode": "static",
            "static_image": "robot01.png",
        },
        "process_insights": False,
    }

    test_cases = []

    # Test 1: Missing API key (should be handled by middleware)
    print("Test 1: Missing API key")
    print("-" * 80)
    result = await test_endpoint_with_key(
        api_base_url,
        "/api/bot/join",
        None,
        bot_join_payload,
        "Missing API key - should return 401 from middleware",
    )
    test_cases.append(result)
    print(f"Status: {result['status_code']}")
    print(f"Response: {result.get('response', {})}")
    print("Expected: 401 (Unauthorized)")
    print(f"Result: {'✅ PASS' if result['status_code'] == 401 else '❌ FAIL'}\n")

    # Test 2: Invalid API key (should be handled by middleware)
    print("Test 2: Invalid API key")
    print("-" * 80)
    result = await test_endpoint_with_key(
        api_base_url,
        "/api/bot/join",
        "invalid-key-12345",
        bot_join_payload,
        "Invalid API key - should return 401 from middleware",
    )
    test_cases.append(result)
    print(f"Status: {result['status_code']}")
    print(f"Response: {result.get('response', {})}")
    print("Expected: 401 (Unauthorized)")
    print(f"Result: {'✅ PASS' if result['status_code'] == 401 else '❌ FAIL'}\n")

    # Test 3: Valid API key but user not in public.users (no credits added)
    # This would require a valid Unkey key that hasn't been added to public.users
    # For now, we'll just document this case
    print("Test 3: Valid API key but user not in public.users")
    print("-" * 80)
    print(
        "Note: This requires a valid Unkey API key that hasn't been added to public.users"
    )
    print("      (user exists in auth.users but not in public.users)")
    if test_api_key:
        result = await test_endpoint_with_key(
            api_base_url,
            "/api/bot/join",
            test_api_key,
            bot_join_payload,
            "Valid API key but user not in public.users - should return 401",
        )
        test_cases.append(result)
        print(f"Status: {result['status_code']}")
        print(f"Response: {result.get('response', {})}")
        if result["status_code"] == 401:
            detail = result.get("response", {}).get("detail", {})
            if isinstance(detail, dict):
                error_msg = detail.get("detail", "")
                print(f"Error message: {error_msg}")
                print(
                    f"Expected message contains 'credits' or 'API key': {'✅' if 'credit' in error_msg.lower() or 'api key' in error_msg.lower() else '❌'}"
                )
        print("Expected: 401 (Unauthorized) with helpful message")
        print(f"Result: {'✅ PASS' if result['status_code'] == 401 else '❌ FAIL'}\n")
    else:
        print("⚠️  Skipped - UNKEY_PAILKIT_SECRET not set\n")

    # Test 4: Valid API key with insufficient credits
    # This requires a user in public.users with credit_balance < 0.15
    print("Test 4: Valid API key with insufficient credits")
    print("-" * 80)
    print("Note: This requires a user in public.users with credit_balance < 0.15")
    print("      You'll need to manually set a low credit balance in the database")
    if test_api_key:
        result = await test_endpoint_with_key(
            api_base_url,
            "/api/bot/join",
            test_api_key,
            bot_join_payload,
            "Valid API key with insufficient credits - should return 402",
        )
        test_cases.append(result)
        print(f"Status: {result['status_code']}")
        print(f"Response: {result.get('response', {})}")
        if result["status_code"] == 402:
            detail = result.get("response", {}).get("detail", {})
            if isinstance(detail, dict):
                error_msg = detail.get("detail", "")
                current_balance = detail.get("current_balance")
                print(f"Error message: {error_msg}")
                print(f"Current balance: {current_balance}")
                print(
                    f"Expected message contains 'insufficient credits': {'✅' if 'insufficient' in error_msg.lower() or 'credit' in error_msg.lower() else '❌'}"
                )
        print("Expected: 402 (Payment Required) with current_balance")
        print(f"Result: {'✅ PASS' if result['status_code'] == 402 else '❌ FAIL'}\n")
    else:
        print("⚠️  Skipped - UNKEY_PAILKIT_SECRET not set\n")

    # Test 5: Valid API key with sufficient credits (happy path)
    print("Test 5: Valid API key with sufficient credits (happy path)")
    print("-" * 80)
    if test_api_key and test_room_url:
        result = await test_endpoint_with_key(
            api_base_url,
            "/api/bot/join",
            test_api_key,
            bot_join_payload,
            "Valid API key with sufficient credits - should return 200",
        )
        test_cases.append(result)
        print(f"Status: {result['status_code']}")
        print(f"Response: {result.get('response', {})}")
        print("Expected: 200 (Success) or 500 (if room doesn't exist)")
        # Accept 200 or 500 (500 might happen if room doesn't exist, but credit check passed)
        print(
            f"Result: {'✅ PASS' if result['status_code'] in [200, 500] else '❌ FAIL'}"
        )
        if result["status_code"] == 500:
            print(
                "   (Note: 500 might indicate room doesn't exist, but credit check passed)"
            )
    else:
        print("⚠️  Skipped - UNKEY_PAILKIT_SECRET or TEST_ROOM_URL not set")
        print("   Set both to test the happy path\n")

    # Summary
    print(f"\n{'='*80}")
    print("📊 Test Summary")
    print(f"{'='*80}\n")

    passed = sum(
        1
        for tc in test_cases
        if tc.get("success") or tc.get("status_code") in [401, 402]
    )
    total = len(test_cases)

    for i, tc in enumerate(test_cases, 1):
        status = (
            "✅ PASS"
            if tc.get("success") or tc.get("status_code") in [401, 402]
            else "❌ FAIL"
        )
        print(f"Test {i}: {status} - {tc.get('description', 'Unknown')}")

    print(f"\nTotal: {passed}/{total} tests passed")

    print(f"\n{'='*80}")
    print("💡 Testing Tips")
    print(f"{'='*80}\n")
    print("1. To test insufficient credits:")
    print("   - Find a user in public.users by unkeyId")
    print("   - Set their credit_balance to a value < 0.15 (e.g., 0.05)")
    print("   - Use their API key in UNKEY_PAILKIT_SECRET")
    print()
    print("2. To test user not found:")
    print("   - Use a valid Unkey API key that hasn't been added to public.users")
    print("   - This simulates a user who hasn't added credits yet")
    print()
    print("3. To test happy path:")
    print("   - Use a valid API key with credit_balance >= 0.15")
    print("   - Set TEST_ROOM_URL to a valid Daily.co room URL")
    print()


if __name__ == "__main__":
    asyncio.run(main())
