# Safi — POC

> **This is a proof-of-concept built with AI assistance** (under SDE supervision and guidance, without exhaustive manual review of every output). The goal is to validate that the idea is technically feasible and see what the cleaned result looks like — not to ship production-ready code.

Process a YouTube video to make it suitable for a Muslim audience:
- **Music removed** — Demucs extracts the vocals-only stem; instrumentals are discarded.
- **Women blurred** — InsightFace detects female faces; every flagged second gets a whole-frame blur.
- **Sexual content blurred** — NudeNet v3 catches any exposed or suggestively-covered private area.

> **Note on blur scope:** In this POC the *entire frame* is blurred (fully opaque) whenever a flag is triggered. A future real product would blur only the specific detected region.

---

## Prerequisites

- Python 3.10+
- **ffmpeg** on your `PATH` (used for audio extraction, frame extraction, and encoding)
  - Windows: `winget install ffmpeg` or download from https://ffmpeg.org
  - Linux/macOS: `sudo apt install ffmpeg` / `brew install ffmpeg`

---

## Local setup

```bash
git clone <this-repo>
cd safi-poc

# Create and activate a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Run
python safi.py "https://youtube.com/watch?v=VIDEO_ID"
```

**Note:** InsightFace downloads ~500 MB of model weights to `~/.insightface/` on the first run. NudeNet also downloads its own weights automatically. Both are cached for subsequent runs.

---

## Google Colab setup

Paste this into a Colab cell to install everything:

```python
# System dependency
!apt-get install -y ffmpeg

# Python packages
!pip install yt-dlp demucs librosa numpy nudenet insightface onnxruntime opencv-python

# Clone the repo (or upload safi.py + steps/ manually)
!git clone <this-repo>
%cd safi-poc
```

Then run in a second cell:

```python
!python safi.py "https://youtube.com/watch?v=VIDEO_ID"
```

---

## Performance expectations

**Your CPU may run at 100% throughout the entire pipeline.**

> **Technical limitation:** This POC runs on CPU only. GPU acceleration is not wired up in the current implementation. Demucs, InsightFace, and NudeNet all support CUDA — GPU support is a straightforward next step for a real product.

Measured on a **1-minute video** with a high-end CPU:

| Step                                   | Time         | Share |
| -------------------------------------- | ------------ | ----- |
| Download                               | 3.6 s        | 1%    |
| Music removal (Demucs)                 | 21 s         | 8%    |
| Frame extraction                       | 0.7 s        | —     |
| Model loading                          | 2.1 s        | 1%    |
| Frame analysis (InsightFace + NudeNet) | 1 m 20 s     | 30%   |
| Rendering (ffmpeg)                     | 2 m 39 s     | 59%   |
| **Total**                              | **4 m 28 s** |       |

On another video with **1:40-min**:
| Step                                   | Time         | Share |
| -------------------------------------- | ------------ | ----- |
| Download                               | 3.1 s        | 1%    |
| Music removal (Demucs)                 | 35 s         | 10%   |
| Frame extraction                       | 2.0 s        | 1%    |
| Model loading                          | 2.2 s        | 1%    |
| Frame analysis (InsightFace + NudeNet) | 2 m 37 s     | 44%   |
| Rendering (ffmpeg)                     | 2 m 36 s     | 44%   |
| **Total**                              | **5 m 56 s** |       |

Rendering dominates because ffmpeg re-encodes the full video with the partial-opacity blur filter. Longer videos scale roughly linearly.

---

## Output files

| File | Contents |
|------|----------|
| `output/safi_<id>_clean.mp4` | Music removed + women blurred + sexual content blurred |
| `output/safi_<id>_sexual_only.mp4` | Music removed + only sexual content blurred (for evaluating NudeNet in isolation) |
| `tmp/<id>/annotations.json` | Full JSON record of every flagged second and its detections |
| `tmp/<id>/frames/` | One JPEG per second of the original video |

`tmp/` is intentionally preserved for inspection — delete it manually when done.

---

## How it works

```
YouTube URL
    │
    ▼
[1] yt-dlp          → best-quality MP4
    │
    ▼
[2] Demucs          → htdemucs --two-stems vocals → vocals.mp3 (music gone)
    │
    ▼
[3] ffmpeg          → 1 JPEG per second
    │
    ▼
[4] For each frame:
    │
    ├─ Stage 1: InsightFace buffalo_l
    │       female face found + blur_women ON?  → flag second, skip Stage 2
    │
    └─ Stage 2: NudeNet v3  (only if Stage 1 didn't flag)
            explicit class ≥ 0.45?  → flag second
    │
    ▼
[5] annotations.json  (flagged seconds + bounding boxes)
    │
    ▼
[6] ffmpeg render ×2:
    clean.mp4         original video + vocals.mp3 + blur on (women ∪ sexual) seconds
    sexual_only.mp4   original video + vocals.mp3 + blur on sexual seconds only
```

### Music removal

Music separation is based on [Demucs](https://github.com/facebookresearch/demucs) (`htdemucs` model, `--two-stems vocals`). The approach was informed by studying the [NoMusic](https://github.com/IbraheemTuffaha/nomusic) project, which tackles the same problem and provided useful implementation reference.

---

## Configuration

All tunable values live at the top of their respective modules:

| Constant | File | Default | Purpose |
|----------|------|---------|---------|
| `BLUR_WOMEN` | `safi.py` | `True` | Blur frames with female faces |
| `BLUR_MEN` | `safi.py` | `False` | Blur frames with male faces |
| `DEMUCS_MODEL` | `steps/audio.py` | `htdemucs` | Demucs model name |
| `FPS` | `steps/frames.py` | `1` | Frames extracted per second |
| `CONFIDENCE_THRESHOLD` | `steps/detect_gender.py` | `0.5` | InsightFace minimum face score |
| `SCORE_THRESHOLD` | `steps/detect_sexual.py` | `0.45` | NudeNet minimum detection score |
| `BLUR_CLASSES` | `steps/detect_sexual.py` | (11 classes) | NudeNet classes that trigger blur |
| `BLUR_LR` / `BLUR_LP` | `steps/encoder.py` | `10` / `10` | ffmpeg boxblur radius / iterations |
