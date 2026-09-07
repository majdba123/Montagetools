# P3/P4/P8 canonical acceptance checkpoint

HEAD: `28b072638a51c35c6f90ee4c90a5e7dbe800927b`. All changes remain local WIP.

## Preserved canonical MP4 actor audit

Run `20260907-031719-c8ba4a99`; MP4 SHA256 `03af81e50030ad1f03e246cf6ee99ae82edcddbf35da7e67d0fa05603192fb56`.
Exact source-framing report matched all 31 original crop/refit decisions. Planner and render-map composition/timing fields matched (zero mismatches). No production render or behavior change was used for this audit.

Full-frame verified: 21/21. Actor-attributable verified: 21/21. Confirmed false greens: 0; event IDs: none.

The first post-state-only audit returned 19/21. Its two apparent failures (SCENE_013_PHYS_03 and SCENE_024_PHYS_02) sampled after both intended actors had physically retired. Authored-midpoint encoded probes prove participant contribution above the unchanged .003 delta / .012 changed-pixel thresholds. These were attribution sampling false negatives, not confirmed false greens. The full-frame thresholds and original full-frame sampling are unchanged; attribution additionally examines the authored midpoint. Ordinary entry/exit motion cannot earn credit without an authored-state counterfactual delta. Unrelated actor alpha support and rendered text/graphics are excluded.

Owner equals event ID in this table. Deltas are full-frame-normalized mean absolute gray change divided by 255, not ROI-normalized percentages. Owner/participant columns require encoded/source concordance and a nonzero authored-state counterfactual contribution. Full-frame delta retains the original before/after window; the last column identifies the actual attribution window.

