# Participant repair checkpoint — 2026-09-07

Status: uncommitted WIP, not release-certified. Starting/current HEAD:
`28b072638a51c35c6f90ee4c90a5e7dbe800927b`.

## Repairs and focused proof

- Optical scale candidates now undergo the existing trajectory checks in every
  affected card, including later cards reached by a long-lived carrier. The new
  cross-card regression fails against the HEAD implementation and passes with
  this repair. Thresholds, positions, and lifetimes are unchanged.
- Participant A precedes B, starts no earlier than legal existence, and B is
  bounded by both participants' physical end. Insufficient windows and static
  residual supports reject the optional candidate without mutating either actor.
- Participant states use the existing shared composition evaluator, renderer
  routing, motion-interval compiler, partition bounds, and final timing seal.
- The candidate concurrency guard now calls the existing visual density authority
  instead of using an opacity-only approximation.

Passed: `test_v31_composition_cross_card_scale.py`,
`test_v31_composition_participant_contract.py`,
`test_v31_problem34_adaptive_composition.py`,
`test_v31_foundation_problem1_closure.py`, `test_v31_problem2_closure.py`,
`test_v31_foundation_reconstruction_safety.py`,
`test_v31_final_visual_lifetime_contract.py`,
`test_v31_post_interaction_finalization_barrier.py`,
`test_v31_absolute_preset_state.py`,
`test_v31_sprint1_production_integration.py`.

P2 failed in an ad-hoc shared-process run after other tests, then passed in a
fresh process. The maintained suite runs scripts in separate processes. Do not
interpret the shared-process failure as a diagnosed production regression.

## Canonical identity and replay stop

Package: `HEXA_INSUFFICIENT_BALANCE_AR_HEXA_V20_SCENE_PACKAGE_V1_FINAL.zip`
under `C:/Users/INTEL CENTER/Desktop/content/VideoFolder/BALANCE_LIMIT`.

SHA256: `6abda3a85214305e37ab4b533cdb23b522607e631c68e70d54438ca8cb145535`.

Audio in the same folder:
`ElevenLabs_2026-08-15T03_15_07_Ahmed - Intellectual, Calm & Educational_pvc_sp101_s76_sb100_se0_b_m2.mp3`.

SHA256: `6332a4da17261e4a05ca7f5206370f372f31c72764cbc531e972d8c985d7a030`.
Live probe: 99.32 seconds. Both hashes checked immediately before execution.

Run `20260907-031059-1995e592` failed before motion planning/render at
VISION_RECONSTRUCTION / SCENE_001: `ModuleNotFoundError: No module named 'cv2'`.

This was an invocation defect in the temporary replay helper: it inserted the
configured vendor roots into parent `sys.path` but did not export `PYTHONPATH`.
`app/pipeline.py::_run_scene_vision_worker` launches a new interpreter and
inherits `PYTHONPATH`, not parent `sys.path`. A read-only child-process probe
with the configured roots exported successfully imported cv2 from the V23
vendor overlay. No package installation is needed to resolve that invocation.

The runtime configuration logs stale source identity `c81c4f0...`; actual local
HEAD and dirty diff were recorded separately, not misrepresented as installed
source identity.

Per the latest replay stop rule: no second production replay, full suite,
commit, push, installation, or Premiere execution was performed.

Failure evidence resides under:
`C:/Users/INTEL CENTER/AppData/Local/HEXA/VideoBuilderV31/builds/6abda3a85214_6332a4da1726/runs/20260907-031059-1995e592`.

## Preserved diagnostic evidence

Ignored `.hexa_tmp_inspect` contains the diagnostic helpers, canonical identity,
planner controls/snapshots, normalized metrics, and four contact sheets. These
are not maintained production tools and must not be staged as release code.

The cached-input planner diagnostic passed physical certification and density
with 24 committed recompositions after the initial repair. It is not a full
production replay and does not prove encoded or actor-attributable success.

