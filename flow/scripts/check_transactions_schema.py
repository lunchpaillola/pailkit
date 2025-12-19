#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0
"""
Check transactions table schema in Supabase database.
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flow.db import get_supabase_client


def check_transactions_schema():
    """Check if transactions table exists and get its structure."""
    client = get_supabase_client()
    if not client:
        print("❌ Cannot connect to Supabase")
        return

    try:
        # Try to query the transactions table
        result = client.table("transactions").select("*").limit(1).execute()
        print("✅ transactions table exists")

        if result.data:
            print("\nSample record columns:")
            for key in result.data[0].keys():
                value = result.data[0][key]
                value_type = type(value).__name__
                print(f"  - {key}: {value_type}")
        else:
            print("  (table is empty)")

    except Exception as e:
        print(f"❌ transactions table may not exist: {e}")
        print("\nChecking users table structure for reference...")
        try:
            user_result = client.table("users").select("*").limit(1).execute()
            if user_result.data:
                print("\nUsers table columns:")
                for key in user_result.data[0].keys():
                    print(f"  - {key}")
        except Exception as e2:
            print(f"Error checking users: {e2}")


if __name__ == "__main__":
    check_transactions_schema()
