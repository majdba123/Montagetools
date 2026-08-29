# HEXA Execution State

- Architecture: `pipeline.build` validates the frozen package, aligns voice, reconstructs scenes, then calls `motion.build_motion_plan` (the V31 preset story planner), semantic audit/title planning, scene-media render, Premiere handoff, and production certification.
- Authorities: user preset map and editing-rules JSON; `preset_story_planner.py` owns legal deterministic choreography; `design_director.py` owns the post-plan semantic audit and title accounting.
- Confirmed problem: V31.0.25 has rich `preset_actions`, but the story-lock audit only grants physical credit for entry readability and must be checked against the exact package/voice. Coverage gates must not be relaxed.
- Inputs found: extracted balance package and exact voice under `C:\Users\INTEL CENTER\Desktop\content\VideoFolder\BALANCE_LIMIT` (the requested zip itself was not located).
- Chosen changes: semantic audit now consumes the committed `semantic_events` ledger and verifies the linked preset entry; this preserves the coverage thresholds and does not grant passive credit.
- Commands: targeted Python tests via `PYTHONPATH=extension/py`; production CLI via `python -m hexa_v31.cli build`.
- Current test/build state: `test_v31_semantic_ledger_accounting`, `test_v31_semantic_mapping_guard`, `test_v31_0_25_motion_interaction_director`, and Python compile pass. Exact production build `20260829-220750-b778eecb` is actively processing forced alignment.
- Blockers: real build has not yet reached the semantic lock/render stage; installer and Premiere follow only after that result.
