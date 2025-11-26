# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Base step class for interview workflow steps.

This provides a common interface and shared functionality for all interview steps.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict

logger = logging.getLogger(__name__)


class InterviewStep(ABC):
    """
    Base class for all interview workflow steps.

    **Simple Explanation:**
    This is like a template that all interview steps follow. It ensures
    every step has the same structure and can be used in the workflow.

    Each step:
    - Takes the current state (all the data from previous steps)
    - Does its specific job
    - Returns the updated state
    - Handles errors gracefully
    """

    def __init__(self, name: str, description: str):
        """
        Initialize the step.

        Args:
            name: Unique name for this step (e.g., "create_room")
            description: Human-readable description of what this step does
        """
        self.name = name
        self.description = description

    @abstractmethod
    async def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the step.

        **Simple Explanation:**
        This is the main method that does the work. Each step must implement
        this method to define what it does.

        Args:
            state: Current workflow state dictionary

        Returns:
            Updated state dictionary

        Raises:
            Exception: If the step fails and cannot continue
        """
        pass

    def validate_state(self, state: Dict[str, Any], required_keys: list[str]) -> bool:
        """
        Validate that required state keys are present.

        **Simple Explanation:**
        This checks if the state has all the data this step needs before
        trying to run. It's like checking you have all ingredients before
        starting to cook.

        Args:
            state: Current workflow state
            required_keys: List of keys that must be present in state

        Returns:
            True if all required keys are present, False otherwise
        """
        missing_keys = [
            key for key in required_keys if key not in state or state[key] is None
        ]

        if missing_keys:
            logger.warning(
                f"Step {self.name} missing required state keys: {missing_keys}"
            )
            return False

        return True

    def update_status(self, state: Dict[str, Any], status: str) -> Dict[str, Any]:
        """
        Update the processing status in state.

        **Simple Explanation:**
        This updates the status field so we can track which step is currently
        running or if there's an error.

        Args:
            state: Current workflow state
            status: New status string (e.g., "room_created", "error")

        Returns:
            Updated state dictionary
        """
        state["processing_status"] = status
        return state

    def set_error(self, state: Dict[str, Any], error_message: str) -> Dict[str, Any]:
        """
        Set an error in the state.

        **Simple Explanation:**
        If something goes wrong, this method records the error so the workflow
        knows what happened and can stop gracefully.

        Args:
            state: Current workflow state
            error_message: Description of what went wrong

        Returns:
            Updated state dictionary with error set
        """
        state["error"] = error_message
        state["processing_status"] = "error"
        logger.error(f"Step {self.name} error: {error_message}")
        return state
