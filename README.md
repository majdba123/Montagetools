# HEXA Video Builder — MontageTools

> Adobe Premiere Pro automation and media-processing system combining a Premiere extension, Python-based build tooling, semantic scene planning, layout constraints, motion QA, and render-validation workflows.

## Overview

MontageTools contains the **HEXA Video Builder** engineering workspace. The project focuses on turning structured scene packages and voice-over input into constrained video-editing plans for Adobe Premiere Pro while enforcing layout, motion, and visual-quality rules before final render validation.

The current V31 line was developed around a production problem that is common in automated video generation: a plan can be logically correct yet still fail visually because of object overlap, unsafe motion envelopes, oversized compound illustrations, white-stage artifacts, or dense scene composition.

The system therefore treats video construction as a constrained engineering pipeline rather than a sequence of unconstrained animation commands.

## Engineering Scope

The repository includes work around:

- Adobe Premiere Pro extension installation and integration;
- Python-based processing and installation payloads;
- semantic scene / role interpretation;
- phase-aware rectangle constraint solving;
- geometry-aware asset placement;
- motion-envelope validation;
- collision checks through time;
- sparse multi-phase scene composition;
- explicit relationship / cause-flow handling;
- image cutout and white-stage leak checks;
- deterministic geometry stress testing;
- build identity and release validation;
- runtime self-test and validation reports.

## Processing Model

A simplified view of the V31 workflow is:

```text
Scene Package + Voice Over
          │
          ▼
Semantic / Structural Analysis
          │
          ▼
Scene Grammar + Phase Planning
          │
          ▼
Geometry / Constraint Solver
          │
          ▼
Motion Envelope + Collision QA
          │
          ▼
Premiere Extension / Build Payload
          │
          ▼
Rendered MP4
          │
          ▼
Real Visual Validation
```

## Architecture Principles

### Constraint-based layout

Placement is based on actual object footprints, safe-frame boundaries, spacing requirements, and motion envelopes rather than only object center points.

### Motion-aware validation

The system samples configured motion behavior through time so a layout that is safe at its nominal frame is not automatically assumed to remain safe during animation.

### Sparse storytelling phases

Dense visual cards can be decomposed into a small number of staged visual states instead of displaying every available asset concurrently.

### Explicit relationships

Relationship motion is intended to represent relationships supported by structured metadata rather than being inferred only from visual proximity.

### Asset integrity

Compound illustrations are treated as indivisible assets unless an explicit, safe transformation path exists.

## Installation Entry Point

The repository includes a Windows launcher:

```text
bayer.bat
```

The launcher validates that the expected release payload exists, checks release identity against the current source commit, performs generated-artifact cleanup, and invokes the validated V31 installer payload.

The current installation flow targets an Adobe Premiere Pro 2022 workflow documented by the project materials.

## Quality & Validation

The repository contains runtime self-test, validation, patch-note, and execution-state artifacts associated with the V31 development line.

Internal validation is used to check implementation, geometry, cutout, release, and motion constraints. These checks are **not presented as proof of final visual parity by themselves**.

The project documentation explicitly keeps the final real-media gate separate:

> A real MP4 produced from the target scene package and voice-over is required before claiming reference-level visual parity.

That distinction is intentional: automated tests can validate engineering contracts, but final video quality still requires evaluation of the rendered media.

## Repository Notes

The default branch is currently named `old-final-package` because it preserves the validated project/package state used by the existing installation workflow. Renaming or restructuring release paths should only be done together with validation of the launcher and packaged references.

Generated render/build artifacts are excluded from source control through `.gitignore`. Environment files and local secrets are also ignored and should never be committed.

## Project Positioning

This repository demonstrates engineering work beyond standard web development, particularly in:

- media-processing automation;
- geometry and constraint solving;
- deterministic QA pipelines;
- Adobe Premiere workflow integration;
- Python automation;
- release/install tooling;
- production debugging of visual systems.

It complements my backend/full-stack portfolio by showing experience building and debugging a specialized media-processing system with strict correctness and visual-quality constraints.

## Portfolio

**Majd Bayer — Full Stack Software Engineer | Backend-Focused**  
Laravel · FastAPI · Next.js · REST APIs · System Design · Media Processing

Portfolio / Company: https://www.hexaterminal.com/en
