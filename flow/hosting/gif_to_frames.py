# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

from PIL import Image
import os


def gif_to_png_sequence(gif_path, output_dir):
    """
    Convert a GIF into individual PNG frames.

    Args:
        gif_path: Path to your GIF file
        output_dir: Folder to save the output PNG frames
    """
    os.makedirs(output_dir, exist_ok=True)

    gif = Image.open(gif_path)
    frame_index = 0

    try:
        while True:
            gif.seek(frame_index)
            frame = gif.convert("RGBA")  # Keep transparency if needed

            output_path = os.path.join(output_dir, f"frame_{frame_index:03}.png")
            frame.save(output_path)

            print(f"Saved {output_path}")
            frame_index += 1

    except EOFError:
        print(f"\nDone converting GIF to PNG sequence. Total frames: {frame_index}")


# Example usage:
if __name__ == "__main__":
    gif_to_png_sequence(gif_path="Voice sprite.gif", output_dir="voice_sprites")
