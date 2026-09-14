# ROUND 4 — REFERENCE VISUAL GRAMMAR

## Status
This document is the viewer-facing visual authority for Round 4 and later visual-quality work on HEXA V31.

Any future engineer, Codex session, or ChatGPT session working on the visual output must read this file before changing motion/story behavior.

This authority was derived from the three approved reference videos:

- `تأثير المتفرج2.mp4`
- `انحياز 2.mp4`
- `hallo 2(1).mp4`

The goal is **not** to copy their literal artwork or exact timings. The goal is to reproduce the same visual storytelling grammar: progressive construction, readable focus, meaningful entry/exit, and continuous composition change.

---

## 1. Core principle

The video must not behave like a static poster.

A scene is a sequence of visual beats, not a collection of PNGs placed on screen at once.

Preferred visual sequence:

`ENTER → READ → ADD → RELATE → RESULT → RELEASE`

In plain language:

1. Show the main idea.
2. Give the viewer a moment to understand it.
3. Add the next supporting element.
4. Show the relationship between the elements.
5. Reveal the result or conclusion.
6. Remove, reduce, or hand off old elements before the next idea takes focus.

---

## 2. Element lifecycle

Every important character, icon, label, and diagram element must have a reason to be on screen.

### Required behavior
- Elements should enter when their idea becomes relevant.
- They should remain readable long enough to be understood.
- They should leave, fade, shrink, or move into a support role when their idea is finished.
- Old elements must not remain full-size and full-focus while unrelated new ideas accumulate.
- The composition should visibly evolve during narration.

### Good example
A character enters → an icon appears beside them → an arrow appears → a result icon appears → the first icon fades or exits → the result becomes the new focus.

### Bad example
Character + three icons + arrow + text all appear together and remain unchanged for several seconds.

---

## 3. Focus and hierarchy

At most times, the viewer should immediately know what to look at.

### Required behavior
- Prefer one clear hero/focus element at a time.
- Supporting elements may remain, but they must visually step back when focus transfers.
- A new hero should take focus only after the old hero has begun to release focus.
- Focus transfer should feel intentional, not like unrelated objects appearing beside each other.

### Three valid handoff styles
1. **Exit handoff** — old hero exits, new hero enters.
2. **Retained-context handoff** — old hero becomes smaller/secondary while new hero takes focus.
3. **Ghost handoff** — old composition fades/greys/blurs while the incoming element becomes sharp and prominent.

---

## 4. Characters

Characters are story actors, not permanent decoration.

### Required behavior
- A character appears when they have a narrative purpose: explain, react, point, compare, think, receive a result, or connect ideas.
- Characters may disappear completely during diagram/icon-only passages.
- Reusing the same character is acceptable when the pose/function changes.
- Pose changes are useful visual beats.
- Do not keep the same character PNG parked on one side of the screen throughout the video.

### Example
Character enters and points at a problem → problem icon takes focus → character exits → diagram explains the process → character returns later in a reaction pose.

---

## 5. Icons and diagrams

Icons should normally build progressively.

### Required behavior
- Introduce related icons one at a time or in small readable groups.
- Do not reveal the entire diagram before the narration explains it.
- The main element should usually appear before arrows, checks, crosses, labels, or result markers.
- Result/support icons should appear later than the cause or subject they explain.

### Example
Main object → second object → arrow → check/cross/result.

Not:
Main object + second object + arrow + result all at the same instant.

---

## 6. Relationships and arrows

Relationship graphics are semantic events, not decoration.

### Required order
`A appears → B appears → relationship appears`

The arrow/line/check/cross should clarify a relationship that the viewer has already had a chance to see.

Do not show relationship graphics before their endpoints are readable.

---

## 7. Motion style

The references use simple motion, but use it at the right moment.

### Preferred motion vocabulary
- directional slide from left/right/top/bottom when spatially logical;
- short scale/pop for important symbols or results;
- fade plus slight scale for secondary elements;
- motion blur during faster transitions when appropriate;
- staggered appearance for groups;
- clean exit or fade for finished elements;
- composition shift when focus changes.

### Avoid
- movement with no narrative reason;
- every element entering from the same direction;
- every card using the same animation recipe;
- excessive bouncing or theatrical motion;
- tiny technical movement that is practically invisible to the viewer;
- strong movement that distracts from narration.

