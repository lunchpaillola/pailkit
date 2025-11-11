# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""Workflow definitions."""

from typing import Any, Protocol

from experiments.flow.workflows.order_food import OrderFoodWorkflow


class Workflow(Protocol):
    """Base workflow interface."""

    name: str
    description: str

    def execute(
        self, message: str, user_id: str | None = None, channel_id: str | None = None
    ) -> dict[str, Any]:
        """Execute the workflow with the provided context."""
        ...


class WorkflowNotFoundError(Exception):
    """Exception raised when a requested workflow is not found."""

    pass


def get_workflows() -> dict[str, Workflow]:
    """Return all available workflows."""
    return {
        "order_food": OrderFoodWorkflow(),
    }


def get_workflow(name: str) -> Workflow:
    """
    Get a workflow by name.

    Raises:
        WorkflowNotFoundError: If the workflow doesn't exist.
    """
    workflows = get_workflows()

    if name not in workflows:
        raise WorkflowNotFoundError(f"Workflow '{name}' not found")

    return workflows[name]


__all__ = [
    "Workflow",
    "OrderFoodWorkflow",
    "get_workflows",
    "get_workflow",
    "WorkflowNotFoundError",
]
