# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running Safi

```powershell
# Activate virtual environment (Windows)
.venv\Scripts\activate

# Run the pipeline on a YouTube URL
python safi.py "https://youtube.com/watch?v=VIDEO_ID"
```

## Debug scripts

```powershell
# Inspect InsightFace detection on a single frame
python debug_frame.py tmp/<video_id>/frames/frame_000042.jpg

# Inspect NudeNet detection on a single frame (prints all classes, threshold status, saves annotated image)
python debug_sexual.py tmp/<video_id>/frames/frame_000042.jpg
```

## Architecture

The pipeline runs as six sequential steps driven by `safi.py`:

```
safi.py  →  steps/downloader.py  →  steps/audio.py  →  steps/frames.py
         →  steps/detect_gender.py + steps/detect_sexual.py (models loaded once)
         →  steps/analyze.py  →  steps/annotations.py  →  steps/encoder.py
```

**Two-stage sequential filter** (`steps/analyze.py`):
- Stage 1: InsightFace buffalo_l — detects female faces. If flagged, Stage 2 is **skipped** (whole frame will be blurred anyway; NudeNet would be wasted compute).
- Stage 2: NudeNet v3 — runs only on frames Stage 1 let through.

Frame index = second in video (1 fps extraction), so `frame_000042.jpg` → second 42.

**Key model notes:**
- InsightFace: must use `buffalo_l`, not `buffalo_sc`. The `sc` variant has no `genderage.onnx`, so `face.gender` is always `None`.
- `face.gender == 0` = female, `1` = male.
- Demucs is invoked via `sys.executable -m demucs` (not `"python"`), to stay inside the venv on Windows. The `--mp3` flag is required to avoid a torchaudio ≥ 2.5 `torchcodec` bug.
- NudeNet **cannot detect content that is already blurred in the source video** — this is a fundamental limitation.

**ffmpeg blur** (`steps/encoder.py`):
- Uses `-vf boxblur=lr=10:lp=10:enable='...'` — fully opaque blur.
- Consecutive flagged seconds are merged into ranges by `_merge_ranges()` to avoid the "expression too long" ffmpeg error.
- When no seconds are flagged, passes through `0:v:0` directly (no filter).

## Key constants (all tunable at the top of their module)

| Constant | File | Default |
|---|---|---|
| `BLUR_WOMEN`, `BLUR_MEN` | `safi.py` | `True`, `False` |
| `DEMUCS_MODEL` | `steps/audio.py` | `htdemucs` |
| `FPS` | `steps/frames.py` | `1` |
| `CONFIDENCE_THRESHOLD` | `steps/detect_gender.py` | `0.5` |
| `SCORE_THRESHOLD` | `steps/detect_sexual.py` | `0.45` |
| `BLUR_CLASSES` | `steps/detect_sexual.py` | 11 NudeNet class labels |
| `BLUR_LR`, `BLUR_LP` | `steps/encoder.py` | `10`, `10` |

## Outputs

| Path | Contents |
|---|---|
| `output/safi_<id>_clean.mp4` | Music removed + women + sexual blur |
| `output/safi_<id>_sexual_only.mp4` | Music removed + sexual blur only (NudeNet evaluation) |
| `tmp/<id>/annotations.json` | Every flagged second with bounding boxes |
| `tmp/<id>/frames/` | One JPEG per second of source video |

`tmp/` is preserved intentionally for inspection and re-runs with `--no-overwrites`.
