"""
Sequential two-stage frame analysis.

Stage 1 (InsightFace) runs first.  If it flags the frame, Stage 2 (NudeNet)
is skipped — the frame will be blurred regardless, so the extra inference
would be wasted compute.  Stage 2 only runs on frames Stage 1 let through.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from steps.detect_gender import FaceDetection, detect_faces
from steps.detect_sexual import SexualDetection, detect_sexual


@dataclass
class FrameResult:
    time_sec: int                               # second index (0-based)
    flagged_women: bool
    flagged_sexual: bool
    women_detections: list[FaceDetection] = field(default_factory=list)
    sexual_detections: list[SexualDetection] = field(default_factory=list)


def analyze_frames(
    frames: list[Path],
    gender_model: Any,
    sexual_model: Any,
    blur_women: bool = True,
    blur_men: bool = False,
) -> list[FrameResult]:
    """
    Iterate every frame through the two-stage sequential filter.

    Each frame's index corresponds directly to its second in the video
    (frame 0 → 0 s, frame 1 → 1 s, …) because frames are extracted at 1 fps.
    """
    results: list[FrameResult] = []
    total = len(frames)

    for i, frame_path in enumerate(frames):
        # Progress indicator — print every 10 frames to avoid flooding stdout.
        if i % 10 == 0 or i == total - 1:
            print(f"      frame {i + 1}/{total}", end="\r", flush=True)

        # ── Stage 1: InsightFace ─────────────────────────────────────────────
        flag_women, women_dets = detect_faces(gender_model, frame_path, blur_women, blur_men)

        if flag_women:
            # Skip Stage 2 — the whole frame gets blurred anyway.
            results.append(FrameResult(
                time_sec=i,
                flagged_women=True,
                flagged_sexual=False,
                women_detections=women_dets,
                sexual_detections=[],
            ))
            continue

        # ── Stage 2: NudeNet (only reached when Stage 1 did not flag) ────────
        flag_sexual, sexual_dets = detect_sexual(sexual_model, frame_path)

        results.append(FrameResult(
            time_sec=i,
            flagged_women=False,
            flagged_sexual=flag_sexual,
            women_detections=women_dets,  # may contain male faces that weren't flagged
            sexual_detections=sexual_dets,
        ))

    print()  # newline after the \r progress line
    return results
