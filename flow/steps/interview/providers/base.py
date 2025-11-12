# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Base provider interfaces for interview workflow.

This module defines abstract base classes for different provider types,
allowing the workflow to work with multiple providers (VAPI, 11Labs, OpenAI, etc.)
through a unified interface.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class RoomProvider(ABC):
    """
    Abstract base class for room providers (e.g., Daily.co).

    **Simple Explanation:**
    This defines what any video room provider must be able to do.
    Different providers (Daily.co, Zoom, etc.) can implement this interface
    so the workflow works with any of them.
    """

    @abstractmethod
    async def create_room(
        self,
        room_name: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a video room.

        Args:
            room_name: Name for the room
            config: Optional room configuration

        Returns:
            Dictionary with room_id and room_url
        """
        pass

    @abstractmethod
    async def delete_room(self, room_id: str) -> bool:
        """
        Delete a room.

        Args:
            room_id: ID of the room to delete

        Returns:
            True if successful, False otherwise
        """
        pass


class TranscriptionProvider(ABC):
    """
    Abstract base class for transcription providers.

    **Simple Explanation:**
    This defines what any transcription provider must be able to do.
    Different providers (Daily.co, AssemblyAI, etc.) can implement this
    so the workflow works with any of them.
    """

    @abstractmethod
    async def start_transcription(
        self,
        room_id: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Start transcription for a room.

        Args:
            room_id: ID of the room to transcribe
            config: Optional transcription configuration

        Returns:
            Dictionary with transcription_id
        """
        pass

    @abstractmethod
    async def stop_transcription(self, transcription_id: str) -> Dict[str, Any]:
        """
        Stop transcription and get final transcript.

        Args:
            transcription_id: ID of the transcription to stop

        Returns:
            Dictionary with transcript text
        """
        pass


class VoiceProvider(ABC):
    """
    Abstract base class for voice/AI providers (e.g., VAPI, 11Labs, OpenAI).

    **Simple Explanation:**
    This defines what any voice/AI provider must be able to do.
    Different providers (VAPI, 11Labs, OpenAI Voice, etc.) can implement this
    so the workflow works with any of them.
    """

    @abstractmethod
    async def create_agent(
        self,
        persona: str,
        context: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create an AI agent with persona and context.

        Args:
            persona: Agent persona description
            context: Additional context for the agent
            config: Optional agent configuration

        Returns:
            Dictionary with agent_id
        """
        pass

    @abstractmethod
    async def start_conversation(
        self,
        agent_id: str,
        room_id: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Start a conversation with the agent in a room.

        Args:
            agent_id: ID of the agent to use
            room_id: ID of the room for the conversation
            config: Optional conversation configuration

        Returns:
            Dictionary with conversation_id
        """
        pass

    @abstractmethod
    async def end_conversation(self, conversation_id: str) -> Dict[str, Any]:
        """
        End a conversation and get final transcript.

        Args:
            conversation_id: ID of the conversation to end

        Returns:
            Dictionary with conversation results
        """
        pass
