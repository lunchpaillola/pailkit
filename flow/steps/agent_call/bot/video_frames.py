# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""Video frames loading for bot animation."""

import logging
import os
from typing import Any, Dict, Optional

from PIL import Image
from pipecat.frames.frames import OutputImageRawFrame, SpriteFrame

logger = logging.getLogger(__name__)


def load_bot_video_frames(
    bot_config: Dict[str, Any],
) -> tuple[
    Optional[OutputImageRawFrame],
    Optional[OutputImageRawFrame | SpriteFrame | list[OutputImageRawFrame]],
]:
    """
    Load video frames for the bot based on configuration.

    Supports two modes:
    - "static": Load a single static image (e.g., robot01.png)
    - "animated": Load all frame_*.png files for sprite animation

    Args:
        bot_config: Bot configuration dictionary

    Returns:
        Tuple of (quiet_frame, talking_frame)
        - For static mode: Both frames are the same single image
        - For animated mode: quiet_frame is first frame, talking_frame is SpriteFrame with all frames
    """
    script_dir = os.path.dirname(__file__)
    hosting_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(script_dir))), "hosting"
    )
    sprites_dir = os.path.join(hosting_dir, "sprites")

    # Get video mode from config (default to "animated")
    video_mode = bot_config.get("video_mode", "animated")

    if video_mode == "static":
        # Load a single static image
        static_image = bot_config.get("static_image", "robot01.png")
        image_path = os.path.join(sprites_dir, static_image)

        if os.path.exists(image_path):
            with Image.open(image_path) as img:
                # Convert RGBA to RGB to remove alpha channel and prevent compositing
                if img.mode == "RGBA":
                    # Create a white background and paste the RGBA image on it
                    rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                    rgb_img.paste(img, mask=img.split()[3])  # Use alpha channel as mask
                    img = rgb_img
                elif img.mode != "RGB":
                    img = img.convert("RGB")
                single_frame = OutputImageRawFrame(
                    image=img.tobytes(), size=img.size, format=img.mode
                )
            logger.info(f"Loaded static image from {image_path}")
            return (single_frame, single_frame)
        else:
            logger.warning(f"Static image not found: {image_path}")
            return (None, None)

    elif video_mode == "animated":
        # Load all frame_*.png files for animation (case-insensitive)
        frame_files = []
        if os.path.exists(sprites_dir):
            for filename in os.listdir(sprites_dir):
                # Case-insensitive matching for frame files
                if filename.lower().startswith("frame_") and filename.lower().endswith(
                    ".png"
                ):
                    frame_files.append(filename)

            # Sort frames numerically (case-insensitive)
            frame_files.sort(
                key=lambda x: int(x.lower().replace("frame_", "").replace(".png", ""))
            )

            if frame_files:
                sprites = []
                logger.info(
                    f"Loading {len(frame_files)} sprite frames from {sprites_dir}"
                )

                for frame_filename in frame_files:
                    full_path = os.path.join(sprites_dir, frame_filename)
                    with Image.open(full_path) as img:
                        # Convert RGBA to RGB to remove alpha channel and prevent compositing
                        if img.mode == "RGBA":
                            # Create a white background and paste the RGBA image on it
                            rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                            rgb_img.paste(
                                img, mask=img.split()[3]
                            )  # Use alpha channel as mask
                            img = rgb_img
                        elif img.mode != "RGB":
                            img = img.convert("RGB")
                        sprites.append(
                            OutputImageRawFrame(
                                image=img.tobytes(), size=img.size, format=img.mode
                            )
                        )

                # Create a smooth animation by adding reversed frames (like reference implementation)
                # This makes the animation go forward then backward, creating a smooth loop
                flipped = sprites[::-1]
                sprites.extend(flipped)
                logger.info(
                    f"Added reversed frames: {len(sprites)} total frames (forward + backward)"
                )

                # Duplicate each frame to slow down the animation (like reference implementation)
                # This makes each frame display longer, creating a smoother, slower animation
                frames_per_sprite = bot_config.get(
                    "animation_frames_per_sprite", 1
                )  # Default: show each frame 3 times
                slowed_sprites = []
                for sprite in sprites:
                    for _ in range(frames_per_sprite):
                        slowed_sprites.append(sprite)

                logger.info(
                    f"Created animation with {len(slowed_sprites)} frames (slowed by {frames_per_sprite}x)"
                )

                # First frame for quiet state, animated SpriteFrame for talking
                # SpriteFrame handles animation internally - we just push it once
                quiet_frame = sprites[0] if sprites else None
                talking_frame = (
                    SpriteFrame(images=slowed_sprites) if slowed_sprites else None
                )

                return (quiet_frame, talking_frame)
            else:
                logger.warning(f"No frame files found in {sprites_dir}")
                return (None, None)
        else:
            logger.warning(f"Sprites directory not found: {sprites_dir}")
            return (None, None)

    else:
        logger.warning(f"Unknown video_mode: {video_mode}. Using static mode.")
        return (None, None)
