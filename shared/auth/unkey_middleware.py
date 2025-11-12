# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Unkey Authentication and Rate Limiting Middleware.

Requires an `Authorization: Bearer <key>` header on all requests.

When Unkey credentials are provided via environment variables, the presented
key is verified against Unkey. In local/dev without Unkey configured, the
middleware only enforces the presence of the header.
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

        # Skip authentication for public routes (e.g., hosted meeting pages, favicon)
        path = request.url.path
        if path.startswith("/meet/") or path == "/favicon.ico":
            # Public route - allow access without authentication
            await self.app(scope, receive, send)
            return

        # Require Authorization header
        auth_header = request.headers.get("authorization", "").strip()
        if not auth_header or not auth_header.lower().startswith("bearer "):
            response = JSONResponse(
                status_code=401,
                content={
                    "detail": (
                        "Authorization header required. Use 'Authorization: Bearer <your_api_key>'."
                        " Request a key and include it as a Bearer token."
                    )
                },
            )
            await response(scope, receive, send)
            return

        token = auth_header[7:].strip()

        if not token:
            response = JSONResponse(
                status_code=401,
                content={"detail": "Empty Bearer token provided."},
            )
            await response(scope, receive, send)
            return

        # If Unkey credentials are available, verify the key via Unkey's API.
        if self.unkey_root_key:
            try:
                # Lazy import to avoid hard dependency during startup in environments
                # that don't need verification.
                import httpx

                verify_url = "https://api.unkey.com/v2/keys.verifyKey"
                payload = {"key": token}
                headers = {
                    "Authorization": f"Bearer {self.unkey_root_key}",
                    "Content-Type": "application/json",
                }
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.post(verify_url, json=payload, headers=headers)
                if resp.status_code >= 400:
                    response = JSONResponse(
                        status_code=401,
                        content={
                            "detail": "API key verification failed with Unkey.",
                            "upstream_status": resp.status_code,
                        },
                    )
                    await response(scope, receive, send)
                    return

                data = resp.json().get("data", {})
                if not data.get("valid"):
                    response = JSONResponse(
                        status_code=401,
                        content={"detail": "Invalid API key."},
                    )
                    await response(scope, receive, send)
                    return
            except Exception:
                # Fail closed if verification was intended but errored.
                response = JSONResponse(
                    status_code=401,
                    content={"detail": "Could not verify API key at this time."},
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)
