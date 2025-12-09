# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""Bot process representation for lifecycle management."""

import asyncio
import uuid
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from pipecat.transports.daily.transport import DailyTransport


class BotProcess:
    """Represents a single bot process with proper lifecycle management."""

    def __init__(
        self,
        room_name: str,
        task: asyncio.Task,
        transport: Optional["DailyTransport"] = None,
    ):
        self.room_name = room_name
        self.task = task
        self.transport = transport  # Store transport reference for cleanup
        self.process_id = str(uuid.uuid4())
        self.start_time = asyncio.get_event_loop().time()

    @property
    def is_running(self) -> bool:
        """Check if the bot task is still running."""
        return not self.task.done()

    @property
    def runtime_seconds(self) -> float:
        """Get how long the bot has been running."""
        return asyncio.get_event_loop().time() - self.start_time
