# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Test script for Modal bot integration - can be run locally.

This script tests various aspects of the Modal integration that can be
validated without full deployment.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def test_imports():
    """Test that all imports work correctly."""
    logger.info("🧪 Testing imports...")
    try:
        # Test Modal import
        import modal

        logger.info("✅ Modal package imported successfully (v%s)", modal.__version__)

        # Test Modal app import
        from flow.modal_bot_runner import app

        logger.info("✅ Modal app imported successfully")
        logger.info(f"   App name: {app.app_id}")

        # Test ModalBotSpawner import
        from flow.steps.agent_call.bot.bot_service import ModalBotSpawner

        logger.info("✅ ModalBotSpawner imported successfully: %s", ModalBotSpawner)

        return True
    except ImportError as e:
        logger.error(f"❌ Import failed: {e}")
        logger.info("   💡 Install Modal with: pip install modal>=0.60")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}", exc_info=True)
        return False


def test_modal_spawner_init():
    """Test that ModalBotSpawner can be initialized."""
    logger.info("🧪 Testing ModalBotSpawner initialization...")
    try:
        from flow.steps.agent_call.bot.bot_service import ModalBotSpawner

        spawner = ModalBotSpawner()
        logger.info(
            "✅ ModalBotSpawner initialized successfully (%s)",
            type(spawner).__name__,
        )
        return True
    except RuntimeError as e:
        if "Modal is not installed" in str(e):
            logger.warning(f"⚠️ {e}")
            logger.info("   💡 Install Modal with: pip install modal>=0.60")
            return False
        raise
    except Exception as e:
        logger.error(f"❌ Initialization failed: {e}", exc_info=True)
        return False


def test_modal_app_structure():
    """Test that Modal app has the expected structure."""
    logger.info("🧪 Testing Modal app structure...")
    try:
        from flow.modal_bot_runner import app

        # Check that app exists
        assert app is not None, "App should not be None"
        logger.info(f"✅ App exists: {app.app_id}")

        # Check that run_bot function exists
        if hasattr(app, "run_bot"):
            logger.info("✅ run_bot function found on app")
        else:
            logger.warning("⚠️ run_bot function not found on app (may need deployment)")

        return True
    except Exception as e:
        logger.error(f"❌ App structure test failed: {e}", exc_info=True)
        return False


def test_bot_service_modal_config():
    """Test that BotService correctly detects Modal configuration."""
    logger.info("🧪 Testing BotService Modal configuration...")
    try:
        # Set environment variable
        os.environ["USE_MODAL_BOTS"] = "true"

        from flow.steps.agent_call.bot.bot_service import BotService

        service = BotService()

        if service.use_modal_bots:
            logger.info("✅ BotService correctly detected USE_MODAL_BOTS=true")
            if service.modal_spawner:
                logger.info("✅ Modal spawner initialized")
            else:
                logger.warning(
                    "⚠️ Modal spawner not initialized (Modal may not be installed)"
                )
        else:
            logger.error("❌ BotService did not detect USE_MODAL_BOTS=true")
            return False

        # Clean up
        del os.environ["USE_MODAL_BOTS"]

        return True
    except Exception as e:
        logger.error(f"❌ BotService test failed: {e}", exc_info=True)
        # Clean up on error
        if "USE_MODAL_BOTS" in os.environ:
            del os.environ["USE_MODAL_BOTS"]
        return False


def test_modal_cli_available():
    """Test that Modal CLI commands are available (if Modal is installed)."""
    logger.info("🧪 Testing Modal CLI availability...")
    try:
        import subprocess

        result = subprocess.run(
            ["modal", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            logger.info(f"✅ Modal CLI available: {result.stdout.strip()}")
            return True
        else:
            logger.warning("⚠️ Modal CLI not found in PATH")
            logger.info("   💡 Install Modal with: pip install modal>=0.60")
            return False
    except FileNotFoundError:
        logger.warning("⚠️ Modal CLI not found in PATH")
        logger.info("   💡 Install Modal with: pip install modal>=0.60")
        return False
    except Exception as e:
        logger.warning(f"⚠️ Could not check Modal CLI: {e}")
        return False


async def test_modal_spawner_spawn():
    """Test ModalBotSpawner.spawn() method (requires deployed app)."""
    logger.info("🧪 Testing ModalBotSpawner.spawn()...")
    logger.info("   ⚠️ This test requires the Modal app to be deployed")
    logger.info("   💡 Deploy with: modal deploy flow/modal_bot_runner.py")

    try:
        from flow.steps.agent_call.bot.bot_service import ModalBotSpawner

        spawner = ModalBotSpawner()
        logger.info("✅ Modal spawner created: %s", type(spawner).__name__)

        # Try to import app (will fail if not deployed)
        from flow.modal_bot_runner import app

        # Check if app is deployed by trying to access it
        if hasattr(app, "run_bot"):
            logger.info("✅ Modal app appears to be accessible")
            logger.info("   ⚠️ Full spawn test requires actual deployment and secrets")
            return True
        else:
            logger.warning("⚠️ Modal app not accessible - needs deployment")
            return False

    except Exception as e:
        logger.warning(f"⚠️ Spawn test skipped: {e}")
        logger.info("   💡 This is expected if Modal app is not deployed")
        return False


def main():
    """Run all local tests."""
    logger.info("=" * 60)
    logger.info("Modal Integration Local Tests")
    logger.info("=" * 60)
    logger.info("")
    logger.info("These tests validate the Modal integration code structure")
    logger.info("and configuration. Full integration testing requires:")
    logger.info("  1. Modal CLI installed: pip install modal>=0.60")
    logger.info("  2. Modal authentication: modal token new")
    logger.info(
        "  3. Modal secrets configured: modal secret create pailkit-secrets ..."
    )
    logger.info("  4. Modal app deployed: modal deploy flow/modal_bot_runner.py")
    logger.info("")

    results = []

    # Test 1: Imports
    results.append(("Imports", test_imports()))
    logger.info("")

    # Test 2: ModalBotSpawner initialization
    results.append(("ModalBotSpawner Init", test_modal_spawner_init()))
    logger.info("")

    # Test 3: Modal app structure
    results.append(("Modal App Structure", test_modal_app_structure()))
    logger.info("")

    # Test 4: BotService configuration
    results.append(("BotService Config", test_bot_service_modal_config()))
    logger.info("")

    # Test 5: Modal CLI
    results.append(("Modal CLI", test_modal_cli_available()))
    logger.info("")

    # Test 6: Spawn method (async)
    results.append(("Spawn Method", asyncio.run(test_modal_spawner_spawn())))
    logger.info("")

    # Summary
    logger.info("=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"  {status}: {name}")

    logger.info("")
    logger.info(f"Results: {passed}/{total} tests passed")

    if passed == total:
        logger.info("✅ All local tests passed!")
    else:
        logger.info("⚠️ Some tests failed - check output above for details")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
