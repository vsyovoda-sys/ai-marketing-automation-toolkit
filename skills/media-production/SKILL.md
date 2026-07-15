---
name: media-production
description: Run a rights-aware transcript, alignment, numbered timeline, human KEEP/CUT, captions, mechanical render, visual QA, and delivery loop for audio or video. Use for long-to-short editing, subtitles, interview clips, course clips, talking-head content, or podcast video. Prefer verifiable degraded outputs when codecs, fonts, models, or rendering are unavailable. Never auto-publish or let AI alone choose editorial cuts by default.
---

# Media Production

Turn media into reproducible edit decisions and verified deliverables. The default creative gate is a human-readable numbered timeline, not an opaque “AI highlight” cut.

## Hard gates

- Require rights for media, voice, likeness, music, fonts, and target use.
- Inspect codec, duration, frame rate, audio, subtitle language, fonts, and renderer before work.
- Preserve the original. Work from a copy and invalidate caches by input fingerprint; never delete old source files to fix a revision.
- A human selects KEEP/CUT and later watches/listens to the render.
- Do not claim a video is complete when only a command, timeline, or failed render exists.
- Never publish or upload automatically.

## Start the Loop

```bash
python3 scripts/loopctl.py init workflows/media-production.json \
  --workspace ./runs/media-001 \
  --input media_manifest=./inputs/media-manifest.json \
  --input edit_brief=./inputs/edit-brief.md
```

## Execute phases

1. `preflight`: verify rights and build a capability matrix with a defined fallback for every missing capability.
2. `transcript`: create aligned timestamps; check monotonicity, duration coverage, and low-confidence sections.
3. `numbered_timeline`: divide the source into stable numbered segments with verbatim text and confidence.
4. `keep_cut`: obtain human segment selection, order, and context review.
5. `render`: generate captions and, when capability exists, render reproducibly. Check timeline conservation, audio/video duration, and subtitle bounds.
6. `visual_review`: a human checks frames, audio, captions, black frames, crop, font, and sensitive content.
7. `delivery`: record actual artifacts, degraded outputs, rights, metadata review, and QA status.

Use `loopctl.py start/record/verify/complete`. Store render commands and tool versions in `render-log.json`.

## Degraded success is explicit

If rendering cannot run, a valid degraded delivery may be: numbered timeline + human edit decision + SRT + command preview. Mark the missing rendered media; never substitute an empty or unviewed file.

## Recovery rules

- ASR drift: change audio track/model or split the input; do not keep shifting timestamps by guesswork.
- Over-aggressive edit: return to human KEEP/CUT, not a more emotional prompt.
- Font/codec failure: use the declared fallback or produce the degraded pack.
- Revision: fingerprint the new input and invalidate only affected downstream stages.
- Visual QA failure: record exact timecodes, fix, rerender, and re-review.

## Required deliverables

`transcript.json`, `timeline.csv`, `edit-decision.json`, `captions.srt`, `render-log.json`, `visual-review.md`, and `delivery-manifest.json`.
