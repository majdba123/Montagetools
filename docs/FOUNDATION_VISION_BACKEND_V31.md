# HEXA V31 Foundation Vision backend

## Root cause and baseline

At baseline `f1b73fc23181fd271a8a6e67d2136addb3349a36`, scene actorization begins in `vision.analyze_scene`. It can partition detached foreground components, color regions, and topology-supported children, but it has no semantic region proposer or promptable object mask backend. Connected illustrations therefore reach the physical-unit list as one root/group even when the artwork contains several meaningful objects. Motion consumes that list unchanged; it cannot address an object that Vision never emitted. The historical `subobject_cutouts=0` diagnostic is therefore a missing discovery/mask path, not a choreography defect.

## Production path

`pipeline.build` runs legacy CV first. Only an under-decomposed scene is sent to one persistent isolated worker. Florence-2 combines object detection, dense-region captioning, region proposals, and optional phrase grounding. Candidate fusion rejects duplicates and decorative fragments. SAM 2.1 receives accepted boxes and returns multiple mask hypotheses; selection combines SAM score and physical bbox agreement. HEXA then performs mask validation, its existing white-stage matting, conservative occlusion classification, actor QA, and writes the accepted actors into the existing `PhysicalUnit`-compatible `units` list. The root representation remains a fallback, while two or more validated foundation actors form the downstream `CHILD_PARTITION`.

The worker environment and model directory are outside Git under the V31 LocalAppData runtime. Setup provisions pinned dependencies and revisions once. BUILD forces Hugging Face/Transformers offline mode. Initialization, checkpoint, or inference failure is logged and returns to the unchanged legacy CV path.

## Performance

Model loading is amortized across BUILD. The quality profile is GPU-memory-bound during load and GPU-bound during inference when supported; CPU fallback is memory-bound and CPU-bound. Florence and SAM stages report separate durations. Scenes already safely decomposed incur no foundation inference.

## Real-model testing

Normal tests use deterministic mocked Florence/SAM results and never download weights. `tests/optional_test_v31_foundation_real_models.py` is opt-in for a separately provisioned certification machine. Model installation alone is not an end-to-end quality certification.
