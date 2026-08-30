"""Bounded source-authoritative semantic beats for V1.1 packages."""
import re

_ACTIONS={'PRESENT','ENTER','TRANSFER','CONNECT','READ','COMPARE','INCREASE','DECREASE','BLOCK','REJECT','ACCEPT','REVEAL','REACT','RESOLVE'}
_NEG=re.compile(r'(?<!\w)(?:ما|لا|لم|لن|ليس|غير|NOT|NO|NEVER|WITHOUT)(?!\w)',re.I)

def normalize_scene_beats(scene, alignment=None):
    raw=scene.get('semantic_beats') or ([scene['semantic_beat']] if scene.get('semantic_beat') else [])
    text=((scene.get('script_span') or {}).get('text') or '')
    out=[]
    for i,b in enumerate(raw[:3],1):
        b=dict(b or {}); action=str(b.get('action') or b.get('type') or b.get('semantic_action') or 'PRESENT').upper()
        if action not in _ACTIONS: action='PRESENT'
        anchor=str(b.get('anchor_text') or b.get('phrase') or text).strip()
        if anchor and anchor not in text: anchor=text
        polarity=str(b.get('polarity') or ('NEGATED' if _NEG.search(anchor+' '+text) else 'AFFIRMED')).upper()
        if polarity=='NEGATED' and action=='ACCEPT': action='REJECT'
        row={'beat_id':f"{scene.get('scene_id')}::BEAT_{i:02d}",'scene_id':scene.get('scene_id'),'subject':b.get('subject'),'action':action,'object':b.get('object'),'result':b.get('result'),'polarity':polarity,'anchor_text':anchor,'source':'PACKAGE'}
        _align(row,scene,alignment);out.append(row)
    return out

def _align(beat, scene, alignment):
    interval=((alignment or {}).get('scene_intervals') or {}).get(str(scene.get('scene_id'))) or {}
    start=float(interval.get('start_seconds',interval.get('start',0.0)) or 0); end=float(interval.get('end_seconds',interval.get('end',start)) or start)
    words=(alignment or {}).get('word_timings') or []; anchor=beat['anchor_text']
    match=next((w for w in words if str(w.get('word') or w.get('text') or '') in anchor),None)
    hit=float(match.get('start_seconds',match.get('start',start)) if match else start)
    beat.update({'start_seconds':start,'perceptual_hit_seconds':hit,'end_seconds':end})
