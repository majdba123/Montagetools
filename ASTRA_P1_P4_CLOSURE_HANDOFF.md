# P1-P4 closure sprint checkpoint

Active branch: `chatgpt/p0-visual-lifetime-partition-fix` only.
Starting local and remote HEAD: `f6bb887a7ad8cca50fb9c9e2c38aa7e4f1fbdb99`.
Exact-head CI: run 184 / 34181212121, success (verified live).
Do not reset established work or use old-final-package.

## Current implementation

Uncommitted production work: reference_quality_finalizer.py,
reference_geometry_finalizer.py, perceptual_finalizer.py, and interaction/director.py
(seal field coverage only; no interaction/lifetime solver changes). Regressions:
tests/test_v31_reference_quality_finalizers.py and
tests/test_v31_post_interaction_finalization_barrier.py.

- Topology uses source-backed ink with the encoded full-frame denominator.
- Predecessors retiring inside a continuously sparse interval are considered,
  subject to existing scene/shared-phase continuity, cross-card physical
  collision checks, primary/support budgets, and material ink improvement.
- Complete partitions can fit the safe frame with one uniform static transform;
  suppressed members cannot be silently excluded. No independent child scale.
- Root scale/fade actors may fit their static destination into available safe
  space. All absolute composition destinations retain the same center; actors
  with position authority are excluded from this static relocation.
- Existing collision, density, final lifetime, and physical gates remain intact.
- Geometry and perceptual finishing now share candidate checks at both card and
  changed-actor physical sampling origins. An independent audit caught a narrow
  primary overlap missed by the card clock; the repaired plan passes 48/48
  changed-placement safety checks.
- A bounded later-source-reveal continuation can append one additional focal
  relationship state. No elapsed-time drift, repeated pulses, new sources, or
  competing participant tracks. Long-card regression passes.
- Final seal now also covers settled geometry, visibility, and source-ink fields.
  Individual post-seal mutation regressions pass.

Cached canonical planner (not encoded replay) completed without failure:
3 predecessor holds, including one complete partition; 2 partition enlargements;
30 root enlargements (baseline 10); 2 additional semantic handoffs.
Final projected median alpha coverage 0.251140 (not an encoded occupancy claim).
Artifacts: .hexa_tmp_inspect/canonical_current_motion.json and
acceptance_plans_current.json. Canonical input hashes checked by the helper.

## Verification so far

Focused source ink, projected ink, actor attribution, P3/P4, cross-card scale and
placement, participant concurrency, P1 closure, P2 closure, reconstruction,
final lifetime, post-interaction barrier, absolute coordinates, Sprint1: PASS.
New topology/partition/root-static-fit/collision-rollback regression: PASS.
Full deterministic suite exited 0 with its suite PASS marker. It began before
the final clock/seal/later-reveal edits; final focused checks pass and the full
default focused set is being rerun. Exact frozen-commit CI remains required.
No new canonical encoded replay, release build, commit, push, or CI yet.

## Remaining root causes / next work

Prior canonical run 20260908-060855-837c8f03 failed encoded attribution on
SCENE_037_PHYS_03 at its semantic B state: owner authored delta 0.002248,
encoded owner delta 0.002095, unrelated delta 0.045475. This is an observed
diagnostic ID, not an implementation special case. The new uniform partition
fit includes this owner; encoded verification is still required.

The semantic cascade now continues existing owners at a later authored reveal:
5 additional continuations accepted, 2 rejected by geometry/density, alongside
2 initial handoffs enabled by topology retention. Final geometry accepts 28
roots and 2 complete partitions. Independent changed-placement audit: 47/47.
The final added owner-readability/effective-state checks have focused coverage;
production CLI must recompute the final plan before encoding.
Do not claim P4 closed from fixture states.
The first full-suite invocation began before the last physical-clock/seal/later
reveal edits; a final frozen-source suite is required after it completes.

Run configured Python311 with extension/py plus runtime python_import_roots.
Canonical replay helper: .hexa_tmp_inspect/canonical_replay.py. It uses the exact
original BALANCE_LIMIT package/audio, verifies both SHA256 values, and invokes
the production CLI with source imports. Local canonical media is available.
No need to rerender references: cached comparison uses 4 Hz / 320x180.

Acceptance still requires actual encoded mean occupancy >=24-26%, median >=20%,
below-10% frames <=8%, below-15% frames <=25%, and material semantic motion
toward reference 14.5-17.9% (not the old ~9%). No encoded metrics are predicted
as achieved from the current planner proxy. P3/P4 remain OPEN.
