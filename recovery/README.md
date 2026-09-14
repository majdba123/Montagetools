# HEXA Recovery System

This directory owns recovery problem identity and version-controlled recovery knowledge access. Production motion/layout code may implement bounded candidate strategies, but this layer controls when a strategy is allowed to become reusable knowledge.

## Required lifecycle

1. Detect a problem from CI or encoded-render review.
2. Map it to a stable `problem_id` and reusable fingerprint. Instance ids, scene ids, card ids, package names, and timestamps are diagnostic metadata only.
3. Look for a matching solution in `../recovery_data/proven_solutions.json`.
4. If no proven solution exists, fail/report the problem and implement a generic candidate fix.
5. Run targeted tests and the full CI suite.
6. Render the exact candidate source commit to an encoded MP4.
7. Review the encoded video against the visual requirements/reference quality.
8. Promote the solution to `PROVEN` only when both technical and visual approval pass.

CI success alone is never learning authority. `RecoveryMemory.record()` is intentionally non-learning; only visually proven version-controlled rows may influence future strategy ranking.

## Data ownership

`../recovery_data/problem_registry.json` defines stable problem identities.

`../recovery_data/proven_solutions.json` contains only technically and visually proven reusable solutions.

`../recovery_data/recovery_history.json` contains incidents/candidates, including rejected or render-pending work.

`../recovery_data/recovery_schema.json` defines promotion and fingerprint rules.

The release builder copies the root recovery data into the shipping extension payload as a read-only runtime snapshot. The root files remain the source authority and are updated through normal Git commits.
