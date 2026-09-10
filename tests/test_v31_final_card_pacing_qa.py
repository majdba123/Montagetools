from __future__ import annotations
import pathlib,sys

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'extension/py'))

from hexa_v31.motion.pacing_qa import build_final_card_pacing_report

cards=[
    {'card_id':'HEALTHY','start_seconds':0.0,'end_seconds':4.0},
    {'card_id':'FRONT','start_seconds':4.0,'end_seconds':9.0},
    {'card_id':'SLOW','start_seconds':9.0,'end_seconds':14.0},
]
events=[
    {'event_id':'H','visual_card_id':'HEALTHY','start_seconds':0,'end_seconds':4,'physical_start_seconds':0,'physical_end_seconds':4,
     'perceptual_hit_seconds':.55,'settle_seconds':.55,'preset_entry':{'start_seconds':.1,'duration_seconds':.45},
     'preset_actions':[{'start_seconds':2.0}],
     'composition_participant_states':[{'semantic_beat':'COMPOSITION_REBUILD','start_seconds':3.0}]},
    {'event_id':'F','visual_card_id':'FRONT','start_seconds':4,'end_seconds':9,'physical_start_seconds':4,'physical_end_seconds':9,
     'perceptual_hit_seconds':4.25,'settle_seconds':4.25,'preset_entry':{'start_seconds':4.0,'duration_seconds':.25},
     'preset_actions':[{'start_seconds':4.65}]},
    {'event_id':'S','visual_card_id':'SLOW','start_seconds':9,'end_seconds':14,'physical_start_seconds':9,'physical_end_seconds':14,
     'perceptual_hit_seconds':9.30,'settle_seconds':9.30,'preset_entry':{'start_seconds':9.0,'duration_seconds':.30}},
]
plan={'visual_cards':{'cards':cards},'events':events}
report=build_final_card_pacing_report(plan)
rows={row['card_id']:row for row in report['cards']}
assert rows['HEALTHY']['classification']=='HEALTHY',rows['HEALTHY']
assert rows['FRONT']['classification']=='FRONT_LOADED',rows['FRONT']
assert rows['SLOW']['classification']=='TOO_SLOW',rows['SLOW']
assert rows['FRONT']['static_tail_seconds']>4.0
assert rows['HEALTHY']['semantic_beat_count']>=3
assert report['review_required_count']==2,report
print('V31_FINAL_CARD_PACING_QA_PASS',report['class_counts'])
