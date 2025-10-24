"""
PailKit API - Main FastAPI Application

This is the main entry point for the PailKit API server.
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from routers.rooms import router as rooms_router

# Load environment variables
load_dotenv()

# Create FastAPI application
app = FastAPI(
    title="PailKit API",
    description="Tools for builders. Built by Lunch Pail Labs.",
    version="0.1.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(rooms_router, prefix="/api/rooms", tags=["Rooms"])


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "PailKit API",
        "version": "0.1.0",
        "status": "active",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "api"
    }


if __name__ == "__main__":
    import uvicorn
    
    # Get port from environment or default to 8000
    port = int(os.getenv("PORT", 8000))
    
    # Run the server
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,  
        log_level="info"
    )
