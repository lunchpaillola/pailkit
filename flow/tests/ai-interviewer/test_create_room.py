# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Comprehensive tests for CreateRoomStep.

Tests cover:
- Branding configuration validation
- Room overrides building
- Error handling scenarios
- Provider key validation
"""

import pytest
from unittest.mock import AsyncMock, patch

from flow.steps.interview.create_room import CreateRoomStep


class TestCreateRoomStepBrandingConfig:
    """Tests for _build_branding_config method."""

    def test_build_branding_config_empty(self):
        """Test that empty branding config returns empty dict."""
        step = CreateRoomStep()
        interview_config = {}
        result = step._build_branding_config(interview_config)
        assert result == {}

    def test_build_branding_config_no_branding(self):
        """Test that missing branding key returns empty dict."""
        step = CreateRoomStep()
        interview_config = {"other_key": "value"}
        result = step._build_branding_config(interview_config)
        assert result == {}

    def test_build_branding_config_valid_logo_url(self):
        """Test that valid logo URL is accepted."""
        step = CreateRoomStep()
        interview_config = {
            "branding": {
                "logo_url": "https://example.com/logo.png",
            }
        }
        result = step._build_branding_config(interview_config)
        assert result["logo_url"] == "https://example.com/logo.png"

    def test_build_branding_config_invalid_logo_url_no_scheme(self):
        """Test that logo URL without scheme is rejected."""
        step = CreateRoomStep()
        interview_config = {
            "branding": {
                "logo_url": "example.com/logo.png",
            }
        }
        with pytest.raises(ValueError, match="Invalid logo_url format"):
            step._build_branding_config(interview_config)

    def test_build_branding_config_invalid_logo_url_not_string(self):
        """Test that non-string logo URL is rejected."""
        step = CreateRoomStep()
        interview_config = {
            "branding": {
                "logo_url": 12345,
            }
        }
        with pytest.raises(ValueError, match="logo_url must be a string"):
            step._build_branding_config(interview_config)

    def test_build_branding_config_valid_colors_rgba(self):
        """Test that valid rgba colors are accepted."""
        step = CreateRoomStep()
        interview_config = {
            "branding": {
                "colors": {
                    "background": "rgba(18, 26, 36, 1)",
                    "text": "rgba(255, 255, 255, 1)",
                }
            }
        }
        result = step._build_branding_config(interview_config)
        assert result["colors"]["background"] == "rgba(18, 26, 36, 1)"
        assert result["colors"]["text"] == "rgba(255, 255, 255, 1)"

    def test_build_branding_config_valid_colors_rgb(self):
        """Test that valid rgb colors are accepted."""
        step = CreateRoomStep()
        interview_config = {
            "branding": {
                "colors": {
                    "background": "rgb(18, 26, 36)",
                }
            }
        }
        result = step._build_branding_config(interview_config)
        assert result["colors"]["background"] == "rgb(18, 26, 36)"

    def test_build_branding_config_valid_colors_hex(self):
        """Test that valid hex colors are accepted."""
        step = CreateRoomStep()
        interview_config = {
            "branding": {
                "colors": {
                    "background": "#121A24",
                    "text": "#FFFFFF",
                }
            }
        }
        result = step._build_branding_config(interview_config)
        assert result["colors"]["background"] == "#121A24"
        assert result["colors"]["text"] == "#FFFFFF"

    def test_build_branding_config_valid_colors_named(self):
        """Test that valid named colors are accepted."""
        step = CreateRoomStep()
        interview_config = {
            "branding": {
                "colors": {
                    "background": "black",
                    "text": "white",
                }
            }
        }
        result = step._build_branding_config(interview_config)
        assert result["colors"]["background"] == "black"
        assert result["colors"]["text"] == "white"

    def test_build_branding_config_invalid_color_format(self):
        """Test that invalid color format is rejected."""
        step = CreateRoomStep()
        interview_config = {
            "branding": {
                "colors": {
                    "background": "not-a-color",
                }
            }
        }
        with pytest.raises(ValueError, match="Invalid color format"):
            step._build_branding_config(interview_config)

    def test_build_branding_config_invalid_color_not_string(self):
        """Test that non-string color is rejected."""
        step = CreateRoomStep()
        interview_config = {
            "branding": {
                "colors": {
                    "background": 12345,
                }
            }
        }
        with pytest.raises(ValueError, match="background must be a string"):
            step._build_branding_config(interview_config)

    def test_build_branding_config_invalid_colors_not_dict(self):
        """Test that non-dict colors is rejected."""
        step = CreateRoomStep()
        interview_config = {
            "branding": {
                "colors": "not-a-dict",
            }
        }
        with pytest.raises(ValueError, match="colors must be a dictionary"):
            step._build_branding_config(interview_config)

    def test_build_branding_config_all_color_keys(self):
        """Test that all supported color keys are processed."""
        step = CreateRoomStep()
        interview_config = {
            "branding": {
                "colors": {
                    "background": "rgba(18, 26, 36, 1)",
                    "background_accent": "rgba(31, 45, 61, 1)",
                    "text": "rgba(255, 255, 255, 1)",
                    "border": "rgba(43, 63, 86, 1)",
                    "main_area_background": "rgba(18, 26, 36, 1)",
                    "main_area_background_accent": "rgba(43, 63, 86, 1)",
                }
            }
        }
        result = step._build_branding_config(interview_config)
        assert len(result["colors"]) == 6
        assert all(
            key in result["colors"]
            for key in [
                "background",
                "background_accent",
                "text",
                "border",
                "main_area_background",
                "main_area_background_accent",
            ]
        )

    def test_build_branding_config_multiple_validation_errors(self):
        """Test that multiple validation errors are reported."""
        step = CreateRoomStep()
        interview_config = {
            "branding": {
                "logo_url": "invalid-url",
                "colors": {
                    "background": "not-a-color",
                    "text": 12345,
                },
            }
        }
        with pytest.raises(ValueError) as exc_info:
            step._build_branding_config(interview_config)
        error_msg = str(exc_info.value)
        assert "Invalid logo_url format" in error_msg
        assert "Invalid color format" in error_msg
        assert "text must be a string" in error_msg


class TestCreateRoomStepRoomOverrides:
    """Tests for _build_room_overrides method."""

    def test_build_room_overrides_defaults(self):
        """Test that default overrides include recording and transcription."""
        step = CreateRoomStep()
        interview_config = {}
        branding_config = {}
        result = step._build_room_overrides(interview_config, branding_config)
        assert result["capabilities"]["recording"] is True
        assert result["capabilities"]["transcription"] is True
        assert result["capabilities"]["live_captions"] is False

    def test_build_room_overrides_with_branding(self):
        """Test that branding config is included in overrides."""
        step = CreateRoomStep()
        interview_config = {}
        branding_config = {
            "logo_url": "https://example.com/logo.png",
            "colors": {"background": "rgba(18, 26, 36, 1)"},
        }
        result = step._build_room_overrides(interview_config, branding_config)
        assert result["branding"] == branding_config

    def test_build_room_overrides_with_live_captions(self):
        """Test that live_captions setting is respected."""
        step = CreateRoomStep()
        interview_config = {"live_captions": True}
        branding_config = {}
        result = step._build_room_overrides(interview_config, branding_config)
        assert result["capabilities"]["live_captions"] is True

    def test_build_room_overrides_with_room_settings(self):
        """Test that room_settings are merged into overrides."""
        step = CreateRoomStep()
        interview_config = {
            "room_settings": {
                "capabilities": {"chat": True},
                "media": {"video": True},
                "access": {"max_participants": 10},
            }
        }
        branding_config = {}
        result = step._build_room_overrides(interview_config, branding_config)
        assert result["capabilities"]["chat"] is True
        assert result["capabilities"]["recording"] is True  # Still present
        assert result["media"]["video"] is True
        assert result["access"]["max_participants"] == 10

    def test_build_room_overrides_room_settings_override_capabilities(self):
        """Test that room_settings capabilities override defaults."""
        step = CreateRoomStep()
        interview_config = {
            "room_settings": {
                "capabilities": {"recording": False},
            }
        }
        branding_config = {}
        result = step._build_room_overrides(interview_config, branding_config)
        # room_settings should override the default
        assert result["capabilities"]["recording"] is False
        # But transcription should still be True (default)
        assert result["capabilities"]["transcription"] is True


class TestCreateRoomStepValidation:
    """Tests for validation helper methods."""

    def test_validate_url_valid_http(self):
        """Test that valid HTTP URL is accepted."""
        step = CreateRoomStep()
        assert step._validate_url("http://example.com/logo.png") is True

    def test_validate_url_valid_https(self):
        """Test that valid HTTPS URL is accepted."""
        step = CreateRoomStep()
        assert step._validate_url("https://example.com/logo.png") is True

    def test_validate_url_invalid_no_scheme(self):
        """Test that URL without scheme is rejected."""
        step = CreateRoomStep()
        assert step._validate_url("example.com/logo.png") is False

    def test_validate_url_invalid_no_domain(self):
        """Test that URL without domain is rejected."""
        step = CreateRoomStep()
        assert step._validate_url("https://") is False

    def test_validate_color_rgba(self):
        """Test rgba color validation."""
        step = CreateRoomStep()
        assert step._validate_color("rgba(255, 255, 255, 1)") is True
        assert step._validate_color("rgba(0, 0, 0, 0.5)") is True

    def test_validate_color_rgb(self):
        """Test rgb color validation."""
        step = CreateRoomStep()
        assert step._validate_color("rgb(255, 255, 255)") is True

    def test_validate_color_hex(self):
        """Test hex color validation."""
        step = CreateRoomStep()
        assert step._validate_color("#FFFFFF") is True
        assert step._validate_color("#000000") is True
        assert step._validate_color("#FF0000AA") is True  # With alpha

    def test_validate_color_named(self):
        """Test named color validation."""
        step = CreateRoomStep()
        assert step._validate_color("black") is True
        assert step._validate_color("white") is True
        assert step._validate_color("red") is True

    def test_validate_color_invalid(self):
        """Test invalid color formats are rejected."""
        step = CreateRoomStep()
        assert step._validate_color("not-a-color") is False
        assert step._validate_color("#GGG") is False
        assert step._validate_color("rgb()") is False
        assert step._validate_color(12345) is False  # Not a string


class TestCreateRoomStepRoomConfigValidation:
    """Tests for _validate_room_config method."""

    def test_validate_room_config_empty(self):
        """Test that empty config passes validation."""
        step = CreateRoomStep()
        interview_config = {}
        # Should not raise
        step._validate_room_config(interview_config)

    def test_validate_room_config_valid_profile(self):
        """Test that valid room_profile passes validation."""
        step = CreateRoomStep()
        interview_config = {"room_profile": "podcast"}
        # Should not raise
        step._validate_room_config(interview_config)

    def test_validate_room_config_invalid_profile_not_string(self):
        """Test that non-string room_profile is rejected."""
        step = CreateRoomStep()
        interview_config = {"room_profile": 12345}
        with pytest.raises(ValueError, match="room_profile must be a string"):
            step._validate_room_config(interview_config)

    def test_validate_room_config_valid_live_captions(self):
        """Test that valid live_captions passes validation."""
        step = CreateRoomStep()
        interview_config = {"live_captions": True}
        # Should not raise
        step._validate_room_config(interview_config)

    def test_validate_room_config_invalid_live_captions_not_bool(self):
        """Test that non-boolean live_captions is rejected."""
        step = CreateRoomStep()
        interview_config = {"live_captions": "yes"}
        with pytest.raises(ValueError, match="live_captions must be a boolean"):
            step._validate_room_config(interview_config)

    def test_validate_room_config_valid_room_settings(self):
        """Test that valid room_settings passes validation."""
        step = CreateRoomStep()
        interview_config = {
            "room_settings": {
                "capabilities": {"chat": True},
                "media": {"video": True},
                "access": {"max_participants": 10},
            }
        }
        # Should not raise
        step._validate_room_config(interview_config)

    def test_validate_room_config_invalid_room_settings_not_dict(self):
        """Test that non-dict room_settings is rejected."""
        step = CreateRoomStep()
        interview_config = {"room_settings": "not-a-dict"}
        with pytest.raises(ValueError, match="room_settings must be a dictionary"):
            step._validate_room_config(interview_config)

    def test_validate_room_config_invalid_capabilities_not_dict(self):
        """Test that non-dict capabilities is rejected."""
        step = CreateRoomStep()
        interview_config = {
            "room_settings": {
                "capabilities": "not-a-dict",
            }
        }
        with pytest.raises(
            ValueError, match="room_settings.capabilities must be a dictionary"
        ):
            step._validate_room_config(interview_config)

    def test_validate_room_config_invalid_max_participants_negative(self):
        """Test that negative max_participants is rejected."""
        step = CreateRoomStep()
        interview_config = {
            "room_settings": {
                "access": {"max_participants": -1},
            }
        }
        with pytest.raises(
            ValueError, match="max_participants must be a positive integer"
        ):
            step._validate_room_config(interview_config)

    def test_validate_room_config_invalid_max_participants_zero(self):
        """Test that zero max_participants is rejected."""
        step = CreateRoomStep()
        interview_config = {
            "room_settings": {
                "access": {"max_participants": 0},
            }
        }
        with pytest.raises(
            ValueError, match="max_participants must be a positive integer"
        ):
            step._validate_room_config(interview_config)

    def test_validate_room_config_valid_max_participants_none(self):
        """Test that None max_participants is accepted."""
        step = CreateRoomStep()
        interview_config = {
            "room_settings": {
                "access": {"max_participants": None},
            }
        }
        # Should not raise
        step._validate_room_config(interview_config)


class TestCreateRoomStepExecute:
    """Tests for execute method with mocked provider."""

    @pytest.mark.asyncio
    async def test_execute_missing_provider_keys(self):
        """Test that missing provider_keys returns error."""
        step = CreateRoomStep()
        state = {
            "session_id": "test-session",
            # Missing provider_keys
        }
        result = await step.execute(state)
        assert result["error"] is not None
        assert "Missing required state" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_missing_api_key(self):
        """Test that missing API key returns error."""
        step = CreateRoomStep()
        state = {
            "session_id": "test-session",
            "provider_keys": {
                # Missing room_provider_key
                "room_provider": "daily",
            },
        }
        result = await step.execute(state)
        assert result["error"] is not None
        assert "Missing room_provider_key" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_unsupported_provider(self):
        """Test that unsupported provider returns error."""
        step = CreateRoomStep()
        state = {
            "session_id": "test-session",
            "provider_keys": {
                "room_provider_key": "test-key",
                "room_provider": "unsupported",
            },
        }
        result = await step.execute(state)
        assert result["error"] is not None
        assert "Unsupported room provider" in result["error"]

    @pytest.mark.asyncio
    @patch("flow.steps.interview.create_room.httpx.AsyncClient")
    async def test_execute_success(self, mock_client_class):
        """Test successful room creation."""
        # Mock the httpx client
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "id": "room-123",
            "url": "https://example.daily.co/test-room",
            "created_at": "2025-01-01T00:00:00Z",
            "config": {},
            "privacy": "public",
        }
        mock_response.raise_for_status = AsyncMock()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        step = CreateRoomStep()
        state = {
            "session_id": "test-session",
            "provider_keys": {
                "room_provider_key": "test-key",
                "room_provider": "daily",
            },
            "interview_config": {},
        }

        result = await step.execute(state)

        assert result["error"] is None
        assert result["room_id"] == "room-123"
        assert result["room_url"] == "https://example.daily.co/test-room"
        assert result["room_name"] == "test-room"
        assert result["processing_status"] == "room_created"
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    @patch("flow.steps.interview.create_room.httpx.AsyncClient")
    async def test_execute_provider_error(self, mock_client_class):
        """Test handling of provider API errors."""
        # Mock the httpx client to raise an HTTPStatusError
        import httpx

        mock_response = AsyncMock()
        mock_response.json.return_value = {"error": "Invalid API key"}
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Invalid API key", request=AsyncMock(), response=mock_response
        )

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        step = CreateRoomStep()
        state = {
            "session_id": "test-session",
            "provider_keys": {
                "room_provider_key": "invalid-key",
                "room_provider": "daily",
            },
            "interview_config": {},
        }

        result = await step.execute(state)

        assert result["error"] is not None
        assert "Failed to create video room" in result["error"]
        assert "Invalid API key" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_invalid_branding_config(self):
        """Test that invalid branding config returns error."""
        step = CreateRoomStep()
        state = {
            "session_id": "test-session",
            "provider_keys": {
                "room_provider_key": "test-key",
                "room_provider": "daily",
            },
            "interview_config": {
                "branding": {
                    "logo_url": "invalid-url",  # Invalid URL
                }
            },
        }

        result = await step.execute(state)

        assert result["error"] is not None
        assert "Invalid configuration" in result["error"]
        assert "Invalid logo_url format" in result["error"]

    @pytest.mark.asyncio
    @patch("flow.steps.interview.create_room.httpx.AsyncClient")
    async def test_execute_with_branding(self, mock_client_class):
        """Test room creation with valid branding config."""
        # Mock the httpx client
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "id": "room-123",
            "url": "https://example.daily.co/test-room",
            "created_at": "2025-01-01T00:00:00Z",
            "config": {},
            "privacy": "public",
        }
        mock_response.raise_for_status = AsyncMock()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        step = CreateRoomStep()
        state = {
            "session_id": "test-session",
            "provider_keys": {
                "room_provider_key": "test-key",
                "room_provider": "daily",
            },
            "interview_config": {
                "branding": {
                    "logo_url": "https://example.com/logo.png",
                    "colors": {
                        "background": "rgba(18, 26, 36, 1)",
                        "text": "rgba(255, 255, 255, 1)",
                    },
                }
            },
        }

        result = await step.execute(state)

        assert result["error"] is None
        assert result["branding"] is not None
        assert result["branding"]["logo_url"] == "https://example.com/logo.png"
        assert "colors" in result["branding"]

    @pytest.mark.asyncio
    @patch("flow.steps.interview.create_room.httpx.AsyncClient")
    async def test_execute_no_room_url_returned(self, mock_client_class):
        """Test handling when provider doesn't return room_url."""
        # Mock the httpx client to return response without URL
        mock_response = AsyncMock()
        mock_response.json.return_value = {
            "id": "room-123",
            # Missing url field
            "created_at": "2025-01-01T00:00:00Z",
            "config": {},
            "privacy": "public",
        }
        mock_response.raise_for_status = AsyncMock()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        step = CreateRoomStep()
        state = {
            "session_id": "test-session",
            "provider_keys": {
                "room_provider_key": "test-key",
                "room_provider": "daily",
            },
            "interview_config": {},
        }

        result = await step.execute(state)

        assert result["error"] is not None
        assert "no room_url returned" in result["error"]

    @pytest.mark.asyncio
    @patch("flow.steps.interview.create_room.httpx.AsyncClient")
    async def test_execute_exception_handling(self, mock_client_class):
        """Test that exceptions are caught and handled."""
        # Mock the httpx client to raise an exception
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.post = AsyncMock(side_effect=Exception("Network error"))
        mock_client_class.return_value = mock_client

        step = CreateRoomStep()
        state = {
            "session_id": "test-session",
            "provider_keys": {
                "room_provider_key": "test-key",
                "room_provider": "daily",
            },
            "interview_config": {},
        }

        result = await step.execute(state)

        assert result["error"] is not None
        assert "Failed to create video room" in result["error"]
        assert "Network error" in result["error"]
