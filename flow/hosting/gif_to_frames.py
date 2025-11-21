# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

from PIL import Image
import os


def gif_to_png_sequence(gif_path, output_dir, sample_rate=1):
    """
    Convert a GIF into individual PNG frames, optionally sampling frames.

    Args:
        gif_path: Path to your GIF file
        output_dir: Folder to save the output PNG frames
        sample_rate: Extract every Nth frame (1 = all frames, 3 = every 3rd frame)
    """
    os.makedirs(output_dir, exist_ok=True)

    gif = Image.open(gif_path)
    source_frame_index = 0  # Frame index in the GIF
    output_frame_index = 0  # Frame number for output filename

    try:
        while True:
            gif.seek(source_frame_index)
            # Convert to RGB to strip alpha channel (remove transparency)
            # This is equivalent to: magick input.png -strip -alpha off output.png
            frame = gif.convert("RGB")

            # Format: frame_001.png, frame_002.png, etc. (starting from 001, lowercase)
            output_path = os.path.join(
                output_dir, f"frame_{output_frame_index + 1:03}.png"
            )
            frame.save(output_path)

            print(f"Saved {output_path} (from GIF frame {source_frame_index})")
            output_frame_index += 1
            source_frame_index += sample_rate  # Skip to next frame to sample

    except EOFError:
        print(
            f"\nDone converting GIF to PNG sequence. Total frames extracted: {output_frame_index}"
        )


# Example usage:
if __name__ == "__main__":
    # Sample every 3rd frame from the GIF
    gif_to_png_sequence(gif_path="audiogif.gif", output_dir="sprites", sample_rate=3)
