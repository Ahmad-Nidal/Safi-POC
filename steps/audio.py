"""Music removal via Demucs htdemucs, vocals-only stem — mirrors NoMusic's approach."""

import subprocess
import sys
from pathlib import Path

# Model selection — htdemucs is the Demucs v4 hybrid transformer default (not _ft).
DEMUCS_MODEL: str = "htdemucs"


def _extract_raw_audio(video_path: Path, tmp_dir: Path) -> Path:
    """Pull a 44 100 Hz PCM WAV out of the video for Demucs input."""
    wav_path = tmp_dir / "audio.wav"
    if wav_path.exists():
        return wav_path

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "44100",
        str(wav_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed:\n{result.stderr[-2000:]}")
    return wav_path


def remove_music(video_path: Path, tmp_dir: Path) -> Path:
    """
    Run Demucs with --two-stems vocals on the video's audio track.

    The vocals stem is the cleaned audio — music is gone, speech is preserved.
    Returns the path to vocals.wav produced by Demucs.
    """
    audio_path = _extract_raw_audio(video_path, tmp_dir)
    demucs_out_dir = tmp_dir / "demucs"

    cmd = [
        sys.executable, "-m", "demucs",
        "-n", DEMUCS_MODEL,
        "--two-stems", "vocals",
        "--mp3",            # use lameenc (avoids torchaudio/torchcodec save bug in torchaudio>=2.5)
        "--out", str(demucs_out_dir),
        str(audio_path),
    ]

    print(f"      Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)  # stream output so user sees progress
    if result.returncode != 0:
        raise RuntimeError("Demucs exited with a non-zero status. See output above.")

    # Demucs output layout: <out>/<model>/<track_stem>/vocals.mp3
    # Track stem = audio file name without extension → "audio"
    for ext in ("mp3", "wav", "flac"):
        expected = demucs_out_dir / DEMUCS_MODEL / "audio" / f"vocals.{ext}"
        if expected.exists():
            return expected

    # Fallback: search recursively for any vocals stem file
    for ext in ("mp3", "wav", "flac"):
        found = list(demucs_out_dir.rglob(f"vocals.{ext}"))
        if found:
            return found[0]

    raise RuntimeError(
        f"Demucs ran but no vocals stem was found under {demucs_out_dir}. "
        "Check the Demucs output above for errors."
    )
