from pathlib import Path

from hexa_v31.motion import build_motion_plan
from hexa_v31.preset_qa import preset_motion_qa
from hexa_v31.preset_story_planner import _commit_startup_establishing_state


ROOT = Path(__file__).resolve().parents[1]


def unit(uid, role, cx, kind="CONCEPT"):
    return {
        "physical_id": "PHYS_" + uid,
        "semantic_unit_id": uid,
        "semantic_type": kind,
        "semantic_role": role,
        "center_norm": [cx, 0.5],
        "bbox_norm": [cx - 0.04, 0.43, 0.08, 0.14],
        "hierarchy_level": 0,
        "translation_safe_after_occlusion": True,
        "animation_safe": True,
        "composition_slot_id": uid,
        "semantic_mapping_confidence": 0.99,
    }


scene = {
    "scene_id": "GENERIC_LONG_SCENE",
    "units": [
        {"unit_id": "MAIN", "semantic_name": "generic", "type": "CONCEPT", "role": "PRIMARY"},
        {"unit_id": "A", "semantic_name": "a", "type": "ICON", "role": "SUPPORTING"},
        {"unit_id": "B", "semantic_name": "b", "type": "ICON", "role": "SUPPORTING"},
        {"unit_id": "C", "semantic_name": "c", "type": "ICON", "role": "SUPPORTING"},
    ],
    "visual_progression": [],
    "relation_to_previous": "START",
    "script_span": {"global_char_start": 0, "global_char_end": 12, "text": "generic text"},
}
plan = {"project_id": "GENERIC_V11_LONG", "scenes": [scene]}
alignment = {
    "method": "TEST",
    "scene_count": 1,
    "scene_timings": [{"scene_id": scene["scene_id"], "start": 0.0, "end": 11.16}],
    "word_timings": [{"word": "generic", "start_seconds": 2.5, "end_seconds": 2.8}],
}
vision = [{
    "scene_id": scene["scene_id"],
    "mode": "CLEAN_LAYERED",
    "foreground_fraction": 0.23,
    "raw_component_count": 4,
    "grouped_detail_count": 4,
    # One physically certified root exercises the opening establishing-state
    # repair. Supporting detail remains grouped in the source asset rather
    # than being fabricated as independent motion units.
    "units": [unit("MAIN", "PRIMARY", 0.50)],
}]

motion = build_motion_plan(
    plan,
    alignment,
    vision,
    ROOT / "extension/resources/HEXA_EDITING_RULES_V20.json",
    ROOT / "extension/resources/HEXA_REFERENCE_QA_PROFILE_V20.json",
)
cards = motion["visual_cards"]["cards"]
assert len(cards) == 3
assert all(3.0 <= float(card["duration_seconds"]) <= 5.0 for card in cards)
assert isinstance(motion["visual_cards"]["scene_to_card"][scene["scene_id"]], list)

carry = [event for event in motion["events"] if event.get("lifecycle_state_only")]
assert len(carry) == 2
assert all(event.get("same_scene_persistence_state") for event in carry)
assert all(event.get("source_event_id") and event.get("visual_instance_id") for event in carry)
assert all(not event.get("preset_entry") and not event.get("preset_exit") and not event.get("preset_actions") for event in carry)
assert len({event["visual_instance_id"] for event in carry}) == 1

# Directly exercise the one-object startup gap found by the real V1.1 build.
startup = dict(next(event for event in motion["events"] if event.get("attention_priority") == "PRIMARY" and not event.get("lifecycle_state_only")))
startup.update({"visual_card_id": cards[0]["card_id"], "start_seconds": 2.0,
                "end_seconds": cards[0]["end_seconds"], "perceptual_hit_seconds": 2.56,
                "perceptual_hit_source": "VOICE_TRIGGER",
                "preset_entry": {"name": "APPEAR_HIGH_SCALE", "start_seconds": 2.0, "duration_seconds": 0.8}})
startup_result = _commit_startup_establishing_state([startup], {"cards": [cards[0]]}, 30.0)
assert startup_result["committed"] is True, startup_result
assert startup["perceptual_hit_source"] == "SOURCE_BACKED_EDITORIAL_ESTABLISHING_STATE"
assert startup.get("preserved_semantic_anchor_seconds") == 2.56

qa = preset_motion_qa(motion)
assert qa["pass"], qa["failures"]
print("V31_V11_LONG_SCENE_RELEASE_PASS", len(cards), len(carry))
