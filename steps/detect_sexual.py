"""Stage 2 — detect sexual/explicit content with NudeNet v3."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Minimum NudeNet score to flag a detection.
SCORE_THRESHOLD: float = 0.45

# All classes that trigger a blur — strict mode: any exposed or covered private area.
BLUR_CLASSES: frozenset[str] = frozenset({
    "FEMALE_BREAST_EXPOSED",
    "FEMALE_GENITALIA_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
    "MALE_BREAST_EXPOSED",
    "BUTTOCKS_EXPOSED",
    "ANUS_EXPOSED",
    "FEMALE_GENITALIA_COVERED",
    "BUTTOCKS_COVERED",
    "ANUS_COVERED",
    "BELLY_EXPOSED",
    "ARMPITS_EXPOSED",
})


@dataclass
class SexualDetection:
    cls: str             # NudeNet class label
    score: float         # confidence (0–1)
    bbox: list[float]    # [x1, y1, x2, y2] in pixel coordinates


def load_model() -> Any:
    """Load the NudeNet v3 detector (downloads weights on first run)."""
    from nudenet import NudeDetector  # type: ignore

    return NudeDetector()


def _to_xyxy(box: list) -> list[float]:
    """Convert [x, y, w, h] → [x1, y1, x2, y2]. Handles already-xyxy lists too."""
    if len(box) != 4:
        return list(map(float, box))
    x, y, w, h = map(float, box)
    # If w > x and h > y it is already x2,y2 — pass through; otherwise convert.
    if w > x and h > y:
        return [x, y, w, h]
    return [x, y, x + w, y + h]


def detect_sexual(
    model: Any,
    frame_path: Path,
) -> tuple[bool, list[SexualDetection]]:
    """
    Run NudeNet on one frame.

    Returns:
        should_blur  – True if any flagged class exceeds SCORE_THRESHOLD.
        detections   – All matching detections.
    """
    raw: list[dict] = model.detect(str(frame_path))

    detections: list[SexualDetection] = []
    should_blur = False

    for item in raw:
        cls: str = item.get("class", "")
        score: float = float(item.get("score", 0.0))

        if cls not in BLUR_CLASSES or score < SCORE_THRESHOLD:
            continue

        # NudeNet v3 uses "box"; some builds use "bbox" — handle both.
        raw_box = item.get("box") or item.get("bbox") or [0, 0, 0, 0]
        detections.append(SexualDetection(cls=cls, score=score, bbox=_to_xyxy(raw_box)))
        should_blur = True

    return should_blur, detections
