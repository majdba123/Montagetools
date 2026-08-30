"""Bounded source-authoritative semantic beats for V1.1 packages."""
import re

_ACTIONS={'PRESENT','ENTER','TRANSFER','CONNECT','READ','COMPARE','INCREASE','DECREASE','BLOCK','REJECT','ACCEPT','REVEAL','REACT','RESOLVE'}
_NEG=re.compile(r'(?<!\w)(?:ما|لا|لم|لن|ليس|غير|NOT|NO|NEVER|WITHOUT)(?!\w)',re.I)
_DERIVE=(
 ('READ',r'(?i)\b(?:read|check|inspect|scan)\b|يقرأ|قرأ|فهم|يفهم|يراجع|مراجعة|يتحقق|فحص'),
 ('COMPARE',r'(?i)\b(?:compare|versus|difference)\b|يقارن|مقارنة|الفرق|أكبر من|أقل من|مقابل|لكن'),
 ('REJECT',r'(?i)\b(?:reject|fail|invalid|deny)\b|يرفض|رفض|تنرفض|مرفوض|لا يسمح|ما يسمح|ما تقدر|ما راح'),
 ('BLOCK',r'(?i)\bblock\b|يمنع|محجوز|حد|حدود|يتوقف|مقطوع'),
 ('TRANSFER',r'(?i)\b(?:send|move|transfer)\b|وصل|يصل|يرسل|يخرج|ينتقل'),
 ('CONNECT',r'(?i)\b(?:connect|link)\b|متصل|يربط|يوزع|قنوات|مسارات'),
 ('DECREASE',r'(?i)\b(?:decrease|reduce)\b|ينقص|تخفيض|أخذت جزء|أقل'),
 ('INCREASE',r'(?i)\b(?:increase|raise)\b|يرفع|رفع|يزيد'),
 ('REVEAL',r'(?i)\b(?:show|reveal)\b|يظهر|تشوف|واضح|يوضح'),
 ('REACT',r'(?i)\b(?:think|react)\b|يظنون|يعتقد|يتفاعل'),
 ('RESOLVE',r'(?i)\b(?:solution|resolve)\b|الحل|استخدام وسيلة ثانية'),)

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
    # A singular package beat may expose up to two earlier, literal action anchors.
    if len(out)==1:
        for action,pat in _DERIVE:
            m=re.search(pat,text)
            if not m or action==out[0]['action']: continue
            row=dict(out[0],beat_id=f"{scene.get('scene_id')}::BEAT_{len(out)+1:02d}",action=action,anchor_text=m.group(0),source='DERIVED_FROM_PACKAGE')
            _align(row,scene,alignment)
            if row.get('_aligned'):out.append(row)
            if len(out)>=3:break
        out.sort(key=lambda x:x['perceptual_hit_seconds'])
        for i,b in enumerate(out,1):b['beat_id']=f"{scene.get('scene_id')}::BEAT_{i:02d}"
    for i,b in enumerate(out):
        b['start_seconds']=b['perceptual_hit_seconds'] if i else b['start_seconds'];b['end_seconds']=out[i+1]['perceptual_hit_seconds'] if i+1<len(out) else b['end_seconds'];b.pop('_aligned',None)
    return out

def _align(beat, scene, alignment):
    interval=((alignment or {}).get('scene_intervals') or {}).get(str(scene.get('scene_id'))) or {}
    start=float(interval.get('start_seconds',interval.get('start',0.0)) or 0); end=float(interval.get('end_seconds',interval.get('end',start)) or start)
    words=(alignment or {}).get('word_timings') or []; anchor=beat['anchor_text']
    tokens=[x.casefold() for x in re.findall(r'\w+',anchor)]
    match=next((w for w in words if tokens and str(w.get('word') or w.get('text') or '').casefold() in tokens),None)
    hit=float(match.get('start_seconds',match.get('start',start)) if match else start)
    beat.update({'start_seconds':start,'perceptual_hit_seconds':hit,'end_seconds':end,'_aligned':bool(match) or not beat.get('source')=='DERIVED_FROM_PACKAGE'})
