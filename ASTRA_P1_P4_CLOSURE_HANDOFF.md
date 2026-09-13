# Current sparse-production continuation

See [P3/P4 current sparse audit](docs/P3_P4_CURRENT_SPARSE_AUDIT.md) for the newest real MP4 measurement, limited source-use audit, generic timing/framing changes and explicit remaining failures. This supersedes older visual-closure statements below. P1/P2 remain protected; P3/P4 engineering and canonical encoded acceptance remain OPEN.

# P3/P4 reference sequencing continuation

Branch: `chatgpt/p0-visual-lifetime-partition-fix` only.
Starting local and remote checkpoint: `6474dd07425879d2b9f16ec7c215390eff6bc3f7`.
This section supersedes historical continuation notes below.

## Implemented

- Inspected all three local MP4 references with FFprobe and FFmpeg 4 Hz raw-frame
  sampling, contact sheets and frame differences. Originals retain their hashes.
  See `docs/P4_LOCAL_REFERENCE_MOTION_GRAMMAR.md` for identities and observations.
- P3 ranking now integrates absolute sparse exposure and the severe tail rather
  than preferring a short interval by underfilled ratio. Full-frame samples count
  retained carriers across card ownership boundaries. Diagnostics retain low
  percentiles, deficit integrals, before/after quality and unresolved severe cards.
- P3 bounded retries reserve temporal-framing attempts after static fitting fails.
  An intact static source can receive a safe rest-position fit and a temporary
  scale envelope, returning to the support composition before the next actor's
  actual reveal. Physical/causal timing is not extended. Existing safety and
  density monotonicity gates remain mandatory. Exhausted group rollback restores
  the event ID before looking up its snapshot.
- P4 `REFERENCE_SEMANTIC_STAGGERED_SEQUENCE_V1` authors retained staggered reveals,
  readable overlap, linked focus promotion and hierarchy rebuild. Explicit
  composition/participant envelope states compose with existing P2 destinations;
  causal reveals keep their original opacity timing. Actual travel and partition
  actors remain protected. Unrelated/disjoint phases cannot create a relationship.
- Candidates require full-plan collision and per-frame safe-frame checks, actual
  source runtime pixels, reduced static hold, concurrent actors, and both unchanged
  attribution thresholds: grayscale delta >=.003 and changed fraction >=.012.
- The existing final seal covers all new states. Cache dependencies include the
  scheduler and source-preparation implementation. No cache clearing is required.
- Sparse high-scale RGBA sources are cropped before destination allocation on the
  original global half-pixel grid. CPU/RAM are the bottleneck; no GPU path added.
  The test requires <15% of the full-canvas destination allocation, identical
  geometry, and bounded edge-only interpolation differences (remap quantization).

## Validation and limits

New deterministic tests:
`test_v31_reference_staggered_sequence.py`,
`test_v31_sparse_source_preparation.py`,
`test_v31_sustained_sparse_severity.py`.
They cover two/three actors, retention, causal preservation, real encoded MP4
focus/rebuild attribution, final sealing/cache signatures, static-hold reduction,
travel/partition/unrelated/source-limited rejection, exhausted rollback, retained
cross-card ink, and temporary framing with exact return before incoming support.
The tests are registered in `tests/run_v31_test_suite.py`.

The preserved production-plan probe found five source-backed sequencing
opportunities (cards 001, 002, 014, 018, 021). Its per-cohort static-hold estimates
fell materially; these are proxy measurements, not canonical encoded closure.
The severe P3 tail remains explicit: the bounded safe residual probe did not
close it. Do not equate a safety PASS, a larger actor, or a green CI with P3
visual completion. No whole card in that probe consisted of a sole eligible
root; partition and short/unrelated semantic cohorts still limit sequencing.

P1 CLOSED / PROTECTED. P2 CLOSED / PROTECTED.
P3 ENGINEERING OPEN pending material safe production-tail closure.
P4 engineering authority implemented; release certification must be checked on
this commit's exact-head CI and installed identity.
P3 ENCODED OPEN. P4 ENCODED OPEN.

## Canonical replay

Install through `bayer.bat` / `dist/latest/INSTALL_HEXA_V31.bat`, then use the
HEXA V31 Premiere panel Build action with the original package and voice.
Canonical package SHA256:
`6abda3a85214305e37ab4b533cdb23b522607e631c68e70d54438ca8cb145535`.
Canonical voice SHA256:
`6332a4da17261e4a05ca7f5206370f372f31c72764cbc531e972d8c985d7a030`.

CLI equivalent, from the configured installed runtime environment:
`python -m hexa_v31.cli build --package "<canonical package.zip>" --voice "<canonical voice.mp3>" --extension-root "<installed extension>"`.
Measure the new production MP4 with the same 4 Hz / 320x180 thresholds and
visually review normal playback before declaring either encoded gate closed.
Temporary inspection scripts, probes, references and generated media are excluded
from product commits. Do not open P5/P6/P7 or alter the protected baseline branch.

---

# P1-P4 closure checkpoint

Only branch: `chatgpt/p0-visual-lifetime-partition-fix`.
Never reset or use `old-final-package`.

## Current continuation — byte-identical canonical evidence

Starting HEAD: `91a8fc23f70a0878bdfea2e06e48b1d3a1b5ffd5`.
Exact-head CI #192 / run `34277783670` was fully green.

The user installed/built that exact HEAD and produced the canonical BALANCE_LIMIT replay.
The encoded MP4 was byte-identical to the last evaluated `365f17f8` baseline:

