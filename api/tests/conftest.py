# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Centralized test configuration for pytest.

This file is automatically loaded by pytest and provides:
- Environment variable loading via dotenv
- Shared test fixtures and constants
"""

import os

from dotenv import load_dotenv

# Load environment variables once for all tests
load_dotenv()

# Set AUTH_KEY as a pytest fixture if needed
AUTH_KEY = os.getenv("UNKEY_PAILKIT_SECRET", "pailkit_test_123")
