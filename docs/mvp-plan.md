# Safi MVP plan

> Draft for review. This turns the design discussion that followed the POC into a plan to go live with the MVP: the decisions to confirm or make, the research needed first, and the tasks for each phase.

**Goal:** launch SafiTube on the web and on mobile. A user replaces `youtube.com` with `safitube.com`, or shares from the YouTube app. They keep the default preset or pick another one. Then they watch a clean version rendered on our servers: music removed, and women and sexual content blurred. They can share open or locked links and download an MP4. The user's device only plays video.

**In the MVP:**
- URL swap, plus a box to paste links
- Share from the YouTube app
- Presets (Default / Strict / Kids) plus Custom
- Open and locked share links
- Our own thumbnails and link previews
- MP4 download (only if the lawyer and app stores allow it, see D9)
- Playback that starts before rendering finishes
- "Report a miss" button with human review
- Popular content processed before launch
- Free plan with limits

**Not in the MVP:** browser extension or filtering during playback, export for content owners, TensorRT speed-ups, and our own sexual-content model.

**Timeline:** about 6 months to launch. This assumes five people (founder/product, tech lead, ML engineer, web developer, mobile developer), plus an external lawyer, religious advisors and part-time labelers. After Gate 0 the tracks run in parallel. The analysis pipeline takes the longest, so it sets the launch date. Re-estimate at Gate 0.

## Phase 0: review, decide, research (weeks 1–4)

### Decisions

