from __future__ import annotations
import pathlib,sys

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'extension/py'))

from hexa_v31.layout.reference_staggered_sequence import _related
from hexa_v31.layout.reference_staggered_sequence_v2 import _same_scene_phase_groups

card={
    'card_id':'CARD_GENERIC',
    'story_phase_plan':{
        'phases':[
            {'phase_id':'P1','event_ids':['A']},
            {'phase_id':'P2','event_ids':['B']},
        ]
    },
}
a={'event_id':'A','visual_card_id':'CARD_GENERIC','scene_id':'SCENE_GENERIC','render_mode':'ROOT_ATOMIC'}
b={'event_id':'B','visual_card_id':'CARD_GENERIC','scene_id':'SCENE_GENERIC','render_mode':'ROOT_ATOMIC'}
plan={'events':[a,b],'visual_cards':{'cards':[card]}}

# V1 phase gating rejects the pair despite legitimate same-source-scene evidence.
assert not _related(card,a,b)
synthetic=_same_scene_phase_groups(plan,card)
assert len(synthetic)==1 and set(synthetic[0]['event_ids'])=={'A','B'},synthetic
card['story_phase_plan']['phases'].extend(synthetic)
assert _related(card,a,b)

# Cross-scene unrelated actors remain forbidden; the bridge must not manufacture
# a relationship merely because two assets share a visual card.
c=dict(b,event_id='C',scene_id='OTHER_SCENE')
assert not _related(card,a,c)

print('V31_SAME_SCENE_SEQUENCE_AUTHORITY_PASS')
