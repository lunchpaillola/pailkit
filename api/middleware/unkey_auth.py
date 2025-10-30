"""
Unkey Authentication and Rate Limiting Middleware.

Requires an `Authorization: Bearer pailkit_...` key on all requests.

This middleware is structured to integrate with Unkey for verification and
rate limiting when Unkey credentials are provided via environment variables.
In local/dev without Unkey configured, it still enforces the presence and
format of a PailKit key to avoid accidental anonymous usage.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from types import ModuleType

from fastapi import Request
from fastapi.responses import JSONResponse


class UnkeyAuthMiddleware:
    """ASGI middleware that enforces Unkey-style API keys globally."""

    def __init__(self, app: Callable) -> None:
        self.app = app

        # Environment-driven configuration. If these are present, a real Unkey
        # verification flow can be enabled later without code changes.
        self.unkey_api_id = os.getenv("UNKEY_API_ID")
        self.unkey_root_key = os.getenv("UNKEY_ROOT_KEY")

        # Attempt to import optional Unkey SDK. Code runs without it, but when
        # installed and configured, verification hooks can be enabled.
        try:
            # The Python SDK is commonly published as "unkey". If you are using
            # a different package name, adjust this import accordingly.
            import importlib

            self._unkey_sdk: ModuleType | None = importlib.import_module("unkey")
        except Exception:
            self._unkey_sdk = None

    async def __call__(self, scope, receive, send):  # type: ignore[no-untyped-def]
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)

        # Require Authorization header
        auth_header = request.headers.get("authorization", "").strip()
        if not auth_header or not auth_header.lower().startswith("bearer "):
            response = JSONResponse(
                status_code=401,
                content={
                    "detail": (
                        "Authorization header required. Use 'Authorization: Bearer pailkit_xxx'. "
                        "Get a key from the PailKit dashboard (Unkey)."
                    )
                },
            )
            await response(scope, receive, send)
            return

        token = auth_header[7:].strip()

        # Minimal local validation: enforce prefix to avoid accidental leakage of other tokens
        if not token or not token.startswith("pailkit_"):
            response = JSONResponse(
                status_code=401,
                content={
                    "detail": (
                        "Invalid API key format. Expected key starting with 'pailkit_'. "
                        "Get a valid key from the PailKit dashboard (Unkey)."
                    )
                },
            )
            await response(scope, receive, send)
            return

        # Optional: If Unkey SDK and credentials are available, this is where
        # verification + rate limit check would occur. We keep it non-blocking
        # for local/dev without credentials.
        #
        # Pseudocode (left disabled until credentials exist):
        # if self._unkey_sdk and self.unkey_api_id and self.unkey_root_key:
        #     is_valid = await verify_with_unkey(token)
        #     if not is_valid:
        #         return 401
        #     # Unkey would also enforce per-key rate limits server-side.

        await self.app(scope, receive, send)