| # | Decision | Status |
|---|---|---|
| D1 | SafiTube web + mobile app; no extensions; nothing heavy on the device | Agreed |
| D2 | Render on the server (blur built into the video); analyze each video once and keep its filter track. See [Appendix A](#appendix-a-why-render-on-the-server-d2) | Recommended, to confirm |
| D3 | Video: blur people, not whole frames; follow each person through a scene; decide gender once per person; if unsure, blur | Agreed |
| D4 | Audio: separate dialogue, music and effects; mute singing (with a setting for nasheeds); keep effects | Agreed |
| D5 | Platform design: parallel analysis, rendering in order, delete unwatched renders after 30 days, processing popular videos ahead of time, free-plan limits, "when unsure, hide" | To review, using R5 |
| D6 | Trust: report a miss → human review → fix; a labeled test set; release only when recall targets are met | Agreed |
| D7 | Tech stack as proposed in [Appendix B](#appendix-b-proposed-tech-stack-d7) | To confirm, using R4 and R5 |
| D8 | Launch content: any YouTube video, or only Creative Commons videos and creators who opt in | Open, depends on R1 |
| D9 | MP4 download in the MVP | Open, depends on R1 and R2 |
| D10 | Launch web and mobile together, or web first | Open. Recommended: web first, then mobile once the app stores approve it |
| D11 | What each preset hides: all women or only uncovered women, men, how strict on music, nasheeds | Open, set with the advisors (R6) |
| D12 | Recall target for each category | Open, set after measuring current results on the test set |
| D13 | Free-plan limits: maximum video length, new videos per day | Open, from R5 |
| D14 | UI languages (e.g. Arabic + English) | Open, decide before design starts |

### Research and studies

| # | Study | Question it answers | Owner |
|---|---|---|---|
| R1 | Legal review | Can we stream edited YouTube videos and offer downloads, and in which countries? Is the safer path (Creative Commons, opt-in creators) enough? Is the SafiTube name safe? What terms of use and privacy policy do we need? | Lawyer + founder |
| R2 | App store check | [Apple's guideline 5.2.3](https://developer.apple.com/app-store/review/guidelines/) names YouTube: apps must not save, convert or download its media without permission. Can the app pass Apple and Google Play review? | Mobile developer + lawyer |
| R3 | Download test | Can our cloud servers fetch YouTube videos reliably at the expected volume? What do we do if they can't? | Tech lead |
| R4 | Model study | Test each proposed model on the test set, and confirm every license allows commercial use | ML engineer |
| R5 | Cost study | GPU minutes per minute of video, bandwidth per view, storage → cost per new video and per view | Tech lead + founder |
| R6 | Content policy | What each preset hides, and the labeling rules for the test set | Founder + religious advisors |
| R7 | User interviews | 10–15 parents and teachers on presets, locked links, sharing and downloads | Founder |

### Other Phase 0 tasks

- [ ] Label a test set of 100+ clips using R6's rules (labelers + ML engineer). Cover women seen from the front, back, far away and partly in frame, sexual content, music under speech, singing, and nasheeds.
- [ ] After Gate 0, write the dated plan for phases 1–6.

### Gate 0 (go / no-go)

- D8 and D9 decided with the lawyer
- A path through the app stores, or D10 set to web-only
- The download test passes
- Presets and labeling rules approved
- Test set labeled
- All models chosen and licensed for commercial use
- Cost per video and per view within budget

## Phase 1: foundations (weeks 5–6, tech lead)

- [ ] One repo for web, mobile, API and pipeline, with GitHub Actions, Docker and Terraform, and dev / staging / production environments
- [ ] Accounts: Cloudflare (R2, CDN, Workers), Temporal Cloud, Modal, managed PostgreSQL, Clerk, Sentry, Grafana. Register the safitube.com domain.
- [ ] Database tables: videos, jobs, filter tracks, presets, share links, users, reports
- [ ] FastAPI skeleton, with a TypeScript client generated from it
- [ ] Filter track format, with a version number

## Phase 2: analysis pipeline (weeks 5–14, ML engineer)

- [ ] Download the video and its details (duration, license), with length limits
- [ ] Detect scene changes (TransNetV2) and split the video at them
- [ ] Outline and follow each person (RT-DETR + SAM 2)
- [ ] Gender and clothing classifier (SigLIP): label data, train, calibrate. A vision-language model checks unclear people; if it's still unsure, blur.
- [ ] Sexual content through the moderation API
- [ ] Safety margins: fill short gaps, start 0.5 s early and end 0.5 s late, make masks slightly larger
- [ ] Audio: separate dialogue, music and effects; detect singing (YAMNet); one audio mix per preset
- [ ] Evaluation script that measures recall per category on the test set, run on every change

**Gate 2:** recall targets (D12) met.

## Phase 3: rendering and delivery (weeks 7–12, tech lead)

- [ ] Temporal workflow: download → analyze → render. The video ID is the job ID, so repeat requests join the running job. Retries and progress updates.
- [ ] GPU rendering: FFmpeg hardware decode/encode with the blur applied on the GPU. Output HLS pieces at 480p and 720p, rendered in order. The playlist grows as pieces finish, so playback starts early.
- [ ] R2 + CDN, with signed links checked by a Worker. The player only ever receives rendered pieces.
- [ ] MP4 download by joining the pieces (if D9 is yes)
- [ ] Keep filter tracks forever. Delete renders and source videos after 30 days without views, and re-render on request. After a fix, re-render only the affected pieces.
- [ ] Free-plan limits (D13)

**Gate 3:** a new 10-minute video works end to end, and time to first frame and cost per video are within R5's targets.

## Phase 4: web app (weeks 7–14, web developer)

- [ ] Pages: `/watch?v=ID`, `/shorts/ID`, the paste box, and `/s/<token>`
- [ ] Watch page: progress bar → playback (hls.js); preset picker (Default / Strict / Kids + Custom)
- [ ] Parent accounts (Clerk). Parents can create and cancel locked links. The locked page hides settings and the YouTube ID.
- [ ] Our own thumbnails and link previews
- [ ] Download button, and a "report a miss" button that records the time in the video
- [ ] UI languages (D14)

## Phase 5: mobile app (weeks 11–18, mobile developer)

- [ ] Expo app: watch, presets, share links, download to the device, report a miss
- [ ] Share from the YouTube app: share target on Android, Share Extension on iOS
- [ ] safitube.com links open directly in the app
- [ ] Submit to TestFlight and Google Play internal testing early, to find review problems before launch

## Phase 6: trust and launch (weeks 15–24, everyone)

- [ ] Review tool: report queue → fix the filter track → re-render → add the case to the test set
- [ ] Process launch content ahead of time: popular, kids' and educational channels, within D8's scope
- [ ] Monitoring and alerts: time to first frame, GPU-seconds per minute of video, cache hit rate, reports per hour watched
- [ ] Security check: locked links can't be bypassed, signed links work, rate limits are in place
- [ ] Load test at the expected launch traffic
- [ ] Closed beta with the interviewed families and teachers; fix the top issues

**Launch gate:**
- Recall targets still met
- Lawyer approves
- App store approval, or launch web-only
- Costs within budget
- Someone assigned to review reports every day

## Appendix A: why render on the server (D2)

Two ways to deliver a clean video on SafiTube, with no extra load on users' devices:

| | Filter during playback | Render on the server |
|---|---|---|
| Load on the device | Small but constant: draws the blur and keeps a second audio track in sync | None, it's a plain video |
| Where the video comes from | Either a YouTube embed or our own servers. YouTube's rules don't allow covering or changing its player's picture and sound, and its ads and suggestions stay unfiltered. Our own servers remove the storage saving | Our servers, through the CDN |
| Storage | Tiny, but only with the YouTube embed | About 1–1.5 GB per hour of video for each preset (480p + 720p), limited by deleting old renders |
| MP4 download | Needs a render anyway | Built in |
| Locked kid links | Weak: the device still receives the unblurred video | Strong: the blur is part of the video itself |
| Accuracy | The blur can lag behind fast movement | Exact on every frame |
| TV / Chromecast / AirPlay | Sends the unfiltered video | Works like any video |
| Changing settings | Instant | Needs a new render, then cached |
| Fixing a missed blur | Instant | Re-render only the affected pieces |

"Analyze once" still pays off. The expensive GPU analysis runs once per video and is saved as the filter track. New presets, fixes and deleted renders only need a re-render, which costs much less than a new analysis.

## Appendix B: proposed tech stack (D7)

| Layer | Choice | Why |
|---|---|---|
| Web | Next.js (TypeScript) + hls.js | Share pages built on the server, so link previews stay safe |
| Mobile | React Native (Expo) + react-native-video | Same language and API client as the web; native video players; share-from-YouTube support |
| API | Python + FastAPI | Same language as the ML code; it can generate the typed API client for web and mobile |
| Database | PostgreSQL | Videos, jobs, presets, share links, accounts |
| Pipeline | Temporal (managed service) | Multi-step jobs that survive crashes, with parallel parts, retries and progress. The video ID is the job ID, so 100 people opening the same new video share one job |
| GPU workers | PyTorch on L4-class GPUs; serverless (e.g. Modal) at first, Kubernetes later | Costs nothing when idle at the start; cheaper once traffic is steady |
| Video processing | FFmpeg with NVIDIA hardware decode/encode; blur applied on the GPU | Fast renders |
| Streaming | HLS in short pieces (CMAF), 480p + 720p | Plays on every device; each piece can be rendered, cached and fixed on its own |
| Storage + CDN | Cloudflare R2 + CDN, signed links via a Worker | No bandwidth (egress) fees in any region. Bandwidth is the main cost per view, and it's more expensive in regions where many of our viewers live |
| Login | Managed service (e.g. Clerk) | Parent accounts for locked links; watching needs no account |
| Operations | Docker, Terraform, GitHub Actions, Sentry, Grafana | Standard tools; track time to first frame, GPU-seconds per minute of video, and cache hit rate |

**Models:**
- Scene changes: TransNetV2
- People outlines and tracking: RT-DETR + SAM 2
- Gender and clothing: our own classifier built on SigLIP, with a self-hosted open vision-language model for unclear cases
- Sexual content: a moderation API first (e.g. AWS Rekognition), so we don't have to build a dataset of explicit images; our own model after the MVP
- Audio: a model that separates dialogue, music and effects, plus YAMNet to tell speech from singing

The named models are Apache- or MIT-licensed. Choose a vision-language model and audio separator that also allow commercial use. The POC's face model doesn't qualify: InsightFace's pretrained models, including `buffalo_l`, are [licensed for non-commercial research only](https://github.com/deepinsight/insightface/tree/master/python-package).
