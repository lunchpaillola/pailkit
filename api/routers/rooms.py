"""
Rooms Router - PailKit API

Handles room creation and management for video, audio, and live collaboration.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from providers.rooms.daily import DailyRooms

router = APIRouter()

# Initialize providers
daily_provider = DailyRooms(api_key="your-daily-api-key")  # TODO: Get from env


@router.post("/create")
async def create_room(room_data: Dict[str, Any]):
    """
    Create a new room for video, audio, or live collaboration.
    
    This is the first building block of PailKit - a single API call
    to spin up a new video or audio room.
    """
    try:
        # Extract parameters
        name = room_data.get("name", "Untitled Room")
        room_type = room_data.get("room_type", "video")
        privacy = room_data.get("privacy", "public")
        
        # Route to appropriate provider
        provider = room_data.get("provider", "daily")
        if provider == "daily":
            result = await daily_provider.create_room(name, room_type, privacy)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create room: {str(e)}")


@router.get("/{room_id}")
async def get_room(room_id: str, provider: str = "daily"):
    """Get room details by ID."""
    try:
        if provider == "daily":
            result = await daily_provider.get_room(room_id)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
        
        if not result["success"]:
            raise HTTPException(status_code=404, detail=result["message"])
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get room: {str(e)}")


@router.delete("/{room_id}")
async def delete_room(room_id: str, provider: str = "daily"):
    """Delete a room by ID."""
    try:
        if provider == "daily":
            result = await daily_provider.delete_room(room_id)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["message"])
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete room: {str(e)}")
