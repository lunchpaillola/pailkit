# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Daily.co utility functions for interview workflow steps.

Shared utilities for interacting with Daily.co's API, including authentication
and room name extraction.
"""

from typing import Dict
from urllib.parse import urlparse


def extract_room_name(room_url: str) -> str:
    """
    Extract room name from Daily.co room URL.

    Daily.co room URLs have the format: https://domain.daily.co/{room_name}

    Args:
        room_url: Daily.co room URL (e.g., "https://domain.daily.co/abc123")

    Returns:
        Room name extracted from URL

    Raises:
        ValueError: If URL is invalid or not a Daily.co URL
    """
    if not room_url:
        raise ValueError("room_url is required")

    parsed = urlparse(room_url)
    path = parsed.path.strip("/")
    if not path:
        raise ValueError(
            f"Invalid Daily.co room URL: {room_url}. "
            "Expected format: https://domain.daily.co/{room_name}"
        )

    return path


def get_daily_headers(api_key: str) -> Dict[str, str]:
    """
    Get HTTP headers for Daily.co API requests.

    Args:
        api_key: Daily.co API key (can be just the token or "Bearer <token>" format)

    Returns:
        Dictionary with HTTP headers including Authorization
    """
    auth_header = api_key.strip()
    if not auth_header.startswith("Bearer "):
        auth_header = f"Bearer {auth_header}"

    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": auth_header,
    }
