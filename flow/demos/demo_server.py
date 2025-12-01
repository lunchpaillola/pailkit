#!/usr/bin/env python3
# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Standalone demo server for showcasing lead qualification flow.

This is a separate server that you can run when you want to show demos.
It's not part of the main production infrastructure.

Run with: python flow/demos/demo_server.py
"""

import logging
import os
import sys
from pathlib import Path
from typing import Union

# Add project root to path so we can import flow modules
script_dir = Path(__file__).parent
demo_dir = script_dir  # flow/demos/
flow_dir = demo_dir.parent  # flow/
project_root = flow_dir.parent  # project root (pailkit/)
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from dotenv import load_dotenv  # noqa: E402
from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import HTMLResponse, Response  # noqa: E402

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="PailFlow Demo Server",
    description="Demo server for showcasing lead qualification flow",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/demo", response_model=None)
async def demo_page(start: bool = Query(False)) -> Union[Response, HTMLResponse]:
    """
    Serve the lead qualification demo page or execute the script.

    - GET /demo - serves the HTML page
    - GET /demo?start=true - executes the script and redirects to the meeting
    """
    # If start=true, execute the script and redirect
    if start:
        try:
            from flow.demos.create_lead_qualification_room import (
                create_lead_qualification_room,
            )

            # Run the script function
            result = await create_lead_qualification_room()

            # Get the hosted URL to redirect to
            hosted_url = result.get("hosted_url")
            room_name = result.get("room_name")

            if hosted_url:
                return Response(status_code=302, headers={"Location": hosted_url})
            elif room_name:
                # Fallback to meeting page
                meet_base_url = os.getenv("MEET_BASE_URL", "http://localhost:8001")
                redirect_url = f"{meet_base_url}/meet/{room_name}"
                return Response(status_code=302, headers={"Location": redirect_url})
            else:
                raise HTTPException(
                    status_code=500, detail="Room creation failed - no URL returned"
                )

        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(
                f"Error creating demo lead qualification room: {e}", exc_info=True
            )
            raise HTTPException(
                status_code=500, detail=f"Internal server error: {str(e)}"
            )

    # Otherwise, serve the HTML page
    try:
        # Get the hosting directory (go up from demos/ to flow/ then to hosting/)
        demo_dir = Path(__file__).parent
        flow_dir = demo_dir.parent
        hosting_dir = flow_dir / "hosting"
        html_file = hosting_dir / "demo.html"

        if not html_file.exists():
            logger.error(f"Demo page template not found: {html_file}")
            raise HTTPException(status_code=500, detail="Demo page template not found")

        with open(html_file, "r", encoding="utf-8") as f:
            html_content = f.read()

        return HTMLResponse(content=html_content)

    except Exception as e:
        logger.error(f"Error serving demo page: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to serve demo page: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("DEMO_PORT", 8002))
    logger.info(f"🚀 Starting demo server on port {port}")
    logger.info(f"📱 Demo page available at: http://localhost:{port}/demo")

    uvicorn.run(
        "demo_server:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )
