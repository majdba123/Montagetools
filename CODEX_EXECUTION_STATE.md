# HEXA Execution State

## Mandatory visual authority
Before modifying visual storytelling, motion, composition, entry/exit behavior, text choreography, card continuity, or P3/P4 logic, read:

`ROUND4_REFERENCE_VISUAL_GRAMMAR.md`

That file is the Round 4 viewer-facing authority derived from the approved reference videos:
- `تأثير المتفرج2.mp4`
- `انحياز 2.mp4`
- `hallo 2(1).mp4`

The central requirement is progressive visual storytelling, not static-poster motion. Elements enter when needed, remain readable, then exit/fade/shrink/become secondary before unrelated new ideas take focus. Characters are actors, not permanent decoration. Icons build progressively. Relationships appear after their endpoints. Text is short/contextual and leaves with its idea. Adjacent cards should use meaningful visual handoffs when appropriate.

## Protected engineering state
- Canonical branch: `chatgpt/p0-visual-lifetime-partition-fix`.
- P1 CLOSED/PROTECTED.
- P2 CLOSED/PROTECTED; cause/object must remain before reaction/subject.
- P3/P4 remain open until actual encoded MP4 inspection proves closure.
- Do not weaken collision, safe-frame, viewport, physical-overlap, or P1/P2 gates merely to make tests pass.
- Same-scene unresolved collisions remain hard failures.
- Ordered cross-scene overlap may only use the established final exact-lifetime handoff authority.

## Production validation doctrine
Do not call a visual feature complete because planner JSON or CI looks correct.

Required proof order:
`tests → CI → real motion preflight → real render → encoded MP4 inspection → human/reference comparison`

Encoded pixels and the human viewing result are the final visual authority.

## Current workflow
- Use the existing BALANCE_LIMIT Vision/Foundation cache; do not unnecessarily regenerate it.
- Use `python -m hexa_v31.cli motion-preflight` before an expensive full render.
- Do not ask the user for a full render while motion preflight still fails.
- After preflight PASS, render the real project and compare it against all three approved references using the Round 4 grammar.

## Current CI note
The `codex round3` head `1bdb941289fbb1251fdc833494cc8b8279117975` failed the deterministic suite at final physical certification because of a `VCARD_009` motion-path overlap. Round 4 visual authority was added afterwards and must not be mistaken for a fix to that production/test failure.