Normalized historical candidate: 4 Hz, 320x180 INTER_AREA, occupancy min RGB<245,
motion grayscale absolute delta>8, near-static motion<0.5%. Occupancy mean
16.6285%, median 15.2274%; motion mean 8.3644%, median 4.8655%; near-static
35.6061%, longest sampled static interval 2.5 s. Reference mean motion:
14.5059%, 16.6384%, 17.8945%. These are historical encoded files, not output of
the dirty WIP. No new MP4, new metrics, or reference-parity claim exists.

Next authorized replay must export the configured vendor import roots to child
processes, keep the canonical hashes, and preserve all existing caches/WIP.

## Recovered canonical run: 20260907-031719-c8ba4a99

The subsequently authorized launcher-only correction exported the existing
vendor roots in `PYTHONPATH`. A child imported cv2, NumPy, Pillow, and the Vision
worker successfully. No production/test code changed for this replay.

The same process completed at 03:44:51 +03:00. `logs/master.log`,
`logs/events.jsonl`, `logs/build_summary.json`, and `HEXA_V31_FAILURE.json`
agree: FAIL / PRODUCTION_CERTIFICATION /
`V31 final MP4 artifact integrity failed: underfilled_frame_percent_le_20pct`.
No second build was started to recover this result. The failure bundle exists.

Vision: 49/49 cached scenes; motion director, density, final physical/timing
barrier, render-map completeness (75/75), continuous render and assembly: PASS.
Interaction pixel QA reports 7/7 physical actions. The separate legacy
storytelling verification has zero planned/verified story actions; physical
acting verification is NOT_APPLICABLE with zero eligible/planned actions.
Those empty legacy results are not additional proof of visible interaction.

Encoded composition QA: 21 planned, 21 verified, no failed rows. Its measurements
are **full-frame only**. OWNER_DELTA, PARTICIPANT_DELTA and UNRELATED_DELTA are
not present for any of the 21 rows. Actor-attributable recomposition success
therefore remains UNVERIFIED, not 21/21. P8 remains open. Identical timestamps
share identical full-frame scores; unrelated motion is not ruled out.

Final MP4 (CLI output, not a real Premiere export):
`C:/Users/INTEL CENTER/Documents/HEXA Video Builder/Exports/HEXA_INSUFFICIENT_BALANCE_AR_V31_0_25_20260907-031719-c8ba4a99.mp4`

SHA256: `03af81e50030ad1f03e246cf6ee99ae82edcddbf35da7e67d0fa05603192fb56`.
Size: 24,540,469 bytes. H.264, 1920x1080, 30 fps, audio present.

The production guard measured 42.411% of frames below 15% occupancy, against
its unchanged maximum of 20%. Reference proxy scored 30%, with seven failed
gates: motion activity, occupancy, average/p90/maximum static hold, underfilled
screen time, and motion peak energy. Perceptual story QA passes its own gates;
that does not override production certification. Reference-only score: 6.297/10
against 8/10. No install or full suite is authorized by these results.

### Normalized comparison of the actual files

All four videos were decoded again with the same 4 Hz / 320x180 method documented
above. Percent values below are not the pipeline's adjacent-frame proxy.

| Metric | Reference 1 | Reference 2 | Reference 3 | New canonical MP4 |
| --- | ---: | ---: | ---: | ---: |
| Occupancy mean | 33.1837 | 33.2494 | 32.5254 | 17.2465 |
| Occupancy median | 23.5286 | 24.8142 | 26.6528 | 15.9427 |
| Motion mean | 14.5059 | 16.6384 | 17.8945 | 9.2434 |
| Motion median | 7.4549 | 10.9167 | 13.2708 | 5.6094 |
| Motion p25 | 1.2396 | 4.5677 | 6.6250 | 0.0000 |
| Motion p75 | 21.0174 | 21.3898 | 23.3368 | 15.9214 |
| Motion p90 | 35.6104 | 34.9948 | 37.7837 | 24.3993 |
| Near-static % | 21.1356 | 4.8110 | 7.5710 | 33.0808 |
| Longest sampled static seconds | 1.00 | 0.50 | 1.25 | 2.50 |

