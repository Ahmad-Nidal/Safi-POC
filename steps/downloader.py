"""Download a YouTube video using yt-dlp and parse metadata."""

import json
import re
import subprocess
import sys
from pathlib import Path


def extract_video_id(url: str) -> str:
    """Parse the 11-character video ID from any recognised YouTube URL form."""
    pattern = r"(?:v=|youtu\.be/|embed/|shorts/)([a-zA-Z0-9_-]{11})"
    match = re.search(pattern, url)
    if not match:
        raise ValueError(f"Cannot extract video ID from URL: {url}")
    return match.group(1)


def download(url: str, tmp_dir: Path) -> tuple[Path, str, str, float]:
    """
    Download video to *tmp_dir* with yt-dlp.

    Returns (video_path, video_id, title, duration_seconds).
    Exits the process with a clear message if yt-dlp fails.
    """
    video_id = extract_video_id(url)
    output_template = str(tmp_dir / "video.%(ext)s")

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--output", output_template,
        "--write-info-json",
        "--no-overwrites",
        url,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("[ERROR] yt-dlp failed — check the URL and your internet connection.")
        print(result.stderr[-2000:])
        sys.exit(1)

    # Locate the downloaded file (prefer .mp4, fall back to first match)
    mp4_files = list(tmp_dir.glob("video.mp4"))
    all_video_files = list(tmp_dir.glob("video.*"))
    # Exclude info.json from the video file search
    all_video_files = [f for f in all_video_files if f.suffix != ".json"]
    video_path = mp4_files[0] if mp4_files else (all_video_files[0] if all_video_files else None)

    if video_path is None:
        print("[ERROR] yt-dlp appeared to succeed but no video file was found in tmp/")
        sys.exit(1)

    # Read metadata from the info JSON yt-dlp writes automatically
    title = video_id
    duration = 0.0
    info_files = list(tmp_dir.glob("video.info.json"))
    if info_files:
        with open(info_files[0], encoding="utf-8") as fh:
            info = json.load(fh)
        title = info.get("title", video_id)
        duration = float(info.get("duration", 0))

    return video_path, video_id, title, duration