---

## 8. Timing feel

The references feel alive because there is frequent meaningful visual change.

The target is not a rigid numeric schedule. The viewer should usually receive a meaningful visual beat roughly every one to two seconds during active explanation.

A visual beat can be:
- an element entering;
- an old element leaving;
- a pose change;
- a label appearing;
- an arrow/relation appearing;
- a focus shift;
- a scale emphasis;
- a composition rebuild;
- a cross-card handoff.

A visual beat must add meaning. Random motion does not count.

---

## 9. Text

Text is part of the visual composition, not a transcript dumped on screen.

### Required behavior
- Keep text short and readable.
- Prefer one phrase, keyword, label, or short sentence.
- Use strong hierarchy and clear contrast.
- Position text near the idea it explains.
- Remove old text when its idea is finished.
- Text may appear in chunks as the idea develops.
- Do not accumulate multiple old labels across successive ideas.

### Avoid
- paragraph-like captions as the main visual language;
- tiny text;
- long text that competes with narration;
- text appearing before the visual idea it labels;
- permanent old text remaining after focus changes.

---

## 10. Composition variety

Do not use one repeated layout for the whole video.

Valid compositions include:
- character left + diagram right;
- character right + diagram left;
- centered hero;
- two-object comparison;
- title above + elements below;
- diagram-only scene;
- icon sequence without a character;
- large visual metaphor occupying most of the frame;
- retained old element on one side while a new hero takes the other side.

The layout should follow the idea, not a fixed template.

---

## 11. Scene and card continuity

Cards should not feel like isolated slides restarting from zero.

### Required behavior
- Use clean visual handoffs when adjacent ideas are related.
- Retain an element across the boundary only when it helps continuity.
- A retained element must become secondary if the next card has a new focus.
- It is acceptable for a card to clear the frame when a clean reset is the best storytelling choice.
- Avoid repeated full fade-out → blank white → full fade-in when a meaningful handoff is possible.

---

## 12. Cause and reaction

For reaction stories, preserve the human reading order:

`cause/object → reaction/subject`

The reaction must not visually precede its cause.

This is both a visual-storytelling rule and a protected P2 requirement.

---

## 13. What makes the references feel professional

The reference videos are not strong because they contain many effects.

They are strong because:

1. elements appear only when needed;
2. the frame changes while narration develops;
3. one idea normally owns focus;
4. old ideas release focus before new ones dominate;
5. arrows/results arrive after their causes;
6. characters are used selectively;
7. layouts change according to the story;
8. the viewer can understand the scene without feeling visually overloaded.

---

## 14. Primary anti-pattern: STATIC POSTER

A render must be considered visually wrong when it repeatedly behaves like this:

`character + icons enter → all remain fixed → narration continues → card ends`

Even if every individual asset is technically animated during its first few frames, the scene is still a static poster if the composition does not evolve afterwards.

The desired behavior is:

`hero enters → hold → support enters → relationship appears → result enters → focus changes → old content releases → next idea takes over`

---

## 15. Round 4 acceptance questions

When reviewing the encoded MP4, answer these as a normal viewer:

1. Does each scene visibly develop instead of appearing all at once?
2. Do old characters/icons leave or become secondary when they are no longer needed?
3. Is there a clear main focus at most moments?
4. Do arrows/relationships appear after the related objects?
5. Does the result arrive after the setup instead of too early?
6. Do characters disappear when a diagram can carry the explanation better?
7. Does the composition rebuild as the explanation progresses?
8. Are entry directions and animation types varied enough to avoid repetition?
9. Is text short, large, contextual, and removed when finished?
10. Do connected cards hand off visually instead of always restarting from zero?
11. Does cause appear before reaction?
12. Does the whole video feel actively edited rather than automatically arranged?

If the answer to several of these is no, Round 4 is not visually complete even if unit tests and CI are green.

---

## 16. Proof hierarchy

Visual quality is certified from the actual encoded video, not from planner JSON alone.

Use this proof order:

`tests → CI → real motion preflight → real render → encoded MP4 inspection → human/reference comparison`

CI green is necessary but is not visual proof.

The final authority for P3/P4 remains the encoded pixels and human viewing result.
