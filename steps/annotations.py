"""Persist analysis results to a structured JSON file."""

import json
from pathlib import Path

from steps.analyze import FrameResult


def save_annotations(
    tmp_dir: Path,
    video_id: str,
    title: str,
    duration: float,
    results: list[FrameResult],
    settings: dict,
) -> Path:
    """
    Write tmp/<id>/annotations.json describing every flagged second.

    Returns the path of the written file.
    """
    women_ranges = []
    sexual_ranges = []

    for r in results:
        if r.flagged_women:
            women_ranges.append({
                "time": r.time_sec,
                "detections": [
                    {"gender": d.gender, "score": round(d.score, 4), "bbox": [round(v, 1) for v in d.bbox]}
                    for d in r.women_detections
                ],
            })
        if r.flagged_sexual:
            sexual_ranges.append({
                "time": r.time_sec,
                "detections": [
                    {"class": d.cls, "score": round(d.score, 4), "bbox": [round(v, 1) for v in d.bbox]}
                    for d in r.sexual_detections
                ],
            })

    payload = {
        "video_id": video_id,
        "title": title,
        "duration_sec": int(duration),
        "blur_ranges": {
            "women": women_ranges,
            "sexual": sexual_ranges,
        },
        "settings": settings,
        "model_versions": {
            "audio": "htdemucs",
            "women": "insightface-buffalo_l",
            "sexual": "nudenet-v3",
        },
    }

    out_path = tmp_dir / "annotations.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)

    return out_path
