# P1-P4 closure checkpoint

Only branch: `chatgpt/p0-visual-lifetime-partition-fix`.
Never reset or use `old-final-package`.

## Frozen base before this continuation

Base commit: `365f17f85d7ec10fdd6d5608dd9790f0bc6d066c`.
Exact-head CI #186 / run `34267560460`: fully green, including deterministic suite,
shipping build/install, Foundation smoke, interaction production certification, and
Premiere host contract.

Astra's base work remains protected:
- readable retained context (no ghost tails)
- semantic-slot root fitting
- geometry/role/source-ink hierarchy amplitude
- card-clock + physical-clock collision certification
- P1/P2, partition atomicity, translation safety, renderer and seal unchanged

## Latest encoded evidence on base 365f17f8

Canonical run:
`HEXA_INSUFFICIENT_BALANCE_AR_V31_0_25_20260908-223607-deb486aa.mp4`

Normalized comparison remains `4 Hz / 320x180`.

Measured approximately:
- occupancy mean: 19.72%
- occupancy median: 20.17%
- frames <10%: 10.58%
- frames <15%: 34.26%
- motion mean: 10.27%
- motion median: 7.65%
- near-static: 32.58%

The commit cleaned false/ghost density but did not produce the required global jump.
P1 CLOSED / protected.
P2 CLOSED / protected.
P3 OPEN.
P4 OPEN.

Persistent sparse evidence remains around 73.5-78.25s and several shorter blocks.
These timestamps are diagnostics only and MUST NOT become implementation special cases.

## ChatGPT continuation after Astra limit

The next root cause was the one Astra already identified:
independent fitting cannot use layouts that require moving focal + context together.

New production stage:
`extension/py/hexa_v31/layout/reference_joint_fitter.py`

Architecture:
- only already-source-backed unsuppressed `ROOT_ATOMIC` actors
- exactly a semantic PRIMARY + SUPPORTING context pair
- same visual card and either same source scene or shared authored story phase
- requires sustained underfill / source-ink deficit
- requires >=0.55s physical coexistence
- no position-authored actors
- no partition children/residuals
- no new pixels, IDs, timestamps, narration-specific rules, or package-specific logic
- preserves the pair's existing horizontal/vertical ordering
- uses existing semantic layout destinations plus a bounded two-actor coordinated fit
- pair scale ladder is derived from the existing source-ink role targets/caps
- static settled destination only; never camera drift or position animation
- every candidate passes existing card-clock + physical-clock collision/composition QA
- commit requires material pair-ink gain AND material card underfill/mean-ink gain
- full density monotonicity remains mandatory
- on any failure the pair is atomically rolled back

After a successful joint fit, the stage gives existing later-source semantic reveals one
bounded re-evaluation through the existing semantic continuation compiler. This is not
idle motion; it only creates a state if the real authored reveal and full QA allow it.

Pipeline order is now:
interaction
-> source-backed density topology
-> reference geometry
-> coordinated primary/context joint geometry
-> stable perceptual seal
-> final interaction/lifetime certification if any stage changed

Stats are stored as:
`reference_joint_geometry_finalizer`

## Generalization regression

`tests/test_v31_reference_joint_fitter.py` verifies:
- coordinated focal/context fitting materially reduces sparse-card underfill
- actor order remains preserved
- static destinations are not marked position-animated
- different IDs and narration durations produce the same normalized geometry
- two competing primaries are rejected
- position-authored actors are rejected
- unrelated scenes in separate story phases are rejected

The regression is included in `tests/run_v31_test_suite.py`.

## Acceptance remains unchanged

P3 closure requires canonical encoded evidence:
- occupancy mean >=24-26%
- median >=20%
- <10% <=8%
- <15% <=25%
- zero illegal sustained viewport clipping

P4 closure requires a material encoded motion/recomposition jump toward the
14.5-17.9% reference regime, with semantic attribution and no drift/jitter cheat.

This batch is an architectural candidate, NOT encoded closure proof.

## Resume / next action

1. Verify exact-head CI for the commit containing this handoff.
2. If CI fails, fix the owning production cause; never weaken guards.
3. If CI is fully green, install that exact HEAD and run the canonical BALANCE_LIMIT replay.
4. Measure encoded pixels at `4 Hz / 320x180`.
5. If P3/P4 still miss floors, inspect `reference_joint_geometry_finalizer` stats first:
   requested/evaluated/committed pairs, rejection reasons, underfill before/after,
   and post-joint semantic commits.
6. Continue generalized engineering only. Do not open P5/P6/P7.

Canonical package SHA256:
`6abda3a85214305e37ab4b533cdb23b522607e631c68e70d54438ca8cb145535`

Canonical audio SHA256:
`6332a4da17261e4a05ca7f5206370f372f31c72764cbc531e972d8c985d7a030`
