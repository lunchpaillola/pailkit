# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
PailKit API - Main FastAPI Application

This is the main entry point for the PailKit API server.
"""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from shared.auth import UnkeyAuthMiddleware

# Add project root to Python path to allow imports from flow module
# Simple Explanation: This lets Python find the 'flow' module in the project root
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from api.routers.rooms import router as rooms_router  # noqa: E402
from api.routers.transcribe import router as transcribe_router  # noqa: E402

# Load environment variables
load_dotenv()

# Set up logging first (before Sentry, so Sentry can capture log messages)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize Sentry for error tracking and monitoring
# Simple Explanation:
# Sentry is a service that automatically captures errors and exceptions from your app
# and sends them to a dashboard where you can see what went wrong, when it happened,
# and get detailed information to help fix bugs.
#
# We initialize it here (before creating the FastAPI app) so it can catch all errors.
# The DSN (Data Source Name) is like an address that tells Sentry where to send error reports.
# If SENTRY_DSN is not set, Sentry won't do anything (useful for local development).
import sentry_sdk  # noqa: E402
from sentry_sdk.integrations.fastapi import FastApiIntegration  # noqa: E402
from sentry_sdk.integrations.logging import LoggingIntegration  # noqa: E402

sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    # Configure Sentry with your DSN
    # Simple Explanation:
    # - dsn: Your Sentry project's unique identifier (like an API key)
    # - environment: Helps you filter errors by environment (production, staging, etc.)
    # - release: Optional version identifier (like git commit hash) to track which
    #   code version had the error
    # - integrations: Automatically captures errors from FastAPI and Python logging
    # - traces_sample_rate: How often to track performance (1.0 = 100%, 0.1 = 10%)
    #   We set it to 0.1 (10%) to avoid sending too much data, but you can adjust this
    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
        release=os.getenv("SENTRY_RELEASE"),
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        # Performance monitoring: track 10% of requests to see slow endpoints
        # Simple Explanation: This helps you see which API endpoints are slow
        # Setting it to 0.1 means Sentry will track 1 out of every 10 requests
        # You can increase this if you want more data, or decrease to save on Sentry quota
        traces_sample_rate=0.1,
        # Send errors even in development (you can set this to False for local dev)
        # Simple Explanation: When True, Sentry will send errors even if you're running locally
        # When False, it only sends errors in production
        send_default_pii=False,  # Don't send personal info by default (privacy)
    )
    logger.info("✅ Sentry initialized for error tracking")
else:
    logger.info("ℹ️  Sentry not configured (SENTRY_DSN not set)")

# Create FastAPI application
app = FastAPI(
    title="PailKit API",
    description="Tools for builders. Built by Lunch Pail Labs.",
    version="0.1.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Require Unkey-style Authorization on all routes (including /health and /docs)
app.add_middleware(UnkeyAuthMiddleware)

# Include routers
app.include_router(rooms_router, prefix="/api/rooms", tags=["Rooms"])
app.include_router(transcribe_router, prefix="/api/transcribe", tags=["Transcription"])

# Include flow endpoints (workflows, webhooks, etc.)
# Simple Explanation: Flow is a separate module that provides workflow functionality.
# We import its FastAPI app and include all its routes into our main app.
# Flow routes: /api/flows/*, /workflows, /webhooks/*, /meet/*, /bots/*
# These won't conflict with /api/rooms/* and /api/transcribe/*
from flow.main import app as flow_app  # noqa: E402

# Include all flow routes into the main app
# Simple Explanation: We loop through all routes from flow_app and add them to our main app.
# FastAPI routes are matched in order, so api routes (defined above) take precedence.
for route in flow_app.routes:
    app.routes.append(route)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint with API information."""
    return {
        "message": "PailKit API",
        "version": "0.1.0",
        "status": "active",
        "docs": "/docs",
    }


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "api"}


if __name__ == "__main__":
    import uvicorn

    # Get port from environment or default to 8000
    port = int(os.getenv("PORT", 8000))

    # Run the server
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True, log_level="info")
