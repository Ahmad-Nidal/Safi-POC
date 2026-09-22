# Safi — Final Review

**Date:** 2026-09-23
**Scope:** video processing only (auth, APIs and product features are out of scope).
**Reviewed:**

1. The Safi POC (this repo, commit `9c01c8a`).
2. [Naqi](https://github.com/haithamassoli/NaqiHalalVideoFilter), an Android app that solves the same problem on-device (commit `26e9119`).
3. The earlier plan, [old fable refactor plan.md](old%20fable%20refactor%20plan.md).

Numbers marked *measured* come from benchmarks run for this review (method in the [Appendix](#appendix--benchmark-method)). Numbers marked *estimated* come from adding up component timings, not from a full pipeline run.

---

## Summary

- **Two lines of code cause most of the slowness, and neither is where the README says.**
  - Rendering is slow because of the 10-pass `boxblur`, not the x264 re-encode.
  - Analysis is slow because InsightFace runs 5 models on every face when 2 are needed.
  - Fixing both takes a 1:40 video from about 6 min to about 1 min on the same CPU (*estimated*).
- **The code structure is good.** It needs targeted refactors, not a rewrite. The most important one is to store raw detections first and decide what to blur in a separate step.
- **The bigger production risk is leaks, not speed.**
  - Sampling at 1 fps with no padding lets content through between samples.
  - Only faces are detected.
  - Singing survives music removal.
  - An unreadable frame passes unblurred.
- **Licensing blocks a commercial release.** NudeNet 3.4.2 ships AGPL-3.0 licence files, and the InsightFace buffalo_l weights are for non-commercial research only.
- **Naqi is a strong reference design.** Its edit decision list (EDL), face tracking with a vote per track, music gate and padded intervals are worth adopting. Its face-only detection gaps and heavy comment style are not.
- **The old refactor plan is well structured but needs revising before use.**
  - It misses both measured bottlenecks.
  - Item 2b would let unblurred content through.
  - Its GPU step for NudeNet would stay on CPU without any error.

---

## 1. Safi POC review

### 1.1 Where the time goes (*measured*, Ryzen 5 9600X, CPU only)

**Rendering: a 60 s 1080p30 clip at 4 Mbps with 35% of seconds blurred**

| Variant | Time |
|---|---:|
| POC: `boxblur=lr=10:lp=10` + x264 `medium` | **19.2 s** |
| Same blur, x264 `veryfast` | 17.0 s |
| Encoding only, no blur (`medium`) | 7.0 s |
| `boxblur=lr=40:lp=1` + `veryfast` | 6.0 s |
| Downscale → upscale → overlay blur + `veryfast` | **5.1 s** |
| Nothing flagged, `-c:v copy` | 0.3 s |
| `boxblur` 10×10 alone on every frame (decode + filter, no encode) | **40.1 s** (slower than real time) |

Blur cost grows with the number of flagged seconds times the pixels per frame. At 4K it is about 4× the 1080p figure, which explains the ~2.5 min renders in the README. The downscale blur was equally opaque in a side-by-side check.

**Analysis: one 1080p frame with 6 faces**

| Step | ms/frame |
|---|---:|
| POC: `FaceAnalysis("buffalo_l")`, all 5 models, including `imread` | **764** |
| Detection + genderage only (`allowed_modules`) | **74** (same genders) |
| Detection only | 33 |
| NudeNet 320n, from a file path / from an in-memory array | 17 / 14 |
| JPEG decode of a 1080p frame | 4.4 |

`FaceAnalysis.get()` runs every loaded model on every face. That includes two landmark models and ArcFace R50 recognition, none of which the pipeline uses. Together they add about 115 ms per face.

### 1.2 Performance recommendations, in order of value

1. **Load only detection and genderage.** In [detect_gender.py:36](steps/detect_gender.py#L36), use `FaceAnalysis(name="buffalo_l", allowed_modules=["detection", "genderage"], ...)`. Analysis gets about 5–10× faster.
2. **Replace the blur filter** at [encoder.py:37](steps/encoder.py#L37) with `split → scale=iw/24:-2 → scale back → overlay=enable='…'`. Scale back to the **exact** source size, read with ffprobe: an overlay that is even slightly smaller leaves an unblurred strip at the edge. Rendering gets about 4× faster.
3. **Stream-copy when nothing is flagged.** [encoder.py:57-66](steps/encoder.py#L57-L66) still re-encodes with libx264 in that case.
4. **Cap the source resolution and codec** at [downloader.py:32](steps/downloader.py#L32): prefer `bv*[height<=1080][vcodec^=avc1]+ba`, and cap the fallback too. Today `bestvideo[ext=mp4]` can select 4K AV1.
5. **Run Demucs alongside the video steps.** Start it at the same time as frame extraction, analysis and a video-only render, then mux the audio at the end. After fixes 1–2, Demucs (21–35 s) becomes the slowest step. On CPU, split threads between the two branches or they compete for cores.
6. **Later:**
   - GPU: ONNX Runtime CUDA plus `demucs -d cuda`.
   - Decode frames into memory (ffmpeg pipe or PyAV) instead of writing JPEGs.
   - `--overlap 0.1` for Demucs, about 15–20% faster.
   - A music gate before Demucs (see §2).

### 1.3 Code quality

The structure is good: small step modules, dataclasses and clear names. Before building further:

1. **Store detections, then decide.**
   - Analysis should record every sampled frame's raw detections: all faces with gender and score, all NudeNet classes with score.
   - A separate policy step turns those into blur segments (thresholds, classes, padding).
   - Today thresholds and policy are mixed into the detectors ([detect_gender.py:78](steps/detect_gender.py#L78)), and only flagged frames are saved. Changing a threshold means re-running inference, and no evaluation set can be built.
2. **Remove the Stage 1 → Stage 2 skip** in [analyze.py:50-59](steps/analyze.py#L50-L59) once blur moves to regions. It already makes the sexual-content annotations incomplete, and NudeNet costs only 14 ms.
3. **Pass settings and errors explicitly.**
   - Replace the module constants spread across 6 files with one config object.
   - Stop hardcoding model names a second time in [annotations.py:52-56](steps/annotations.py#L52-L56).
   - In library code, raise exceptions instead of calling `sys.exit` ([downloader.py:44](steps/downloader.py#L44)), and log instead of printing.
4. **Make caching consistent.**
   - Today `audio.wav` is reused, Demucs always re-runs, and frames are always re-extracted.
   - `--no-overwrites` silently reuses a stale video.
   - Each step should be idempotent, with its cache keyed on its inputs and settings.

### 1.4 Bugs

| Where | Bug | Effect |
|---|---|---|
| [detect_sexual.py:40-48](steps/detect_sexual.py#L40-L48) | NudeNet v3 always returns `[x, y, w, h]` (checked in the installed source). The `w > x and h > y` heuristic treats many boxes as `[x1, y1, x2, y2]`. | Annotation boxes are wrong, which would break region blur. `[50,50,100,100]` should become `[50,50,150,150]`. |
| [detect_gender.py:55-56](steps/detect_gender.py#L55-L56) | An unreadable frame returns "no faces". | The frame goes out unblurred without any check. |
| [encoder.py:57-66](steps/encoder.py#L57-L66) | Nothing flagged still triggers a full re-encode. | Wasted time; no output error. |

### 1.5 Production readiness (video processing)

**Output correctness comes first, because one leak is a product failure.**

- **Gaps between samples.** At 1 fps, anything shorter than about 1 s can be missed.
  - A flagged second is blurred exactly `[N, N+1)`, so content leaks at the start and end of a scene.
  - A single missed detection makes the blur flicker on and off.
  - Fix: pad the blur ranges, fill short gaps, and sample faster; 2–4 fps is affordable after fix 1.
- **Only faces are detected.**
  - Women seen from behind, far away, or with faces under about 60 px (after the 640 px detector resize) are not caught.
  - InsightFace gives gender as a hard 0/1 with no confidence, so it can't be tuned.
  - A person detector with a body-level classifier is likely needed. Also test NudeNet's `640m` model.
- **Singing survives.** The Demucs vocals stem keeps singing voices, so songs stay in the output. Singing-vs-speech detection is needed.
- **No evaluation set.** Build a labelled video set with metrics per category that prioritise recall, plus regression tests on reference ("golden") videos. Without it, thresholds can't be tuned responsibly.

**Licensing blocks a commercial release.**

- **NudeNet 3.4.2 ships AGPL-3.0 licence files.** Its package metadata says MIT, but the `LICENSE` and `LICENSE.md` files in the installed wheel are AGPL-3.0.
- **The InsightFace buffalo_l weights are for non-commercial research only.**
- Settle both before investing further in these models. Naqi dropped NudeNet for this reason.

**Robustness**

- Handle videos with no audio track, variable frame rate, rotation metadata, and a non-zero `start_time` (audio drift).
- Add `-pix_fmt yuv420p`, or 10-bit/HDR sources produce High10 H.264 that many devices can't play. Add `-movflags +faststart`.
- Watch disk use on long videos: a full-length WAV plus one JPEG per second.
- Retry and classify yt-dlp failures.

**Reproducibility and operations**

- Pin `requirements.txt`.
- Pin an ffmpeg build that includes libx264. The Fedora `ffmpeg-free` build has none, so the render step fails on that machine as written.
- Bake model weights into the image instead of downloading them at run time.
- Emit metrics for each step, and define a policy for cleaning up `tmp/`.

### 1.6 Doc drift

- There is no `sexual_only.mp4` and no second render. The output is `safi_<id>.mp4`, not `_clean.mp4`.
- The README says "partial-opacity blur", which is wrong, and it says rendering is slow because of the re-encode, which the benchmark disproves.
- CLAUDE.md lists `debug_frame.py` and `debug_sexual.py`, which don't exist.
- CLAUDE.md says `frame_000042.jpg` is second 42. It is second 41 (see [frames.py:15](steps/frames.py#L15)).

---

## 2. Naqi review (reference app)

**What it is:** an Android app in Kotlin, GPL-3.0, arm64 only. It does music removal plus face and NSFW censoring **entirely on the phone**:

- htdemucs (fp16 ONNX) for music removal
- a YAMNet classifier as a music gate
- ML Kit to detect and track faces
- InsightFace `genderage` for a per-track gender vote
- a MobileNetV2 NSFW scene classifier
- a Media3 GPU shader and the hardware encoder for rendering

It has about 8.2k lines of Kotlin code, 16 unit-test files, and 22 planning docs. It was reviewed by reading the source and docs; it was not built or run.

**Performance, from the author's measurements on a Galaxy S23:** a 155-minute film takes about 3.1 h in combined mode (analysis 70.5 min, render about 10 min, music separation is the long pole).

### 2.1 Strengths

- **Two passes with an edit decision list (EDL).** Pass 1 writes the EDL: whole-frame censor intervals plus face tracks with keyframed boxes. Pass 2 renders from the EDL. This is the §1.3 "detect → decide → render" split.
- **A gender vote per face track instead of per frame.**
  - At most 5 votes per track, only on crops of at least 80 px (a floor they measured).
  - When unsure it censors: no votes, or a tie, means the face is censored.
  - Cost is per track, not per frame.
- **Blur timing is handled.**
  - Faces are sampled at 10 fps (±50 ms padding).
  - NSFW scenes are sampled at 5 fps (−500 / +1500 ms padding).
  - Spans closer than 400 ms merge so the blur doesn't strobe.
  - More than 8 faces at once switches to whole-frame censoring.
  - A blur setting that would do nothing is raised to a minimum.
- **Rendering is cheap.**
  - GPU Gaussian blur on a downscaled buffer, with edges feathered only outward.
  - Hardware H.264 encoding.
  - A container copy when there is nothing to censor, and an audio-only remux for music-only jobs.
- **Demucs only runs where there is music.** YAMNet checks each 2.6 s chunk and leans towards saying "music". Chunks without music skip Demucs, with ±2 chunks of margin. Overlap-add crossfades between separated and skipped chunks. Audio runs in parallel with video.
- **Long videos are handled.** Memory stays bounded by streaming, work is checkpointed per segment and resumes after the app is killed, and free disk space is checked first. Model downloads are SHA-256 verified.
- **The README is honest** about accuracy (about 92% on gender) and about singing surviving.

### 2.2 Problems

1. **Small faces are never detected.** ML Kit uses its default `minFaceSize` of 0.1 on frames scaled to 640 px ([FaceTracker.kt:203-207](https://github.com/haithamassoli/NaqiHalalVideoFilter/blob/main/app/src/main/java/com/haithamassoli/naqi/analysis/FaceTracker.kt#L203-L207)).
   - Heads narrower than 10% of the frame width, about 170 px on their test film, are ignored.
   - An undetected face creates no track, so wide shots stay uncensored in every mode, including "everyone" and whole-frame.
   - This was parked as a quality item (`perf-plan-v4.md:279`). It is the biggest source of leaks.
2. **Only faces are detected.** Region mode covers the face plus 25%, so hair and body stay visible. Women seen from behind aren't detected. The NSFW check is a coarse 224 px scene classifier.
3. **Singing survives, and a code comment contradicts that.** [MusicGate.kt:149-151](https://github.com/haithamassoli/NaqiHalalVideoFilter/blob/main/app/src/main/java/com/haithamassoli/naqi/audio/MusicGate.kt#L149-L151) says singing "must be removed". In practice the gate only decides whether Demucs runs, and the vocals stem keeps singing.
4. **Licensing is unresolved.**
   - The NSFW model is marked NOASSERTION upstream.
   - `NOTICE` says the InsightFace non-commercial restriction was "waived by the owner", but the source reads as the app author accepting the risk.
   - The app is GPL-3.0 yet bundles proprietary ML Kit.
5. **Hard to maintain.**
   - Core files are 40–55% comments. Many tell the history and cite planning docs by section number ("plan-v2 §5.4"), which will go stale.
   - `FilterWorker.kt` is 1,443 lines handling 5 job types.
6. **Tests aren't automated.** Unit tests cover the pure logic well, but there's no CI, lint has known errors, and there are no end-to-end tests on real videos.
7. **Slow on a phone.** Android caps this kind of background processing at 6 h per 24 h per app. A mid-range phone at about 2× slower could hit that cap on one film.

### 2.3 What Safi should adopt or avoid

| Topic | Safi today | Adopt from Naqi |
|---|---|---|
| Analysis output | Only flagged seconds | EDL of intervals plus tracked face boxes, consumed by the renderer |
| Gender decision | Every face, every frame | Track faces, vote ≤5 times per track, censor when unsure |
| Sampling | 1 fps, blur exactly `[N, N+1)` | Faces 10 fps, NSFW 5 fps, padding before and after, merge nearby spans |
| Audio | Demucs on the whole track | Music gate first; skip chunks without music; run in parallel with video |
| Nothing flagged | Full re-encode | Copy the video stream |
| Models | NudeNet (AGPL) + buffalo_l (non-commercial) | Choose models with clear licences before scaling up |

**Avoid:** face-only detection as the sole trigger, history-style comments that cite doc sections, and claiming singing is removed.

**Where Safi can do better:** running on a server allows a person detector and body-level classification, which close gaps 1–2, and a GPU turns a 3-hour film into minutes. The trade-off: yt-dlp from server IPs gets blocked and raises terms-of-service questions, while Naqi avoids that by downloading on the user's device.

---

## 3. Review of the old refactor plan

The plan is well organised and its phasing is sensible. Its cleanup items are accurate: librosa is unused, and numpy is unused in `detect_gender.py`. It needs these changes:

### 3.1 It misses both measured bottlenecks

| Plan item | Measured effect | Missing fix | Measured effect |
|---|---|---|---|
| 1b: x264 `veryfast` | Render 19.2 → 17.0 s (−11%) | Replace the `boxblur` filter | Render 19.2 → **5.1 s** |
| 2a: decode each frame once | Saves ~4 ms of 764 ms per frame (<1%) | InsightFace `allowed_modules` | **764 → 74 ms/frame** |

### 3.2 Item-level issues

| Item | Issue | Fix |
|---|---|---|
| **2b** skip near-duplicate frames | **Lets unblurred content through.** Average difference on a 64×64 thumbnail can't see a small face or a person entering at the edge, so the old "clean" result gets reused. After the `allowed_modules` fix it saves almost nothing. | Drop it. For cheaper analysis at higher frame rates, track faces instead (§2). |
| **4** NudeNet GPU | The installed nudenet 3.4.2 **ignores `providers`** (that line is commented out), so the plan's "fall back if not accepted" check passes while NudeNet stays on CPU. | Create the ORT session yourself over `320n.onnx`. Verify with `session.get_providers()`. |
| **4** onnxruntime-gpu | nudenet and insightface both depend on `onnxruntime`, which installs the same Python module as `onnxruntime-gpu`. | Document `pip uninstall onnxruntime` after installing the GPU package. Decide on licensing before this phase. |
| **3c** checkpoint | Keyed only on `blur_women`/`blur_men`/frame count. A changed threshold, class list, FPS or model silently reuses stale flags. | Store raw detections keyed on model and sampling settings, and apply policy afterwards. Handle a half-written last line after a crash. |
| **3a** errors blur the frame | A model broken on every frame (e.g. a bad CUDA setup) "succeeds" with a fully blurred video. | Fail the job above an error-rate threshold. |
| **3b** smoothing | Applied inside the encoder, so `annotations.json` doesn't match what was blurred. Integer seconds only. | Make it its own step and record the final ranges. Use float seconds. |
| **2c** Demucs in parallel | On CPU, Demucs and ORT each try to use every core. `capture_output` holds a long log in memory. | Split thread counts. Write the log to `tmp/<id>/demucs.log`. |
| **1c** resolution cap | `[ext=mp4]` can still pick AV1, which is slow to decode. | Prefer `[vcodec^=avc1]` and cap the fallback. |
| **1f** doc drift | Misses the frame-index off-by-one and the "rendering is slow because of the re-encode" claim. | Add both. |
| Phase 1 checkpoint | "Run the unit-testable pieces mentally". The `_to_xyxy` fix ships before any tests exist. | Move the `_to_xyxy` and range tests into Phase 1. |
| Verification step 2 | Says Demucs reuses the `tmp/` cache. Only `audio.wav` is cached; Demucs re-runs every time. | Correct the step, or add a Demucs cache. |

### 3.3 Missing from the plan

- **A no-regression check on blurred seconds.** Every speed optimisation must produce a superset of the previously blurred seconds on the same videos. The bbox fix is the only intended change. This check would have caught 2b.
- `-pix_fmt yuv420p` and `-movflags +faststart`.
- The licensing decision on NudeNet and buffalo_l.
- A higher sampling rate once analysis is cheap.

---

## 4. Suggested implementation plan

Each phase is shippable on its own. Acceptance checks are listed under each phase.

### Phase 0: safety net (do first, small)

- [ ] Add a `tests/` folder with pytest tests for `_merge_ranges`, `_build_blur_filter`, `_to_xyxy` and `extract_video_id`.
- [ ] Add a blurred-set diff script: given two `annotations.json` files, it lists seconds that were blurred before and are not blurred now.
- [ ] Record a baseline: timings plus `annotations.json` for 3 reference videos (talking head, crowd, music video).

**Accept when:** tests pass, and the baseline is saved.

### Phase 1: quick wins

- [ ] InsightFace `allowed_modules=["detection", "genderage"]`.
- [ ] Replace `boxblur` with the downscale/overlay blur, scaled back to the exact source size.
- [ ] `-c:v copy` when nothing is flagged.
- [ ] Always add `-pix_fmt yuv420p` and `-movflags +faststart`.
- [ ] Cap the resolution at 1080p and prefer avc1.
- [ ] Fix `_to_xyxy`; always convert xywh.
- [ ] Replace `sys.exit` in `download()` with raised exceptions; remove librosa and the unused numpy import.
- [ ] Fix the doc drift in §1.6.

**Accept when:**
- Analysis is at least 5× faster and rendering at least 3× faster on the baseline videos.
- The blurred-set diff is empty.
- `annotations.json` boxes satisfy `x2 > x1` and `y2 > y1`.

### Phase 2: no leaks, and robustness

- [ ] Unreadable frames and model errors blur that second; fail the job above an error-rate threshold.
- [ ] A policy step after analysis: pad ±1 s, fill gaps ≤ 2 s, float seconds. `annotations.json` records the final blurred ranges.
- [ ] Run Demucs in parallel with the video branch, with split thread counts and a log file.
- [ ] Pin Python dependencies; document the required ffmpeg build (with libx264).
- [ ] Handle videos with no audio track.

**Accept when:**
- The blurred-set diff shows only additions.
- A frame deliberately corrupted in a test blurs its second.
- Total wall time is close to max(Demucs, video branch).

### Decision gate: models and evaluation

- [ ] Decide the licensing: replace NudeNet (AGPL-3.0) and the buffalo_l weights (non-commercial), or obtain commercial licences.
- [ ] Build a labelled evaluation set (at least ~50 clips covering the categories in §1.5) and measure recall per category.

### Phase 3: architecture and scale

- [ ] Store raw detections for every sampled frame, then produce an EDL. Checkpoint the raw detections, keyed on model and sampling settings.
- [ ] Raise sampling to 2–4 fps. Add face tracking with a gender vote per track (Naqi pattern).
- [ ] A music gate (YAMNet or PANNs) before Demucs, with a margin of ±1–2 chunks.
- [ ] GPU: explicit ORT sessions with `get_providers()` asserted, and `demucs -d cuda`.
- [ ] Next quality steps: a person or body detector for faces that are too small or turned away, singing detection, and region blur from the EDL.

**Accept when:**
- Recall on the evaluation set is at least the Phase 2 recall.
- On GPU, a 10-minute video processes in under 2 minutes.

---

## Appendix — benchmark method

- **Machine:** AMD Ryzen 5 9600X (6 cores / 12 threads), Linux, CPU only.
- **ffmpeg:** static 7.0.2 with libx264, from `imageio-ffmpeg`. The system Fedora ffmpeg 8.1.2 has no libx264.
- **Render clip:** synthetic `testsrc2` plus light temporal noise, 1920×1080 at 30 fps, 60 s, H.264 at about 4 Mbps (close to YouTube's 1080p bitrate). Blurred ranges were 5–15, 25–30, 40–43 and 50–53 s (21 of 60 s). Each run used `-crf 23` and AAC at 128k.
- **Analysis frame:** InsightFace's bundled 6-face `t1.jpg`, letterboxed into a 1920×1080 frame.
  - Each measurement is the mean of 15 runs after a warm-up.
  - Library versions: insightface 1.0.1, nudenet 3.4.2 (320n), onnxruntime 1.27 on the CPU execution provider.
  - The full and slim (detection + genderage) configurations found the same 6 faces with the same genders.
- **Not measured:** the end-to-end pipeline after the fixes. The "about 6 min → about 1 min" figure is summed from component timings.