| Event / owner | Card | Participant | Owner delta | Participant delta | Unrelated delta | Full-frame delta | Attributable pass | Failure | Attribution samples (s) |
|---|---|---|---:|---:|---:|---:|---|---|---|
| SCENE_002_PHYS_01 | VCARD_002 | SCENE_004_PHYS_02 | 0.031140 | 0.000912 | 0.026431 | 0.050762 | PASS | NONE | 1.733333 → 2.466667 |
| SCENE_005_PHYS_01 | VCARD_002 | SCENE_005_PHYS_02 | 0.034081 | 0.000000 | 0.013883 | 0.060932 | PASS | NONE | 5.933333 → 6.633333 |
| SCENE_010_PHYS_01 | VCARD_004 | SCENE_010_PHYS_02 | 0.025640 | 0.017800 | 0.000000 | 0.047606 | PASS | NONE | 15.500000 → 16.233333 |
| SCENE_013_PHYS_01 | VCARD_005 | SCENE_013_PHYS_03 | 0.039007 | 0.000000 | 0.031285 | 0.075570 | PASS | NONE | 23.000000 → 23.733333 |
| SCENE_013_PHYS_03 | VCARD_005 | SCENE_013_PHYS_04 | 0.000000 | 0.007650 | 0.029583 | 0.075570 | PASS | NONE | 23.000000 → 23.366667 |
| SCENE_014_PHYS_01 | VCARD_006 | SCENE_014_PHYS_02 | 0.000391 | 0.059130 | 0.000000 | 0.094594 | PASS | NONE | 26.033333 → 26.733333 |
| SCENE_016_PHYS_01 | VCARD_007 | SCENE_017_PHYS_01 | 0.031780 | 0.030812 | 0.000000 | 0.075751 | PASS | NONE | 30.233333 → 30.966667 |
| SCENE_019_PHYS_01 | VCARD_008 | SCENE_019_PHYS_02 | 0.023451 | 0.000000 | 0.000000 | 0.057283 | PASS | NONE | 34.000000 → 34.733333 |
| SCENE_022_PHYS_01 | VCARD_010 | SCENE_024_PHYS_02 | 0.029277 | 0.015558 | 0.025120 | 0.073829 | PASS | NONE | 41.366667 → 42.100000 |
| SCENE_024_PHYS_02 | VCARD_009 | SCENE_024_PHYS_03 | 0.001681 | 0.002333 | 0.000000 | 0.028273 | PASS | NONE | 42.333333 → 42.500000 |
| SCENE_027_PHYS_01 | VCARD_010 | SCENE_027_PHYS_02 | 0.006410 | 0.023106 | 0.000000 | 0.107333 | PASS | NONE | 47.166667 → 47.900000 |
| SCENE_028_PHYS_01 | VCARD_011 | SCENE_029_PHYS_01 | 0.053183 | 0.019669 | 0.000000 | 0.079428 | PASS | NONE | 50.933333 → 51.666667 |
| SCENE_030_PHYS_01 | VCARD_012 | SCENE_030_PHYS_02 | 0.024575 | 0.000000 | 0.010833 | 0.048659 | PASS | NONE | 55.033333 → 55.766667 |
| SCENE_033_PHYS_01 | VCARD_013 | SCENE_033_PHYS_02 | 0.030996 | 0.013234 | 0.000000 | 0.119249 | PASS | NONE | 58.433333 → 59.166667 |
| SCENE_035_PHYS_01 | VCARD_014 | SCENE_036_PHYS_01 | 0.028733 | 0.039260 | 0.000000 | 0.086944 | PASS | NONE | 63.366667 → 64.100000 |
| SCENE_037_PHYS_01 | VCARD_015 | SCENE_037_PHYS_03 | 0.030747 | 0.000000 | 0.001620 | 0.057803 | PASS | NONE | 67.233333 → 67.933333 |
| SCENE_037_PHYS_03 | VCARD_015 | SCENE_037_PHYS_04 | 0.008914 | 0.001495 | 0.031223 | 0.057803 | PASS | NONE | 67.233333 → 67.933333 |
| SCENE_040_PHYS_01 | VCARD_016 | SCENE_040_PHYS_02 | 0.000615 | 0.077302 | 0.000000 | 0.092589 | PASS | NONE | 74.366667 → 75.100000 |
| SCENE_043_PHYS_01 | VCARD_018 | SCENE_044_PHYS_01 | 0.049627 | 0.019245 | 0.000000 | 0.077169 | PASS | NONE | 82.766667 → 83.466667 |
| SCENE_045_PHYS_01 | VCARD_019 | SCENE_046_PHYS_01 | 0.047846 | 0.021188 | 0.000000 | 0.080111 | PASS | NONE | 86.900000 → 87.633333 |
| SCENE_049_PHYS_01 | VCARD_021 | SCENE_049_PHYS_02 | 0.029210 | 0.050776 | 0.000000 | 0.090022 | PASS | NONE | 95.500000 → 96.200000 |

## Remaining perceptual limitations

Attribution is not reference-quality certification. For SCENE_013_PHYS_03, its owner destination is masked during its active transition by an incoming participant state; its own participant still supplies meaningful encoded movement. Several other supports have zero authored contribution at the post-state sample. The brief SCENE_024_PHYS_02 transition has only 0.125714 seconds after final carrier clamping and overlaps exit. These observations keep hierarchy choreography/P4 open even where at least one intended actor is encoded.

## Source-ink correction and rejected candidates

Planner `source_layer_path` previously bypassed source-alpha measurement and could use whole-canvas matte fraction inside an already-tight actor bbox. The composition owner now measures alpha within the declared object bbox, preserving source bytes and collision geometry. Initial correction changed 16 placements. Full physical-interval checks found 13 safe and 3 unsafe changed placements, including cross-card neighbors. Two cross-card conflicts already existed and worsened; one was introduced. A separate stronger density-pruning experiment caused 2.450 seconds of sustained viewport clipping and was removed, not accepted or weakened around.

