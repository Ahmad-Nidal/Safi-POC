"""Render output MP4 files with vocal-only audio and whole-frame blur."""

import subprocess
from pathlib import Path

BLUR_LR: int = 10   # boxblur luma radius
BLUR_LP: int = 10   # boxblur luma power (iterations)


def _merge_ranges(seconds: list[int]) -> list[tuple[int, int]]:
    """Collapse individual seconds into contiguous [start, end) ranges."""
    sorted_secs = sorted(set(seconds))
    if not sorted_secs:
        return []
    ranges: list[tuple[int, int]] = []
    start = end = sorted_secs[0]
    for s in sorted_secs[1:]:
        if s == end + 1:
            end = s
        else:
            ranges.append((start, end + 1))
            start = end = s
    ranges.append((start, end + 1))
    return ranges


def _build_blur_filter(seconds: list[int]) -> str | None:
    """
    Build an ffmpeg -vf boxblur filter with an enable expression covering
    every flagged second.  Ranges are merged first to keep the expression short.
    Returns None if no seconds are flagged.
    """
    if not seconds:
        return None
    ranges = _merge_ranges(seconds)
    time_expr = "+".join(f"between(t,{s},{e})" for s, e in ranges)
    return f"boxblur=lr={BLUR_LR}:lp={BLUR_LP}:enable='{time_expr}'"


def render(
    video_path: Path,
    vocals_path: Path,
    output_path: Path,
    blur_seconds: list[int],
) -> None:
    """
    Produce *output_path* from *video_path* with:
    - audio replaced by *vocals_path* (Demucs vocals stem)
    - full boxblur applied to every second in *blur_seconds*
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    blur_filter = _build_blur_filter(blur_seconds)

    cmd = ["ffmpeg", "-y", "-i", str(video_path), "-i", str(vocals_path)]

    if blur_filter:
        cmd += ["-map", "0:v:0", "-vf", blur_filter]
    else:
        cmd += ["-map", "0:v:0"]

    cmd += [
        "-map", "1:a:0",
        "-c:v", "libx264",
        "-crf", "23",
        "-preset", "medium",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg render failed for {output_path.name}:\n{result.stderr[-3000:]}"
        )