New normalized occupancy below 10%: 15.8690%; below 15%: 45.0882%.
Planner-derived mean temporal population: 1.733799 (not an independently
segmented encoded-object count). Mean motion increased 0.8790 percentage points
from the previous canonical candidate, and near-static decreased 2.5253 points.
This is improvement, not parity. Newly sampled contact-sheet inspection still
shows small isolated compositions and pale/low-visibility intervals. Full
semantic/perceptual video acceptance has not been performed. Verdict:
BELOW_REFERENCE against all three references.

### Five rejected candidates

Diagnostic-only execution of the composition compiler on its preserved input
snapshot reproduced the saved production optimizer result exactly: 26 evaluated,
21 committed, five PARTICIPANT_LIFECYCLE rejections, identical committed IDs.
No production planner/render replay was needed. Full traces are preserved in
`.hexa_tmp_inspect/same_run_rejections.json`.

All times below are seconds. Owner A is the settled pose; owner B duration is
0.48 s. Participant A duration is 0.32 s. Proposed B rows were never committed.

| Card | Owner/event | Participant | Owner A / B start | Participant A / B start | Owner physical window at candidate | Participant physical window at candidate | Reason and classification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| VCARD_001 | SCENE_002_PHYS_01 | SCENE_002_PHYS_02 | 1.52 / 1.74 | 1.42 / 1.74 | 0.72–5.033333 | 0.72–1.44 | B starts 0.30 s after support ends; CORRECT_SAFETY_REJECTION |
| VCARD_003 | SCENE_007_PHYS_02 | SCENE_007_PHYS_03 | 10.259048 / 10.479048 | 10.159048 / 10.479048 | 9.459048–13.066667 | 9.459048–10.44 | B starts after support ends; CORRECT_SAFETY_REJECTION |
| VCARD_009 | SCENE_022_PHYS_01 | SCENE_022_PHYS_02 | 38.70 / 38.92 | 38.60 / 38.92 | 37.836190–44.00 | 37.836190–38.61 | B starts 0.31 s after support ends; CORRECT_SAFETY_REJECTION |
| VCARD_010 | SCENE_025_PHYS_01 | SCENE_025_PHYS_02 | 44.98 / 45.20 | 44.88 / 45.20 | 42.565714–46.30 | 42.565714–45.11 | B starts 0.09 s after support ends; CORRECT_SAFETY_REJECTION |
| VCARD_017 | SCENE_041_FV_ACTOR_02 | SCENE_041_RESIDUAL_SUPPORT | 76.472381 / 77.52 | 77.20 / 77.52 | 75.672381–78.25 | 75.672381–78.25 | Residual-support carrier is static and cannot independently execute this scale sequence; CORRECT_SAFETY_REJECTION |

Final physical ends for the first four supports are 1.52, 10.50, 38.636190,
45.11 respectively. The second leaves only 0.020952 s before retirement and is
already in its exit; none rescues the proposed meaningful B transition.
Overconservative rejections proven: zero. This does not prove that a different
semantically timed candidate could never work; it proves these candidates are
invalid. Owners 002 and 022 later receive valid handoffs in another card, so
five rejected candidates do not mean five missing recompositions versus 24.

### Story Lock warning, verbatim and classified

The log contains exactly one WARNING:

```text
[2026-09-07T03:19:08.677+03:00] WARNING USER_PRESET_STORY_LOCK -            USER_PRESET_STORY_LOCK_REVIEW_REQUIRED | physical_event_percent=68.354 title_only_percent=8.861 deferred_percent=22.785 high_confidence_p95_frames=4.771 targets={'physical_min_percent': 80, 'title_max_percent': 10, 'deferred_max_percent': 10, 'p95_max_frames': 4, 'hard_max_frames': 6} deferred_anchor_count=18
```