`SHA256 c79dbb9989f04512f4cdc091c21e8657bafe8d4be73f60ecbaa488e9115c0479`

Therefore the `91a8fc23` joint-fitter batch produced no material encoded-pixel change.
Treat this as engineering evidence, not a file-selection issue.

Frozen `4 Hz / 320x180` measurements remain approximately:
- occupancy mean: 19.6-19.7%
- occupancy median: 20.16-20.17%
- frames <10%: ~10.6-10.8%
- frames <15%: ~34.3-34.5%
- motion mean: ~10.2%
- motion median: ~7.6%
- near-static: ~32.6%

P1 CLOSED / protected.
P2 CLOSED / protected.
P3 OPEN.
P4 OPEN.
Do not open P5/P6/P7.

## Root cause after byte-identical replay

Production inspection established:
1. `motion/__init__.py` calls `finalize_reference_joint_geometry()` in the canonical path.
2. The final seal includes settled geometry and composition-state fields.
3. Production scene-media cache signatures hash the complete render-map event list.
4. `prepare_composition_actor()` consumes `layout_scale_multiplier` and `card_rest_position_norm`.

Stale cache alone therefore does not explain the byte identity. The dominant defect was
opportunity starvation: Joint V1 reused the independent-fit position-authority guard,
which treats any `preset_actions` as position authority. P2/P4 actors with legitimate
scale/opacity-only authority were excluded even though a static card-level relocation is
legal. V1 also stopped at a fixed pair target of 0.26 even when a card remained severely
underfilled after independent fitting.

A second render-consumption gap was found: pure-static events with no preset or composition
state follow the legacy `_event_state()` branch, which used neutral `end_position_px`
instead of the final `card_rest_position_norm`. This could discard the center component
of a late certified static fit.

## Current engineering change

`reference_joint_fitter.py` is upgraded to
`REFERENCE_COORDINATED_PRIMARY_CONTEXT_FIT_V2`.

V2:
- keeps source-backed `ROOT_ATOMIC` and semantic PRIMARY+context requirements;
- keeps same-card and same-scene/shared-story-phase evidence;
- keeps >=0.55s physical overlap and partitions excluded;
- distinguishes actual center travel from scale/opacity-only authority;
- rejects position animation, ENTRY/EXIT travel, WITHIN_FRAME travel, translated states,
  drift and vector motion;
- permits APPEARANCE/DISAPPEARANCE presets and center-preserving hierarchy states;
- derives a bounded pair target from card underfill severity, 0.26 through 0.32;
- adds pair-level scale pressure when individual actor targets are already satisfied;
- remains bounded by existing role/source caps and semantic destinations;
- preserves pair order;
- requires pair ink gain >=0.012 plus material card gain;
- retains full card-clock + physical-clock collision/composition QA;
- retains density monotonicity and atomic rollback;
- records structural pair requests before authority rejection for useful production stats.

The preview facade now bridges `card_rest_position_norm` into the pure-static evaluator
only when there is no preset/state/position authority. Dynamic P2 paths are untouched.

Regressions cover severe-card pressure above 0.26, generalized IDs/durations,
scale/opacity-only authority, center-preserving hierarchy, protected real travel,
unrelated phases, and pure-static final planner center consumption by `_event_state()`.

## Acceptance remains unchanged

P3 closure requires canonical encoded evidence:
- occupancy mean >=24-26%
- median >=20%
- <10% <=8%
- <15% <=25%
- zero illegal sustained viewport clipping

P4 closure requires a material encoded motion/recomposition jump toward the
14.5-17.9% reference regime, with semantic attribution and no drift/jitter cheat.

No planner/proxy/test result closes P3/P4. A new exact-head canonical encoded replay is
required after CI.

## Next replay diagnostics

Inspect `reference_joint_geometry_finalizer` first:
- `joint_pairs_requested`
- `joint_candidates_evaluated`
- `joint_pairs_committed`
- `joint_event_ids`
- `joint_rejections`
- `joint_max_target_ink`
- `before_underfilled_seconds`
- `after_underfilled_seconds`
- post-joint semantic candidates/commits/rejections

If requested=0, the next owner is semantic cohort/card-level topology. If collision
dominates, improve bounded negative-space allocation without weakening collision. If
commits are nonzero but encoded bytes stay unchanged, reopen integration/cache/render
authority immediately. If P3 rises but P4 remains near 10%, continue authored semantic
progression rather than static density.

Diagnostic intervals are evidence only, NEVER implementation conditions:
32.75-36.75, 48-51, 61.5-63.75, 73.5-78.5, 80.5-82.75.
Static diagnostics: 89.5-91.5, 96-98.75.

Canonical package SHA256:
`6abda3a85214305e37ab4b533cdb23b522607e631c68e70d54438ca8cb145535`

Canonical audio SHA256:
`6332a4da17261e4a05ca7f5206370f372f31c72764cbc531e972d8c985d7a030`

## Protected invariants

- P1/P2 remain closed/protected absent new encoded evidence in their ownership.
- Final Motion Plan remains render authority.
- canonical coordinates remain 1920x1080 with one output transform.
- partition child + residual remain atomic; never independently density-scale a child.
- unsafe actors never receive new position travel.
- collision/safe-frame/lifetime certification thresholds are not weakened.
- no package IDs, timestamps, narration-specific rules or BALANCE_LIMIT branches.
- no opacity ghosts, filler, camera zoom, drift, jitter or periodic pulses.
