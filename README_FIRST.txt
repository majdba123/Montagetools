HEXA VIDEO BUILDER V31.0.20
AUDIO SEMANTIC DESIGN DIRECTOR

STATUS: TEST CANDIDATE — REAL MP4 REQUIRED FOR REFERENCE PARITY CLAIM

INSTALL
1. Double-click bayer.bat in the repository root.
2. Wait for: HEXA INSTALL COMPLETE.
3. Open Premiere Pro 2022 and select HEXA Video Builder V31.
4. Use the exact same HEXA Scene Package ZIP + Final Voice Over used for V30.


V31.0.1 REAL-BUILD RECOVERY
The first V31.0.0 Windows run completed alignment and all 49/49 vision scenes, then stopped at VCARD_013 because the phase-aware solver had no legal candidate under fixed role anchors. V31.0.1 fixes that failure class generically with co-occurrence decomposition, geometry-adaptive fallback anchors, fit-derived scale candidates, atomic-phase sanitation, and adaptive phase repacking.

V31.0.9 AUDIO SEMANTIC DESIGN DIRECTOR
V31.0.9 adds voice-aligned semantic-hit auditing, separate exact-copy Arabic/English title
layers, title-safe placement, explicit-only relationship graphics, duplicate-role detection,
and progressive-reveal/optical-balance reports while preserving the 31.0.3 composition guards.

WHY V31 EXISTS
The real V30 MP4 proved that motion alone was not enough. The visible failures were:
- independent icons/illustrations could overlap or visually enter each other;
- large compound illustrations could be packed beside other large elements;
- the plan could be collision-free at nominal size but the Appearance preset holds at ~110%, producing pixel-level overlap;
- raw PRFPSET position values were treated as normalized Program Monitor coordinates, which could push within-frame motion too far;
- the Disappearance preset was interpreted as a huge downward translation even though the supplied visual example is scale/opacity-dominant;
- a conservative white-background group could retain a border-connected white stage pocket as opaque alpha, creating rectangular white seams when moved;
- explicit relationships and general layout motion were not separated strongly enough;
- dense visual cards showed too many independent objects at once instead of telling the story in sparse phases.

V31 PRODUCTION ARCHITECTURE
- Universal Scene Grammar: structural archetypes are inferred from semantic roles/explicit graph edges, never from this project's script text or scene IDs.
- Phase-Aware Rectangle Constraint Solver: placement uses actual object footprint, safe-frame boundaries and hard spacing, not point centers.
- Joint Layout + Motion QA: exact supplied preset curves are sampled and collision-checked through time before render.
- Motion Envelope Layout: the held ~110% Appearance scale is reserved during layout, preventing the old plan-vs-pixels mismatch.
- Atomic Asset Indivisibility: compound illustrations stay intact and may coexist when their exact envelopes are safe.
- Sparse Story Phases: cards evolve through 1–3 visual states instead of stacking all available assets.
- Explicit Relationship Storytelling: cause/flow cards stage source -> target handoffs; relationship motion is allowed only with explicit metadata + >=0.85 physical mapping confidence + safe preset geometry.
- Unsafe relationship travel becomes temporal handoff; it is never invented from proximity.
- User Visual Sample Calibration: within-frame endpoints are calibrated to the supplied sample videos; raw PRFPSET values remain stored only as audit data.
- Disappearance execution uses the supplied sample's scale/opacity behavior without the previously misinterpreted full-frame downward throw.
- Top-Level Cutout Lock: no speculative sub-object slicing is permitted.
- Local White-Stage Leak Repair: border-connected white stage trapped inside a group is made transparent while enclosed white object interiors stay opaque.
- Opaque Stage Leak Hard Gate: remaining opaque white-stage contamination rejects the pre-render plan.
- No full-frame crossfade, white wash, arbitrary drift, synthetic motion blur, mask wipe, or invented arrows.

USER HARD RULES PRESERVED
- 3–5 second visual cards.
- 1–2 primary elements maximum concurrently.
- 3–8 supporting visual details remain the target density.
- Entry/Exit family is primary-only.
- Within-frame family is allowed for any element when geometry is physically safe.
- Appearance is preferred for secondary elements and used for primary only when necessary.
- Disappearance is available to any element.

GENERALIZATION CONTRACT
There are no payment/balance/wallet/current-scene special cases in the V31 composition/motion path.
The same grammar/solver path is used for comparison, character explanation, cause/effect, blocker, flow/pipeline, hub-and-spokes and single-focus content.
The shipping test suite includes deterministic geometry stress across all supported archetypes.

REAL QUALITY GATE
Internal tests prove code/geometry/cutout/preset contracts. They do NOT prove 8/10 reference parity.
The decisive gate remains the actual V31 MP4 rendered from the same real package/voice and compared against the locked reference videos.