Classification: SEMANTIC_COVERAGE + SEMANTIC_TIMING, at global plan scope.
Severity: WARNING in the pipeline, unresolved product-acceptance blocker.
Owner: semantic scheduling/handoff planning in `planning/preset_story_planner.py`
and the semantic coverage audit consumed by `app/pipeline.py`; the audit reports
the problem and must not be weakened. P5_RELEVANT=YES. P6_RELEVANT=YES for title
substitution review, but title-only 8.861% is within its 10% limit and does not
independently prove a typography failure. MUST_FIX_BEFORE_INSTALL=YES for
coverage/timing acceptance, without automatically patching individual warnings.

Viewer-facing risk supported by audit: meaningful visual hits arrive too early,
too late, or without verified physical change near the spoken anchor. Physical
coverage 68.354% is below 80%; deferred 22.785% exceeds 10%; high-confidence p95
4.771 frames exceeds 4 (but is below the separate hard maximum 6).

Affected deferred events and signed hit error in frames:

| Card | Events (signed error) | Audit classification |
| --- | --- | --- |
| VCARD_001 | SCENE_003_PHYS_02 (+20.4), SCENE_004_PHYS_02 (+11.4) | primary budget blocked |
| VCARD_004 | SCENE_011_PHYS_01 (+76.38) | committed event not physically verified |
| VCARD_006 | SCENE_014_PHYS_02 (-25) | committed event not physically verified |
| VCARD_007 | SCENE_018_FV_ACTOR_02 (-12.15), SCENE_018_RESIDUAL_SUPPORT (-12.15) | timing blocked |
| VCARD_008 | SCENE_019_PHYS_01 (+14), SCENE_019_PHYS_02 (+15.8); SCENE_020_PHYS_01 (+59.4) | primary budget blocked; committed event not physically verified |
| VCARD_010 | SCENE_025_PHYS_02 (-6.3) | primary budget blocked |
| VCARD_012 | SCENE_030_PHYS_02 (-25); SCENE_031_RESIDUAL_SUPPORT (-11.85) | not physically verified; layout blocked |
| VCARD_013 | SCENE_032_PHYS_01 (+13.629), SCENE_033_PHYS_01 (+15.429), SCENE_033_PHYS_02 (+17.229) | layout blocked |
| VCARD_016 | SCENE_040_PHYS_02 (-25) | committed event not physically verified |
| VCARD_017 | SCENE_041_FV_ACTOR_02 (-53.029), SCENE_041_RESIDUAL_SUPPORT (-53.029) | timing blocked |

Three otherwise physically satisfied SCENE_007 events also exceed the preferred
four-frame error: PHYS_02 +4.771, PHYS_03/04 +4.8. These are audit findings, not
new invented log warnings. They require semantic/visual review before a fix is
chosen. No additional VISUAL_SENTENCE or AUDIO_VISUAL_ALIGNMENT log warning
was emitted. P6 direction/readability remains unclosed, not certified by its
text-event count.

### Next owner, without changing architecture in this checkpoint

Immediate failed product invariant: sustained source-visible underfill (P3).
Composition solver / scene-adaptive composition planning is the next owner to
inspect, using final projected visible ink and readable temporal population,
not bbox occupancy alone. The plan's median bbox coverage is 0.461810 while
estimated alpha coverage is 0.096002. A concurrency peak gate can pass despite
this sustained sparsity. The underlying deficit predates the WIP; normalized
occupancy and motion improved, although exact per-pass causality is not isolated.

Minimum generic direction to prove next: select source-backed per-phase
hierarchy/scale/layout candidates for actual visible-ink/readability deficits,
with full affected-lifetime collision certification. Do not force 24 handoffs,
move residual carriers independently, change thresholds, or apply global zoom.
P5 timing/coverage and P8 actor attribution remain separate pre-install blockers.
No production changes, full suite, commit, push, install, or Premiere launch were
performed while harvesting this completed run.
