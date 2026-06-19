"""Extract one JPEG frame per second from a video using ffmpeg."""

import subprocess
from pathlib import Path

# Frames-per-second rate for analysis. 1 fps → one frame per second of video.
FPS: int = 1


def extract_frames(video_path: Path, frames_dir: Path) -> list[Path]:
    """
    Write one JPEG per second to *frames_dir* and return the sorted list of paths.

    Frame filenames: frame_000001.jpg, frame_000002.jpg, …
    Frame N corresponds to second (N-1) of the video (1-indexed by ffmpeg).
    """
    frames_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"fps={FPS}",
        "-q:v", "2",            # high JPEG quality (lower number = better)
        str(frames_dir / "frame_%06d.jpg"),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg frame extraction failed:\n{result.stderr[-2000:]}")

    frames = sorted(frames_dir.glob("frame_*.jpg"))
    if not frames:
        raise RuntimeError("ffmpeg ran but produced no frame files — check the video.")
    return frames