The active candidate repairs static composition against final cross-card overlap using existing semantic slots, safe-center projection, unchanged-scale candidates before any reduction, and bounded coupled focal/support placement when independent placement is infeasible. It changes neither lifetimes nor presets, never moves child/residual partitions independently, and retains the unchanged physical gate.

## Final pre-replay placement verification

The completed cached canonical planner passes the unchanged physical and viewport gates. There are 19 final changed placements versus the preserved MP4 plan, and 19/19 pass the full physical-interval safety audit. The initial 3 unsafe changed placements were repaired; no failed geometry was accepted. Candidate projection is not encoded acceptance: projected median ink 0.203900, median safe-frame bbox coverage 0.454853, and planned temporal population 1.723829.

All rows below pass safe frame, per-actor collision, cross-card collision, viewport clipping, physical/motion interval containment, unchanged motion-capability flags, and composition-state translation safety. Ink is the measured source-alpha fraction inside the declared object bbox; it is not an encoded occupancy measurement.

| Event | Card | Old position | New position | Old scale | New scale | Source ink | Physical lifetime | Motion lifetime | All safety checks |
|---|---|---|---|---:|---:|---:|---|---|---|
| SCENE_001_PHYS_03 | VCARD_001 | 0.680000, 0.310000 | 0.680000, 0.310000 | 0.907200 | 0.866400 | 0.758523 | 0.000000, 0.800000 | 0.000000, 0.800000 | PASS |
| SCENE_001_PHYS_04 | VCARD_001 | 0.680000, 0.730000 | 0.680000, 0.730000 | 0.920000 | 1.000000 | 0.714685 | 0.000000, 0.800000 | 0.000000, 0.800000 | PASS |
| SCENE_005_PHYS_01 | VCARD_002 | 0.750000, 0.520000 | 0.660000, 0.520000 | 0.840000 | 0.840000 | 0.377963 | 4.729524, 9.500000 | 5.020000, 9.500000 | PASS |
| SCENE_010_PHYS_01 | VCARD_004 | 0.750000, 0.520000 | 0.660000, 0.520000 | 1.000000 | 1.000000 | 0.512072 | 14.188571, 19.833333 | 14.600000, 19.833333 | PASS |
| SCENE_014_PHYS_02 | VCARD_006 | 0.580000, 0.520000 | 0.660000, 0.520000 | 0.866400 | 0.600000 | 0.556562 | 23.647619, 27.237143 | 24.286667, 27.237143 | PASS |
| SCENE_018_RESIDUAL_SUPPORT | VCARD_007 | 0.680000, 0.730000 | 0.500000, 0.730000 | 0.540000 | 0.540000 | 0.781456 | 31.665000, 32.840000 | 31.665000, 31.665000 | PASS |
| SCENE_019_PHYS_01 | VCARD_008 | 0.750000, 0.520000 | 0.660000, 0.520000 | 1.080000 | 1.311000 | 0.282871 | 33.106667, 36.733333 | 33.106667, 36.733333 | PASS |
| SCENE_019_PHYS_02 | VCARD_008 | 0.340000, 0.520000 | 0.250000, 0.520000 | 0.560000 | 0.416000 | 0.494019 | 33.106667, 35.360000 | 33.166667, 35.360000 | PASS |
| SCENE_020_PHYS_02 | VCARD_008 | 0.340000, 0.520000 | 0.250000, 0.520000 | 0.448000 | 0.345600 | 0.296377 | 34.560000, 36.733333 | 35.360000, 36.733333 | PASS |
| SCENE_025_PHYS_02 | VCARD_010 | 0.340000, 0.520000 | 0.340000, 0.520000 | 0.920000 | 0.983091 | 0.784922 | 42.565714, 45.110000 | 43.970000, 45.110000 | PASS |
| SCENE_030_PHYS_01 | VCARD_012 | 0.270000, 0.560000 | 0.340000, 0.520000 | 1.000000 | 1.000000 | 0.336088 | 52.024762, 56.800000 | 54.140000, 56.800000 | PASS |
| SCENE_030_PHYS_02 | VCARD_012 | 0.730000, 0.560000 | 0.680000, 0.730000 | 0.388800 | 0.320000 | 0.446411 | 52.024762, 55.655000 | 53.306667, 55.655000 | PASS |
| SCENE_037_PHYS_01 | VCARD_015 | 0.750000, 0.520000 | 0.730000, 0.536241 | 0.840000 | 0.840000 | 0.529175 | 66.213333, 73.500000 | 66.320000, 73.500000 | PASS |
| SCENE_037_PHYS_04 | VCARD_015 | 0.500000, 0.520000 | 0.320000, 0.310000 | 0.360000 | 0.320000 | 0.607464 | 66.213333, 68.010000 | 66.333333, 68.010000 | PASS |
| SCENE_040_PHYS_02 | VCARD_016 | 0.340000, 0.520000 | 0.320000, 0.310000 | 0.680000 | 0.320000 | 0.624940 | 70.942857, 75.672381 | 72.646667, 75.672381 | PASS |
| SCENE_041_FV_ACTOR_02 | VCARD_017 | 0.730000, 0.700000 | 0.680000, 0.730000 | 0.320000 | 0.540000 | 0.393807 | 75.672381, 78.250000 | 75.672381, 78.250000 | PASS |
| SCENE_042_PHYS_01 | VCARD_017 | 0.300000, 0.520000 | 0.320000, 0.310000 | 0.540000 | 0.518400 | 0.511817 | 75.672381, 80.433333 | 78.240000, 80.433333 | PASS |
| SCENE_043_PHYS_01 | VCARD_018 | 0.660000, 0.520000 | 0.710024, 0.520000 | 0.648000 | 0.648000 | 0.646779 | 80.140000, 85.366667 | 80.140000, 85.366667 | PASS |
| SCENE_048_PHYS_01 | VCARD_020 | 0.500000, 0.500000 | 0.500000, 0.520000 | 1.000000 | 0.941552 | 0.571975 | 89.860952, 94.633333 | 92.140000, 94.633333 | PASS |

