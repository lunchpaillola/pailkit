#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0
"""
Test script to verify Supabase PostgreSQL connection.

This script tests the database connection using the credentials from .env
"""

import os
import sys
from pathlib import Path
from urllib.parse import quote_plus

# Add flow directory to path
flow_dir = Path(__file__).parent.parent
sys.path.insert(0, str(flow_dir))

from dotenv import load_dotenv  # noqa: E402

env_path = flow_dir / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ Loaded .env from: {env_path}\n")
else:
    print(f"❌ No .env file found at: {env_path}")
    sys.exit(1)

db_url = os.getenv("SUPABASE_DB_URL")
db_password = os.getenv("SUPABASE_DB_PASSWORD")

print("=" * 70)
print("TESTING SUPABASE POSTGRESQL CONNECTION")
print("=" * 70)
print()

if not db_url:
    print("❌ SUPABASE_DB_URL is not set")
    sys.exit(1)

print(
    f"Connection string: {db_url.split('@')[0]}@***MASKED***@{db_url.split('@')[1] if '@' in db_url else 'N/A'}"
)
print()

# Test 1: Try direct connection with psycopg
print("Test 1: Direct connection with psycopg...")
try:
    import psycopg
    from psycopg.conninfo import conninfo_to_dict

    # Parse connection string
    conn_params = conninfo_to_dict(db_url)

    # Mask password in output
    conn_params_display = conn_params.copy()
    if "password" in conn_params_display:
        conn_params_display["password"] = "***MASKED***"
    print(f"   Connection parameters: {conn_params_display}")

    # Try to connect
    conn = psycopg.connect(db_url)
    print("   ✅ Connection successful!")
    conn.close()

except ImportError:
    print("   ⚠️  psycopg not installed (this is okay, we'll test with async)")
except Exception as e:
    print(f"   ❌ Connection failed: {e}")
    print()
    print("   💡 TIP: Check that:")
    print(
        "      - The password is correct (get it from Supabase Dashboard > Settings > Database)"
    )
    print("      - The database password hasn't been reset recently")
    print("      - You're using the 'Database password' (not the API key)")

print()

# Test 2: Try async connection with psycopg
print("Test 2: Async connection with psycopg (what LangGraph uses)...")
try:
    import asyncio
    from psycopg_pool import AsyncConnectionPool

    async def test_async_connection():
        try:
            # Try to create a connection pool (similar to what AsyncPostgresSaver does)
            async with AsyncConnectionPool(db_url, min_size=1, max_size=1) as pool:
                async with pool.connection() as conn:
                    # Test a simple query
                    async with conn.cursor() as cur:
                        await cur.execute("SELECT version();")
                        version = await cur.fetchone()
                        print("   ✅ Async connection successful!")
                        print(f"   PostgreSQL version: {version[0][:50]}...")
                        return True
        except Exception as e:
            print(f"   ❌ Async connection failed: {e}")
            return False

    result = asyncio.run(test_async_connection())

except ImportError:
    print("   ⚠️  psycopg async libraries not installed")
    print("   Install with: pip install psycopg[binary,pool]")
except Exception as e:
    print(f"   ❌ Test failed: {e}")

print()

# Test 3: Try with URL-encoded password
print("Test 3: Testing with URL-encoded password...")
if db_password:
    try:
        encoded_password = quote_plus(db_password)
        if encoded_password != db_password:
            # Replace password in connection string
            parts = db_url.split("@")
            if len(parts) == 2:
                user_pass = parts[0].split("://")[1]
                user = user_pass.split(":")[0]
                encoded_url = db_url.replace(
                    f"{user}:{db_password}", f"{user}:{encoded_password}"
                )
                print(f"   Original password: {db_password}")
                print(f"   URL-encoded password: {encoded_password}")
                print(
                    f"   Would try: {encoded_url.split('@')[0]}@***MASKED***@{encoded_url.split('@')[1]}"
                )

                # Try connection with encoded password
                import asyncio
                from psycopg_pool import AsyncConnectionPool

                async def test_encoded():
                    try:
                        async with AsyncConnectionPool(
                            encoded_url, min_size=1, max_size=1
                        ) as pool:
                            async with pool.connection() as _:
                                print(
                                    "   ✅ Connection with URL-encoded password successful!"
                                )
                                return True
                    except Exception as e:
                        print(f"   ❌ Connection with URL-encoded password failed: {e}")
                        return False

                asyncio.run(test_encoded())
            else:
                print("   ⚠️  Could not parse connection string for encoding test")
        else:
            print("   ℹ️  Password doesn't need URL encoding")
    except Exception as e:
        print(f"   ⚠️  Encoding test failed: {e}")

print()
print("=" * 70)
print("TROUBLESHOOTING")
print("=" * 70)
print()
print("If connection is failing, try:")
print("1. Verify the password in Supabase Dashboard:")
print("   - Go to: https://supabase.com/dashboard")
print("   - Select your project")
print("   - Go to: Settings > Database")
print("   - Look for 'Database password' (NOT the API keys)")
print()
print("2. If the password is wrong or you're not sure:")
print("   - Go to: Settings > Database > Reset database password")
print("   - Copy the new password")
print("   - Update SUPABASE_DB_PASSWORD in your .env file")
print()
print("3. Make sure you're using the correct connection string format:")
print(
    "   SUPABASE_DB_URL=postgresql://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres"
)
print()
print("4. For Supabase cloud, SSL is required (enabled by default)")
print("   If you need to disable SSL (not recommended), add: ?sslmode=disable")
print()
