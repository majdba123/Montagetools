from __future__ import annotations
import pathlib,sys

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'extension/py'))

from hexa_v31.design_director import _filter_title_copy

plan={
    'events':[
        {'text_id':'T1','scene_id':'S1','visual_card_id':'C1','text':'لكن في','typography_role':'HERO'},
        {'text_id':'T2','scene_id':'S2','visual_card_id':'C2','text':'قيمة التحويل','typography_role':'HERO'},
    ],
    'text_event_count':2,
    'title_qa':{'viewer_title_count':2,'machine_label_leak_count':0},
}
out=_filter_title_copy(plan)
assert [e['text_id'] for e in out['events']]==['T2'],out
assert out['text_event_count']==1 and out['title_qa']['viewer_title_count']==1,out
assert out['premium_title_copy_rejections'][0]['reason']=='WEAK_DISCOURSE_BOUNDARY',out
# Filtering is copy-on-write: caller-owned title plan remains intact.
assert len(plan['events'])==2 and plan['text_event_count']==2,plan
print('V31_PREMIUM_TITLE_COPY_GATE_PASS')