## Focused regressions and replay blocker

PASS: source-ink basis, projected visible ink, actor attribution including real encoded short-handoff midpoint, encoded P3/P4 fixture, cross-card scale, cross-card placement, participant contract, P1 closure, Foundation reconstruction/translation safety, final visual lifetime, post-interaction finalization barrier, absolute preset coordinate invariance, and Sprint1 integration. These ran as separate configured-runtime Python processes. Full suite was not run.

P2 closure is not reliably passing. An isolated run passed, but subsequent serial runs failed before physical action compilation. A read-only solver trace captured CP-SAT status UNKNOWN, configured max_time_in_seconds=0.2, wall_time=0.1987647, zero branches, zero conflicts, zero integer propagations, and deterministic_time=1.37e-7. This is budget exhaustion before search, not evidence that the model is infeasible. The test raises ZERO_ACTIONABLE_INTERACTION_EMBODIMENT after SAFE_FALLBACK_NO_FEASIBLE_SCHEDULE.

AST comparisons against HEAD confirm solve_interaction_schedule, _available_frames, _reserved_intervals, and apply_interaction_director are unchanged. The schedule-function AST SHA256 is 09fd5dc997ad169b9fa5bcd35f8ba33a5b83f8baa09308f40092a9c9fc894b59. No solver settings, constraints, P2 thresholds, or test assertions were weakened. No warm-up or retries were added to manufacture a test pass.

The latest user explicitly protects P2 and authorizes only its regressions. A change to the protected solver's budget/startup handling needs authorization. The one new canonical replay has therefore NOT been started: the required focused P2 gate is failing. No new encoded candidate metrics exist; the prior canonical metrics remain historical evidence only. P3/P4/P8 remain open pending a passing focused gate and actual new encoded production evidence. No full suite, commit, push, install, or Premiere launch occurred.

