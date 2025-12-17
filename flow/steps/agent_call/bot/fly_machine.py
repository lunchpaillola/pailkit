# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""Fly.io machine spawning for bot execution."""

import json
import logging
import os
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)


class FlyMachineSpawner:
    """
    Handles spawning Fly.io machines to run bots.

    Simple Explanation: This class manages the creation of Fly.io machines
    that run bot instances. Each machine runs independently and auto-destroys
    when the bot finishes.
    """

    def __init__(
        self,
        fly_api_host: str,
        fly_app_name: str,
        fly_api_key: str,
    ):
        """
        Initialize the Fly.io machine spawner.

        Args:
            fly_api_host: Fly.io API host URL
            fly_app_name: Fly.io app name
            fly_api_key: Fly.io API key for authentication
        """
        self.fly_api_host = fly_api_host
        self.fly_app_name = fly_app_name
        self.fly_api_key = fly_api_key

    def spawn(
        self,
        room_url: str,
        token: str,
        bot_config: Dict[str, Any],
        workflow_thread_id: str = None,
    ) -> str:
        """
        Spawn a new Fly.io machine to run the bot.

        Args:
            room_url: Full Daily.co room URL
            token: Meeting token for authentication
            bot_config: Bot configuration dictionary
            workflow_thread_id: Optional workflow thread ID to associate with this bot session

        Returns:
            Machine ID of the spawned machine

        Raises:
            Exception: If machine spawning fails
        """
        if not self.fly_api_key or not self.fly_app_name:
            raise RuntimeError(
                "Fly.io machine spawning is not enabled. "
                "Set FLY_API_KEY and FLY_APP_NAME environment variables."
            )

        headers = {
            "Authorization": f"Bearer {self.fly_api_key}",
            "Content-Type": "application/json",
        }

        # Get the Docker image from the current app
        res = requests.get(
            f"{self.fly_api_host}/apps/{self.fly_app_name}/machines",
            headers=headers,
        )
        if res.status_code != 200:
            raise Exception(f"Unable to get machine info from Fly: {res.text}")

        machines = res.json()
        if not machines:
            raise Exception("No machines found in Fly app to get image from")

        image = machines[0]["config"]["image"]
        logger.info(f"Using Docker image: {image}")

        # Prepare bot config as JSON for the command
        bot_config_json = json.dumps(bot_config)

        # Machine configuration
        cmd = [
            "python3",
            "flow/steps/agent_call/bot/bot_executor.py",
            "-u",
            room_url,
            "-t",
            token or "",  # Use empty string if token is None
            "--bot-config",
            bot_config_json,
        ]
        # Add workflow_thread_id if provided
        if workflow_thread_id:
            cmd.extend(["--workflow-thread-id", workflow_thread_id])

        worker_props = {
            "config": {
                "image": image,
                "auto_destroy": True,  # Machine destroys itself when bot exits
                "init": {"cmd": cmd},
                "restart": {"policy": "no"},  # Don't restart - let it exit cleanly
                "guest": {
                    "cpu_kind": "shared",
                    "cpus": 1,
                    "memory_mb": 1024,  # 1GB RAM - enough for VAD and bot processing
                },
                "env": {
                    # Set PYTHONPATH so Python can find the flow module
                    "PYTHONPATH": "/app",
                    # Pass through required environment variables for bot execution
                    "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
                    "DEEPGRAM_API_KEY": os.getenv("DEEPGRAM_API_KEY", ""),
                    # Supabase credentials for saving workflow thread data and LangGraph checkpoints
                    # Support both SUPABASE_SERVICE_ROLE_KEY and SUPABASE_SECRET_KEY (modern naming)
                    "SUPABASE_URL": os.getenv("SUPABASE_URL", ""),
                    "SUPABASE_SERVICE_ROLE_KEY": os.getenv(
                        "SUPABASE_SERVICE_ROLE_KEY", ""
                    ),
                    "SUPABASE_SECRET_KEY": os.getenv("SUPABASE_SECRET_KEY", ""),
                    "SUPABASE_DB_PASSWORD": os.getenv("SUPABASE_DB_PASSWORD", ""),
                    # Note: DAILY_API_KEY is not needed - bot only joins rooms via WebSocket
                    # (room URL and optional token are passed as command args, not env vars)
                },
            },
        }

        # Spawn a new machine instance
        logger.info(
            f"Spawning Fly.io machine for bot (room: {room_url.split('/')[-1]})"
        )
        res = requests.post(
            f"{self.fly_api_host}/apps/{self.fly_app_name}/machines",
            headers=headers,
            json=worker_props,
        )

        if res.status_code != 200:
            raise Exception(f"Problem starting a bot worker: {res.text}")

        # Get the machine ID from the response
        vm_id = res.json()["id"]
        logger.info(f"✅ Machine spawned: {vm_id}")

        # Wait for the machine to enter the started state
        res = requests.get(
            f"{self.fly_api_host}/apps/{self.fly_app_name}/machines/{vm_id}/wait?state=started",
            headers=headers,
        )

        if res.status_code != 200:
            raise Exception(f"Bot was unable to enter started state: {res.text}")

        logger.info(f"✅ Machine {vm_id} is started and ready")
        return vm_id
