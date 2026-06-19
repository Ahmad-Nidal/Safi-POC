"""
Safi — clean a YouTube video for a Muslim audience.

Usage:
    python safi.py "https://youtube.com/watch?v=VIDEO_ID"

Outputs two MP4 files in output/:
  safi_<id>_clean.mp4        music removed + women blurred + sexual content blurred
  safi_<id>_sexual_only.mp4  music removed + only sexual content blurred (for evaluation)
"""

import argparse
import sys
import time
from pathlib import Path

from steps.downloader import download, extract_video_id
from steps.audio import remove_music
from steps.frames import extract_frames
from steps.detect_gender import load_model as load_gender_model
from steps.detect_sexual import load_model as load_sexual_model
from steps.analyze import analyze_frames
from steps.annotations import save_annotations
from steps.encoder import render

# ── Top-level settings ──────────────────────────────────────────────────────
# These will be exposed as CLI flags in the future MVP.
BLUR_WOMEN: bool = True
BLUR_MEN: bool = False

TMP_BASE: Path = Path("tmp")
OUTPUT_DIR: Path = Path("output")


def _fmt(seconds: float) -> str:
    """Format a duration in seconds as a human-readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Safi — process a YouTube video to remove music and blur inappropriate content.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", help="YouTube video URL (any standard form)")
    args = parser.parse_args()

    url: str = args.url

    try:
        video_id = extract_video_id(url)
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        sys.exit(1)

    tmp_dir = TMP_BASE / video_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    timings: dict[str, float] = {}
    t_total = time.perf_counter()

    # ── Step 1: Download ─────────────────────────────────────────────────────
    print(f"\n[1/6] Downloading  →  {url}")
    t = time.perf_counter()
    video_path, video_id, title, duration = download(url, tmp_dir)
    timings["1. Download"] = time.perf_counter() - t
    print(f"      {video_path.name}  |  {duration:.0f}s  |  {title}")

    # ── Step 2: Music removal ────────────────────────────────────────────────
    print(f"\n[2/6] Demucs — music removal (htdemucs, vocals-only stem)...")
    t = time.perf_counter()
    vocals_path = remove_music(video_path, tmp_dir)
    timings["2. Music removal"] = time.perf_counter() - t
    print(f"      Vocals stem: {vocals_path}")

    # ── Step 3: Frame extraction ─────────────────────────────────────────────
    print(f"\n[3/6] Extracting frames at 1 fps...")
    t = time.perf_counter()
    frames_dir = tmp_dir / "frames"
    frames = extract_frames(video_path, frames_dir)
    timings["3. Frame extraction"] = time.perf_counter() - t
    print(f"      {len(frames)} frames extracted to {frames_dir}")

    # ── Step 4: Load detection models ────────────────────────────────────────
    print(f"\n[4/6] Loading detection models...")
    t = time.perf_counter()
    print("      Loading InsightFace buffalo_l (downloads weights on first run)...")
    gender_model = load_gender_model()
    print("      Loading NudeNet v3...")
    sexual_model = load_sexual_model()
    timings["4. Model loading"] = time.perf_counter() - t
    print("      Both models ready.")

    # ── Step 5: Analyse frames ───────────────────────────────────────────────
    print(f"\n[5/6] Analysing {len(frames)} frames  "
          f"(Stage 1: InsightFace  →  Stage 2: NudeNet if not already flagged)...")
    t = time.perf_counter()
    results = analyze_frames(
        frames,
        gender_model,
        sexual_model,
        blur_women=BLUR_WOMEN,
        blur_men=BLUR_MEN,
    )
    timings["5. Frame analysis"] = time.perf_counter() - t

    women_seconds = sorted({r.time_sec for r in results if r.flagged_women})
    sexual_seconds = sorted({r.time_sec for r in results if r.flagged_sexual})
    print(f"      {len(women_seconds):4d} seconds flagged for women blur")
    print(f"      {len(sexual_seconds):4d} seconds flagged for sexual content blur")

    settings = {"blur_women": BLUR_WOMEN, "blur_men": BLUR_MEN}
    ann_path = save_annotations(tmp_dir, video_id, title, duration, results, settings)
    print(f"      Annotations → {ann_path}")

    # ── Step 6: Render ───────────────────────────────────────────────────────
    print(f"\n[6/6] Rendering output videos...")
    t = time.perf_counter()

    clean_seconds = sorted(set(women_seconds) | set(sexual_seconds))
    clean_path = OUTPUT_DIR / f"safi_{video_id}.mp4"
    print(f"      Rendering clean version  ({len(clean_seconds)} blur ranges)...")
    render(video_path, vocals_path, clean_path, clean_seconds)
    print(f"      → {clean_path}")

    timings["6. Rendering"] = time.perf_counter() - t

    # ── Timing summary ───────────────────────────────────────────────────────
    total = time.perf_counter() - t_total
    print(f"\n{'─' * 42}")
    print(f"  Timing summary")
    print(f"{'─' * 42}")
    for label, elapsed in timings.items():
        pct = elapsed / total * 100
        print(f"  {label:<22}  {_fmt(elapsed):>8}  ({pct:.0f}%)")
    print(f"{'─' * 42}")
    print(f"  {'Total':<22}  {_fmt(total):>8}")
    print(f"{'─' * 42}\n")


if __name__ == "__main__":
    main()
