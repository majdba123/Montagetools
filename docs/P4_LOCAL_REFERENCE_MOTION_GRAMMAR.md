# Local reference motion grammar

Inspected 2026-09-09 from `C:\Users\INTEL CENTER\Desktop\nnn`.
Originals were opened read-only. Size, modification time and SHA256 were
checked before and after sampling. No original was moved, renamed or encoded.

FFmpeg sampling: `fps=4,scale=320:180:flags=area`, RGB24 raw frames.
Occupancy: `255 - min(rgb) > 10`. Motion: maximum-channel absolute difference
between consecutive samples >13. Near-static: changed fraction <0.005.
Contact sheets cover each whole video plus quarter-second opening sequences.
Sampling timestamps below are evidence, never scheduler inputs.
FFprobe verified H.264 at 854x480 for all three files: `hallo 2.mp4` is
79.552 seconds at 25 fps; `انحياز 2.mp4` is 79.360 seconds at 30 fps;
`تأثير المتفرج2.mp4` is 72.960 seconds at 25 fps.

| File | SHA256 | Mean occupancy | Mean motion | Near-static samples |
|---|---|---:|---:|---:|
| hallo 2.mp4 | adef863155bd32fcbd06d98c5c2b88c9ee0e583b8077767a0b2c4272cfe8f17f | 32.3703% | 16.8891% | 7.5710% |
| انحياز 2.mp4 | 8d1f014258ba0a029ba9c1b8f270f682212d2ec8a997536655ff82bbba53300d | 33.3722% | 13.7318% | 22.7848% |
| تأثير المتفرج2.mp4 | 6d576b807d9bb81108f13aed7c09539f60df6a06b8358a0f6b1e5cfcc09af227 | 33.4358% | 16.3735% | 4.8110% |

The measured values supersede approximate remembered reference metrics for
these exact local bytes. All-frame metrics include titles, blank openings,
background transitions and text; they are not actor-only motion scores.

## Observed grammar

- **Reveal order:** establish the character or concept first; add related
  symbols, arrows and words while the focal remains. In `hallo`, the initial
  blue/red pair appears together as one explicit encounter; the later narrator
  joins an already visible character. Simultaneity is semantic, not universal.
- **Stagger/settle:** in the sampled openings, entries and opacity changes
  commonly occupy about 0.25–0.75 seconds; sequential labels/icons often begin
  roughly 0.5–1 second apart. These are visual estimates at 0.25-second precision.
- **Overlap/retention:** `hallo` retains the character through narrator entry
  around 6.75–7.75 seconds and the relationship/attribute additions through
  about 9 seconds. `انحياز` retains the character while the bulb, checks, arrow
  and label accumulate around 2.5–4.5 seconds. The third video retains the
  character while tickets, arrow and a second symbol build around 1–3.5 seconds.
- **Population:** these examples build from one focal to two or three substantial
  actors, plus annotations. Small marks are annotations, not invented actors.
- **Focus/hierarchy:** the incoming symbol becomes the next readable subject;
  the old focal remains context. Text can take foreground priority while the
  previous composition visibly recedes (third video around 7.5–8.25 seconds).
- **Rebuild:** a character moves from centered presentation into a side role
  when a relationship needs space. This is licensed by the reference's own
  artwork; it does not authorize translation of unsafe production cutouts.
- **Handoff:** annotations can leave while the character persists into a new
  pose/statement. Whole-card exits also occur when the semantic subject changes.
  There is no requirement to connect unrelated cards or force continuous ink.
- **Static holds:** readable plateaus exist. The stronger references interrupt
  them with a new relevant participant, word, relationship or focus state.
  The second reference contains substantially more static sampling intervals.

## Generic implementation contract

`REFERENCE_SEMANTIC_STAGGERED_SEQUENCE_V1` uses source actors and same-scene/shared
story-phase evidence, bounded by actual physical/motion/exit intervals. An
explicit composition envelope authors reveal, retained overlap, focus transfer
and hierarchy rebuild. Timing scales with the available interval and frame rate;
no reference timestamp, production card ID or narration condition is consulted.

The envelope composes with existing P2 states. It cannot retime causal presets,
add center travel, split a composite, or mutate a partition child. Single-source
cards and insufficient/unsafe/unrelated opportunities remain explicit rejections.
Cross-card handoff remains owned by existing continuity and physical lifetimes.

Candidate acceptance requires the unchanged full-plan safety gates, actual-source
runtime pixels, both focus/rebuild attribution thresholds (grayscale delta >=.003,
changed fraction >=.012), readable concurrency and reduced sampled static hold.
This is engineering/proxy evidence. Canonical encoded P3/P4 closure still requires
a new production replay with measurement and visual review.
