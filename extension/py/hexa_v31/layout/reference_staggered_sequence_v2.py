from __future__ import annotations

"""Same-source-scene authority bridge for reference staggered sequencing.

The V1 finalizer correctly forbids unrelated cross-scene actors, but its early
phase-membership rejection can also reject two actors from the *same source scene*
when the story compiler placed them in adjacent/disjoint micro-phases.  Same-scene
source provenance is already accepted by the lower semantic-pair authority; this
bridge exposes that provenance as a temporary sequencing phase without changing the
persisted story plan or any P1/P2 timing.
"""

import copy

from . import reference_staggered_sequence as _v1

AUTHORITY = 'REFERENCE_SEMANTIC_STAGGERED_SEQUENCE_SAME_SCENE_V2'


def _same_scene_phase_groups(plan: dict, card: dict) -> list[dict]:
    cid = str(card.get('card_id') or '')
    by_scene: dict[str, list[str]] = {}
    for event in plan.get('events') or []:
        if event.get('suppressed_by_card_density'):
            continue
        if str(event.get('visual_card_id') or '') != cid:
            continue
        if str(event.get('render_mode') or 'ROOT_ATOMIC') != 'ROOT_ATOMIC':
            continue
        scene_id = str(event.get('scene_id') or '')
        event_id = str(event.get('event_id') or '')
        if not scene_id or not event_id:
            continue
        by_scene.setdefault(scene_id, []).append(event_id)
    groups=[]
    for scene_id,event_ids in sorted(by_scene.items()):
        ids=sorted(set(event_ids))
        if len(ids)<2:
            continue
        groups.append({
            'phase_id': f'{cid}::SAME_SOURCE_SCENE::{scene_id}',
            'event_ids': ids,
            'authority': AUTHORITY,
            'relationship_evidence': 'SAME_SOURCE_SCENE',
            'temporary_sequence_authority': True,
        })
    return groups


def finalize_reference_staggered_sequence(plan: dict, fps: float = 30.0) -> dict:
    cards = list((plan.get('visual_cards') or {}).get('cards') or [])
    originals=[]
    group_count=0
    try:
        for card in cards:
            phase_plan=card.setdefault('story_phase_plan',{})
            original=copy.deepcopy(phase_plan.get('phases') or [])
            originals.append((card,original))
            synthetic=_same_scene_phase_groups(plan,card)
            group_count+=len(synthetic)
            if synthetic:
                phase_plan['phases']=original+synthetic
        stats=_v1.finalize_reference_staggered_sequence(plan,fps=fps)
    finally:
        for card,phases in originals:
            card.setdefault('story_phase_plan',{})['phases']=phases
    stats=dict(stats)
    stats['authority_bridge']=AUTHORITY
    stats['same_scene_authority_phase_groups']=group_count
    return stats
