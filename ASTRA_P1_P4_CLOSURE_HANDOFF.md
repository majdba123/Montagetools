# P1-P4 closure checkpoint

Only branch: chatgpt/p0-visual-lifetime-partition-fix.
Sprint base: 729515bd81ee66d653af1f4c77bc6615ee2f2d50; remote equality verified.
Exact-head CI 185 / 34230379438 passed. Never reset or use old-final-package.

## Latest batch

Retained exits now end at the committed retirement, not before a faded tail.
Retained context must remain >=0.85 effective opacity before its intentional
exit; otherwise reject the candidate, never globally clamp opacity.
Static retained roots may use an existing semantic layout slot.
Root enlargement tries up to six existing semantic destinations before reducing
scale. Every mutation passes card-clock and physical-clock collision checks.
Later-reveal amplitude now uses a four-step deterministic ladder derived from
source ink, role, population and safe-frame headroom instead of fixed 1.30.
P1/P2, translation capability, partitions, renderer, QA thresholds and seal remain
unchanged from the sprint base.

Production files: layout/reference_quality_finalizer.py,
layout/reference_geometry_finalizer.py. Tests: test_v31_reference_quality_finalizers.py.

## Verification

Focused P1/P2/P3/P4, source ink, participant concurrency, cross-card geometry,
reconstruction, lifetime/barrier, absolute coordinates, Sprint1: PASS.
Readability, normalized hierarchy and semantic-slot regressions: PASS.
Frozen-source full suite exited 0 on 2026-09-08 around 22:08 local, with suite
PASS marker. Media-probe fixture skipped for no PATH ffmpeg; encoded P3/P4
fixtures used configured ffmpeg. Independent placement audit: 46/46 PASS.
New exact-commit CI remains pending at this writing.

## Product evidence and next issue

Existing encoded run 20260908-163240-89a165fb belongs to base 729515bd.
User-reported 4 Hz / 320x180 metrics: occupancy mean19.35/median18.89%;
below10 12.59%; below15 33.75%; motion mean10.26/median7.66%; static~32.3%.
Actual encoded QA: 27/28 attributable. Later reveal owned by SCENE_014_PHYS_01
had owner delta0.001849. This ID is diagnostic, never an implementation branch.

Current cached candidate: 24 planned transitions, 31 root enlargements from
797 trials, 2 partition enlargements, 1 readable retained partition cohort,
2 later-reveal continuations. Geometry projected median alpha0.243087;
full-frame ink proxy mean0.168840, NOT encoded occupancy.
Two formerly ghost-like root holds now reject on collisions.
These projections do NOT establish P3/P4 closure or predict the 24-26% floor.

Next: bounded order-preserving joint fitting of a focal root and its context.
Independent fitting cannot use space that requires moving both actors.
Also inspect fixed root/group enlargement caps against source-ink requirements.
Do not weaken collision or independently transform partition children.

Ignored diagnostics only: establishment_probe.py improved ink proxy by merely
0.0022 on one focal phase; continuity_probe.py found only3 safe short cross-card
continuations from authored CONTINUES_CANONICAL_EXPLANATION links. Most collide.
Neither probe changed production. Do not present them as completed fixes.

## Resume

Configured Python311 plus repo extension/py and runtime python_import_roots.
Reuse .hexa_tmp_inspect/focused_candidate_checks.py,
acceptance_baseline.py plans --control current, placement_safety.py.
canonical_replay.py invokes production CLI with original verified inputs.
Package SHA256: 6abda3a85214305e37ab4b533cdb23b522607e631c68e70d54438ca8cb145535
Audio SHA256: 6332a4da17261e4a05ca7f5206370f372f31c72764cbc531e972d8c985d7a030
Original media available in Desktop/content/VideoFolder/BALANCE_LIMIT.
No new replay or local installation in this batch.

P3/P4 OPEN. Continue engineering after CI. No P5/P6/P7.
