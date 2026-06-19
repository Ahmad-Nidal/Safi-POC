"""Stage 1 — detect faces and filter by gender with InsightFace buffalo_l."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

# Minimum InsightFace detection confidence to count a face.
CONFIDENCE_THRESHOLD: float = 0.5

# InsightFace gender codes.
_GENDER_FEMALE: int = 0
_GENDER_MALE: int = 1


@dataclass
class FaceDetection:
    gender: str          # "female" or "male"
    score: float         # detection confidence (0–1)
    bbox: list[float]    # [x1, y1, x2, y2] in pixel coordinates


def load_model() -> Any:
    """
    Load the InsightFace FaceAnalysis model.

    Uses buffalo_l which includes the genderage sub-model — buffalo_sc lacks
    gender estimation entirely (face.gender is always None with that pack).
    Downloads model weights on first run (cached in ~/.insightface).
    Uses CPU only — no CUDA required.
    """
    from insightface.app import FaceAnalysis  # type: ignore

    model = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    model.prepare(ctx_id=0, det_size=(640, 640))
    return model


def detect_faces(
    model: Any,
    frame_path: Path,
    blur_women: bool = True,
    blur_men: bool = False,
) -> tuple[bool, list[FaceDetection]]:
    """
    Run InsightFace on one frame.

    Returns:
        should_blur  – True if at least one face matches the blur policy.
        detections   – All faces found above the confidence threshold.
    """
    img = cv2.imread(str(frame_path))
    if img is None:
        return False, []

    faces = model.get(img)
    detections: list[FaceDetection] = []
    should_blur = False

    for face in faces:
        if float(face.det_score) < CONFIDENCE_THRESHOLD:
            continue

        if face.gender is None:
            continue  # model couldn't determine gender for this face

        gender_code = int(face.gender)
        gender_str = "female" if gender_code == _GENDER_FEMALE else "male"
        det = FaceDetection(
            gender=gender_str,
            score=float(face.det_score),
            bbox=face.bbox.tolist(),
        )
        detections.append(det)

        if (gender_code == _GENDER_FEMALE and blur_women) or (gender_code == _GENDER_MALE and blur_men):
            should_blur = True

    return should_blur, detections
