import json, pathlib, tempfile
import cv2
import numpy as np
from types import SimpleNamespace

from hexa_v31.preset_story_planner import _commit_beat_focus_emphasis
from hexa_v31.preview import _preset_event_state
from hexa_v31.typography import build_text_plan
from hexa_v31.visual_choreography import visual_choreography_qa
from hexa_v31.physical_acting_verify import verify_physical_acting

cards={'cards':[{'card_id':'C1','start_seconds':0.,'end_seconds':4.},{'card_id':'C2','start_seconds':4.,'end_seconds':8.}],'scene_to_card':{'S1':['C1','C2']}}
event={'event_id':'E1','visual_card_id':'C2','attention_priority':'PRIMARY','start_seconds':4.,'end_seconds':8.,'perceptual_hit_seconds':4.,'same_scene_persistence_state':True,'lifecycle_state_only':True,'focus_beats':[]}
stats=_commit_beat_focus_emphasis([event],cards,30.)
assert stats['committed']==1 and event['focus_beats'][0]['scale_peak']==1.12
render_event=dict(event,object_rest_position_px=[960,540],sequence_width=1920,sequence_height=1080,preset_coordinate_mode='ABSOLUTE_OBJECT_CENTER',preset_entry={'name':'APPEAR_HIGH_SCALE','start_seconds':4.,'duration_seconds':.8})
state=_preset_event_state(render_event,event['focus_beats'][0]['peak_seconds'])
assert state and state[1]>=1.05 and state[0]==(960.,540.)

scene={'scene_id':'S1','script_language':'ar','script_span':{'text':'يظهر الحد بوضوح ثم يرفض الطلب فوراً'},'units':[
 {'unit_id':'U1','type':'STATUS','role':'PRIMARY','narrative_function':'REVEAL','focus_trigger':{'phrase':'يظهر الحد بوضوح','global_char_start':0,'global_char_end':15}},
 {'unit_id':'U2','type':'STATUS','role':'PRIMARY','narrative_function':'REJECT','focus_trigger':{'phrase':'يرفض الطلب فوراً','global_char_start':20,'global_char_end':37}}]}
alignment={'scene_timings':[{'scene_id':'S1','start':0.,'end':8.}],'word_timings':[{'char_start':0,'char_end':15,'start':1.,'end':1.7},{'char_start':20,'char_end':37,'start':5.,'end':5.8}]}
plan=build_text_plan(SimpleNamespace(plan={'scenes':[scene]}),alignment,[{'scene_id':'S1','units':[]}],{'visual_cards':cards})
assert len(plan['events'])==2 and {x['visual_card_id'] for x in plan['events']}=={'C1','C2'}
assert plan['hard_rules']['max_one_primary_text_event_per_visual_card']
assert all(x['start_seconds']<=x['impact_seconds']<=x['end_seconds'] for x in plan['events'])

profile=json.loads((pathlib.Path(__file__).parents[1]/'extension/resources/HEXA_CREATIVE_REFERENCE_PROFILE_V31.json').read_text(encoding='utf-8'))
bad_report={'cards':[{}]*28,'static_poster_risk_count':0,'low_optical_impact_count':9,'fade_only_transition_count':15,'transition_classification_counts':{'FADE_ONLY':15,'SCALE_REVEAL':21},'progressive_reveal_count':30,'effect_family_diversity':0,'within_frame_recomposition_count':0,'motion_units':[{'entry_preset':'APPEAR_HIGH_SCALE'}]*12}
qa=visual_choreography_qa(bad_report,{'duration_seconds':99.1667,'meaningful_change_gap_p90_seconds':3.5,'low_motion_percent':84.9025},profile)
assert not qa['pass'] and not qa['gates']['effect_family_diversity']['pass']

with tempfile.TemporaryDirectory() as td:
    p=str(pathlib.Path(td)/'static.mp4');writer=cv2.VideoWriter(p,cv2.VideoWriter_fourcc(*'mp4v'),10.,(160,90))
    for _ in range(20):writer.write(np.full((90,160,3),255,np.uint8))
    writer.release();result=verify_physical_acting(p,{'motion_dna_version':'USER_PRESET','events':[],'scenes':[]})
    assert result['planned_physical_actions']==0 and not result['pass']
print('V31_CREATIVE_QUALITY_RECOVERY_PASS')
