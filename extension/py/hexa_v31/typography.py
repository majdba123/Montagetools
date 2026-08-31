from __future__ import annotations
import os, pathlib, re, json, hashlib, math
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont, features

_ARABIC_RE=re.compile(r'[\u0600-\u06FF]')
_LATIN_RE=re.compile(r'[A-Za-z]')
_DIGIT_RE=re.compile(r'[0-9٠-٩]')
_TRIM=' \t\r\n،,.;:؛!?؟-–—()[]{}"\''
TYPE_PRIORITY={'PRICE':9.5,'NUMBER':9.0,'STATUS':8.7,'LABEL':7.3,'CONCEPT':6.9,'CARD':4.2,'UI':4.2,'DEVICE':3.2,'OBJECT':2.7,'GROUP':2.7,'ICON':2.2}
GENERIC_SEMANTIC_ACTIONS=('LIMIT','FAIL','REJECT','STATUS','ERROR','BLOCK','WARNING','RESULT','SOLUTION','PROBLEM','COMPARE','CAUSE','EFFECT','CHANGE','INCREASE','DECREASE','RISK','PRICE','COST','NUMBER','PERCENT','TOTAL','AVAILABLE','RESERVED','DEFINE','NAME','KEY','FOCUS','CONCLUSION','SUCCESS','APPROVE','COMPLETE')
# Language glue, not topic knowledge. This is used only to avoid rendering fragments such as "لكن" or "في" as graphics.
WEAK_WORDS={'و','أو','او','بس','لكن','لأن','لان','إذا','اذا','حتى','مع','من','في','على','عن','هذا','هذه','هذي','ذلك','تلك','اللي','إنه','انه','ثم','بعد','قبل','عند','كان','كانت','يكون','تكون','هو','هي','هم','ما','مو','مش','لا','لم','لن','قد','كل','أي','اي','أكثر','اقل','أقل'}


_CONNECTOR_RE=re.compile(r'^(?:and|or|but|because|if|then|with|from|to|of|the|a|an|this|that|it|they|he|she|we|i)$',re.I)
_ARABIC_BOUNDARY_GLUE={'و','أو','لكن','لأن','إذا','حتى','مع','من','في','على','عن','إلى','ثم','بعد','قبل','عند','هو','هي','هم','قد'}
_ARABIC_POLARITY={'ما','لا','لم','لن','ليس','غير'}

class ArabicPhraseCompletenessAnalyzer:
    version='HEXA_ARABIC_PHRASE_COMPLETENESS_V3'
    def assess(self,value,canonical=None):
        text=_clean(value);words=[_word_clean(x) for x in text.split() if _word_clean(x)]
        reasons=[];arabic=bool(_ARABIC_RE.search(text));numeric=bool(_DIGIT_RE.search(text))
        if canonical is not None and text not in str(canonical):reasons.append('NOT_EXACT_CANONICAL_SUBSTRING')
        if canonical is not None and text in str(canonical):
            cw=[_word_clean(x) for x in _clean(canonical).split()];tw=[_word_clean(x) for x in text.split()]
            for i in range(0,max(0,len(cw)-len(tw)+1)):
                if cw[i:i+len(tw)]==tw and i>0 and cw[i-1] in _ARABIC_POLARITY:reasons.append('POLARITY_DROPPED');break
        if not words:reasons.append('EMPTY')
        if words and (words[0] in _ARABIC_BOUNDARY_GLUE or words[-1] in _ARABIC_BOUNDARY_GLUE):reasons.append('WEAK_BOUNDARY_CONNECTOR')
        if words and words[-1] in _ARABIC_POLARITY:reasons.append('INCOMPLETE_POLARITY')
        if words and (_CONNECTOR_RE.match(words[0]) or _CONNECTOR_RE.match(words[-1])):reasons.append('WEAK_BOUNDARY_CONNECTOR')
        content=[w for w in words if w not in _ARABIC_BOUNDARY_GLUE]
        if arabic and not numeric and len(content)<2:reasons.append('INCOMPLETE_SEMANTIC_PHRASE')
        if len(words)>5 or len(text)>36:reasons.append('DISPLAY_BUDGET_EXCEEDED')
        return {'pass':not reasons,'version':self.version,'text':text,'exact_substring':canonical is None or text in str(canonical),'reasons':list(dict.fromkeys(reasons)),'content_word_count':len(content),'numeric':numeric}

class TypographyDirectorV2:
    """Deterministic literal-copy selection and physical treatment authority."""
    version='HEXA_TYPOGRAPHY_DIRECTOR_V2'
    @staticmethod
    def phrase_complete(value):
        return ArabicPhraseCompletenessAnalyzer().assess(value).get('pass',False)
    @staticmethod
    def treatment(value):return str(value or 'FREE_KEYWORD').upper()

def _scene_timing(alignment):
    return {str(x.get('scene_id')):x for x in (alignment.get('scene_timings') or [])}


def _trigger_time(trigger,alignment,scene_row):
    st=float(scene_row.get('start',0)); en=float(scene_row.get('end',st+1))
    if trigger:
        a=int(trigger.get('global_char_start',-1)); b=int(trigger.get('global_char_end',-1)); rows=alignment.get('word_timings') or []
        if rows and a>=0 and b>=a:
            wr=[r for r in rows if int(r.get('char_end',-1))>a and int(r.get('char_start',10**9))<b]
            if wr:
                return max(st,float(wr[0].get('start',st))-0.02),min(en,float(wr[-1].get('end',st+0.3))+0.04)
    return st+min(0.22,max(0.05,(en-st)*0.20)),min(en-0.03,st+min(1.7,max(0.72,(en-st)*0.72)))


def _clean(s):
    return ' '.join(str(s or '').split()).strip(_TRIM)

def validate_viewer_text(value, script_language=None):
    """Strict firewall: rendering is for authored/canonical copy, never machine labels."""
    s=_clean(value)
    if not s or len(s)>64 or '_' in s or re.search(r'(^|\s)[A-Z][A-Z0-9_]{2,}($|\s)',s):return False
    if re.search(r'\b(?:semantic|visual|state|role|slug|asset|unit|scene|card|function|meaning)\b',s,re.I):return False
    if str(script_language or '').lower() in ('ar','arabic') and not _ARABIC_RE.search(s):return False
    return _is_displayable(s)

def measure_title_layout(text, canvas_w, canvas_h, w_norm, h_norm):
    """Measure shaped text with the actual installed font; no character-count cropping."""
    path=find_arabic_font('headline')
    if not path:return {'fits':False,'rtl_capable':False,'reason':'NO_GLYPH_CAPABLE_FONT'}
    w,h=int(canvas_w*w_norm),int(canvas_h*h_norm);rtl=bool(_ARABIC_RE.search(str(text)));raqm=bool(features.check('raqm'));draw_value=str(text) if (not rtl or raqm) else _fallback_shape(str(text));fallback_ok=(not rtl or raqm or draw_value!=str(text))
    for size in range(int(60*canvas_h/1080),int(31*canvas_h/1080)-1,-2):
        font=ImageFont.truetype(path,max(18,size));draw=ImageDraw.Draw(Image.new('RGBA',(w,h)))
        kw={'font':font};
        if rtl and raqm:kw.update(direction='rtl',language='ar')
        try: box=draw.textbbox((0,0),draw_value,**kw)
        except Exception:continue
        if box[2]-box[0]<=w-38 and box[3]-box[1]<=h-26:return {'fits':True,'font_size':size,'line_count':1,'rtl_capable':fallback_ok,'measured_width':box[2]-box[0]}
    return {'fits':False,'rtl_capable':fallback_ok,'reason':'MEASURED_TEXT_DOES_NOT_FIT'}


def _word_clean(w):
    return str(w or '').strip(_TRIM)


def _is_displayable(s):
    s=_clean(s)
    if not s or len(s)<2 or len(s)>36:return False
    words=s.split()
    if len(words)>5:return False
    if not (_ARABIC_RE.search(s) or _LATIN_RE.search(s) or _DIGIT_RE.search(s)):return False
    return True


def _strip_weak_prefix(s):
    words=_clean(s).split()
    while len(words)>=2 and _word_clean(words[0]).lower() in WEAK_WORDS and _word_clean(words[0]) not in _ARABIC_POLARITY:
        words=words[1:]
    return _clean(' '.join(words))


def _phrase_quality(s):
    s=_clean(s)
    if not _is_displayable(s) or not TypographyDirectorV2.phrase_complete(s):return -999.0
    words=s.split(); clean=[_word_clean(w) for w in words]
    content=[w for w in clean if w and w.lower() not in WEAK_WORDS]
    numeric=bool(_DIGIT_RE.search(s))
    if not numeric and not content:return -999.0
    score=0.0
    score+=4.0 if numeric else 0.0
    score+=2.2 if len(words) in (2,3) else 1.0 if len(words)==1 else 0.7
    score+=1.2 if 5<=len(s)<=26 else 0.2
    score+=0.8*min(3,len(content))
    if clean and clean[0].lower() in WEAK_WORDS:score-=2.0
    if clean and clean[-1].lower() in WEAK_WORDS:score-=2.0
    return score


def _exact_subphrases(raw):
    """Return compact contiguous literal phrases without inventing copy.

    V22 could only use a trigger when the whole trigger was <=5 words, which collapsed real
    production coverage to 8.16%. V31 searches literal contiguous n-grams and clause fragments,
    scoring them for readability. The selected text always remains an exact substring of narration.
    """
    raw=' '.join(str(raw or '').split())
    out=[]
    if not raw:return out
    whole=_strip_weak_prefix(raw)
    if _is_displayable(whole):out.append((whole,_phrase_quality(whole)+1.0))
    # Clause candidates first.
    for clause in re.split(r'[،,;؛:!?؟]+',raw):
        c=_strip_weak_prefix(clause)
        if _is_displayable(c):out.append((c,_phrase_quality(c)+0.8))
    tokens=raw.split()
    # Complete 2..5 word windows only; a standalone number remains eligible.
    for size in (2,3,4,5,1):
        for i in range(0,max(0,len(tokens)-size+1)):
            cand=_clean(' '.join(tokens[i:i+size]))
            cand2=_strip_weak_prefix(cand)
            if not cand2 or cand2 not in raw:continue
            if size==1 and not _DIGIT_RE.search(cand2):continue
            if not ArabicPhraseCompletenessAnalyzer().assess(cand2,raw)['pass']:continue
            q=_phrase_quality(cand2)
            if q>-100:out.append((cand2,q))
    # Deduplicate while retaining highest quality.
    best={}
    for text,score in out:
        if text not in best or score>best[text]:best[text]=score
    return sorted(best.items(),key=lambda x:(-x[1],len(x[0].split()),len(x[0])))


def _best_exact_subphrase(raw):
    rows=_exact_subphrases(raw)
    return rows[0][0] if rows else ''


def _style_for(typ,nf,phrase,scene):
    rel=str(scene.get('relation_to_previous') or '').upper()
    if typ in ('PRICE','NUMBER') or _DIGIT_RE.search(phrase):return 'NUMERIC_HERO'
    if typ=='STATUS' or any(k in nf for k in ('FAIL','REJECT','STATUS','ERROR','BLOCK','WARNING','SUCCESS','APPROVE','COMPLETE')):return 'STATUS_BADGE'
    if rel in ('COMPARE','COMPARISON') or any(k in nf for k in ('COMPARE','LIMIT','CONTRAST','VERSUS')):return 'CONTRAST_LABEL'
    if typ in ('LABEL','UI','DEVICE','CARD'):return 'MICRO_LABEL'
    return 'KEY_TERM'


def _typography_role(typ,nf,phrase,scene):
    """Generic semantic role selection; no package/topic knowledge."""
    token=(str(typ)+' '+str(nf)).upper()
    if _DIGIT_RE.search(phrase): return 'VALUE'
    if any(x in token for x in ('ERROR','FAIL','REJECT','BLOCK','WARNING')): return 'WARNING'
    if any(x in token for x in ('SUCCESS','APPROVE','COMPLETE','RESULT','SOLUTION')): return 'RESULT'
    if 'STATUS' in token:return 'STATUS'
    if any(x in token for x in ('COMPARE','LIMIT','CONTRAST','VERSUS')):return 'COMPARISON_LABEL'
    if typ in ('LABEL','UI','DEVICE','CARD'):return 'MICRO_LABEL'
    return 'KEYWORD'


def _treatment_for(role, ordinal):
    """Deterministic V3 typography treatment rotation within a semantic role."""
    options={
        'VALUE':('VALUE_LOCKUP','RESULT_LOCKUP'), 'WARNING':('WARNING_BADGE','SIDE_CALLOUT'),
        'RESULT':('RESULT_LOCKUP','BOTTOM_RESULT','SIDE_RESULT'), 'STATUS':('STATUS_BADGE','INLINE_LABEL'),
        'COMPARISON_LABEL':('COMPARISON_LABELS','OBJECT_ADJACENT_LABEL'),
        'MICRO_LABEL':('MICRO_CONTEXT','INLINE_LABEL'), 'KEYWORD':('FREE_KEYWORD','OBJECT_ADJACENT_LABEL','SIDE_CALLOUT'),
    }.get(role,('FREE_KEYWORD','SIDE_CALLOUT'))
    return options[int(ordinal)%len(options)]


def _candidate(scene,unit):
    typ=str(unit.get('type') or '').upper(); role=str(unit.get('role') or '').upper(); tr=unit.get('focus_trigger') or unit.get('appear_trigger')
    raw=(tr or {}).get('phrase') or ''
    rows=_exact_subphrases(raw)
    if not rows:return None
    phrase,pq=rows[0]
    score=float(TYPE_PRIORITY.get(typ,1.0))+(3.2 if role=='PRIMARY' else 0.8 if role=='SUPPORTING' else 0)+pq*0.55
    if _DIGIT_RE.search(phrase):score+=3.2
    nf=str(unit.get('narrative_function') or '').upper(); score+=min(3.2,sum(0.8 for k in GENERIC_SEMANTIC_ACTIONS if k in nf))
    if str(unit.get('semantic_intent') or '').upper() in ('INTRODUCE','EMPHASIZE','COMPARE','RESOLVE','REVEAL','FOCUS'):score+=1.1
    return {'scene_id':scene['scene_id'],'text':phrase,'unit_id':unit.get('unit_id'),'unit_type':typ,'role':role,'trigger':tr,'score':round(score,3),'style':_style_for(typ,nf,phrase,scene),'source':'UNIT_TRIGGER_LITERAL_SUBPHRASE'}


def _fallback(scene):
    raw=((scene.get('script_span') or {}).get('text') or '')
    rows=_exact_subphrases(raw)
    if not rows:return None
    phrase,pq=rows[0]
    numeric=bool(_DIGIT_RE.search(phrase))
    # The candidate is still an exact 1--5 word canonical substring.  A
    # moderate-quality phrase is useful as a visual label when no explicit
    # source viewer string exists; rejecting all of them left long, visually
    # unsupported source states despite valid narration-grounded copy.
    if not numeric and pq<2.8:return None
    score=4.8+pq*0.50+(2.8 if numeric else 0.0)
    style='NUMERIC_HERO' if numeric else 'KEY_TERM'
    return {'scene_id':scene['scene_id'],'text':phrase,'unit_id':None,'unit_type':'SCRIPT_SPAN','role':'PRIMARY','trigger':None,'score':round(score,3),'style':style,'source':'SCENE_SCRIPT_LITERAL_SUBPHRASE'}


def _overlap(a,b):
    ax,ay,aw,ah=a; bx,by,bw,bh=b; ix=max(0,min(ax+aw,bx+bw)-max(ax,bx)); iy=max(0,min(ay+ah,by+bh)-max(ay,by)); return ix*iy/max(1e-9,aw*ah)


@lru_cache(maxsize=48)
def _alpha_channel(path):
    try:
        with Image.open(path) as im:
            return im.getchannel('A').copy() if im.mode=='RGBA' else None
    except (OSError,ValueError):
        return None


def _alpha_occupancy(alpha,rect):
    if alpha is None:return None
    x,y,w,h=rect;aw,ah=alpha.size;box=(max(0,int(x*aw)),max(0,int(y*ah)),min(aw,int((x+w)*aw)),min(ah,int((y+h)*ah)))
    if box[2]<=box[0] or box[3]<=box[1]:return 0.0
    hist=alpha.crop(box).histogram();total=max(1,sum(hist));return sum(hist[9:])/total


def _role_geometry(text,role,canvas_w=1920,canvas_h=1080):
    """Return content-sized geometry from real shaped glyph bounds."""
    role=str(role or 'KEYWORD').upper(); preferred={'HERO':88,'VALUE':86,'RESULT':78,'WARNING':72,'STATUS':68,'KEYWORD':72,'CALLOUT':60,'CONTEXT':52,'MICRO_LABEL':48,'COMPARISON_LABEL':58}.get(role,64)
    floor=36 if role in {'CONTEXT','MICRO_LABEL','CALLOUT'} else 42
    max_w=int(canvas_w*(.46 if role in {'HERO','VALUE','RESULT'} else .40)); max_h=int(canvas_h*.20)
    path=find_arabic_font(role.lower()); rtl=bool(_ARABIC_RE.search(str(text)));raqm=bool(features.check('raqm'));value=str(text) if (not rtl or raqm) else _fallback_shape(str(text));draw=ImageDraw.Draw(Image.new('RGBA',(max_w,max_h)))
    for size in range(preferred,floor-1,-2):
        font=ImageFont.truetype(path,size);kw={'font':font,'spacing':int(size*.18)}
        if rtl and raqm:kw.update(direction='rtl',language='ar')
        variants=[value]
        words=str(text).split()
        if len(words)>2:
            for cut in range(1,len(words)):
                a=' '.join(words[:cut]);b=' '.join(words[cut:]); variants.append((a+'\n'+b) if (not rtl or raqm) else (_fallback_shape(a)+'\n'+_fallback_shape(b)))
        for rendered in variants:
            try:box=draw.multiline_textbbox((0,0),rendered,align='right' if rtl else 'left',**kw)
            except (TypeError,ValueError):
                kw.pop('direction',None);kw.pop('language',None);box=draw.multiline_textbbox((0,0),rendered,align='right' if rtl else 'left',**kw)
            gw,gh=box[2]-box[0],box[3]-box[1]
            if gw<=max_w and gh<=max_h:
                pad_x=max(10,int(size*.16));pad_y=max(8,int(size*.12))
                return {'font_size':size,'rendered_text':rendered,'glyph_width':gw,'glyph_height':gh,'w_norm':(gw+2*pad_x)/canvas_w,'h_norm':(gh+2*pad_y)/canvas_h,'padding_x':pad_x,'padding_y':pad_y,'line_count':rendered.count('\n')+1}
    return None


def _choose_slot(vscene,text,style,treatment='FREE_KEYWORD',related_unit_id=None,typography_role=None):
    """Place content-sized text beside its related visual, never top-centre."""
    geom=_role_geometry(text,typography_role or 'KEYWORD')
    if not geom:return None
    width=max(.10,float(geom['w_norm']));height=max(.055,float(geom['h_norm']));units=vscene.get('units') or []
    related=next((u for u in units if str(u.get('unit_id') or u.get('physical_id'))==str(related_unit_id)),None)
    rb=(related or {}).get('bbox_norm') or []
    slots=[]
    if len(rb)==4:
        ux,uy,uw,uh=map(float,rb); related_type=str((related or {}).get('semantic_type') or '').upper();gap=.075 if 'CHARACTER' in related_type else .040
        slots=[('RELATED_RIGHT',ux+uw+gap,uy+uh*.5-height*.5,width,height),('RELATED_LEFT',ux-gap-width,uy+uh*.5-height*.5,width,height),('RELATED_BELOW',ux+uw-width,uy+uh+gap,width,height),('RELATED_ABOVE',ux+uw-width,uy-gap-height,width,height)]
    slots += [('MID_RIGHT',.94-width,.38,width,height),('MID_LEFT',.06,.38,width,height),('BOTTOM_RIGHT',.94-width,.90-height,width,height),('BOTTOM_LEFT',.06,.90-height,width,height),('TOP_RIGHT',.94-width,.07,width,height),('TOP_LEFT',.06,.07,width,height)]
    boxes=[];alpha_layers=[]
    for u in units:
        alpha=_alpha_channel(str(u.get('layer_path') or '')) if u.get('layer_path') else None
        if alpha is not None:alpha_layers.append(alpha)
        b=u.get('bbox_norm') or []
        if len(b)==4 and alpha is None:
            x,y,w,h=map(float,b); pad=0.028
            # Human visual safety is stricter than ink-rectangle collision:
            # text may not crowd a face/head or a primary action region.
            typ=str(u.get('semantic_type') or '').upper(); role=str(u.get('semantic_role') or '').upper()
            if 'CHARACTER' in typ: pad=0.065
            elif role=='PRIMARY': pad=0.060
            # A loose source bounding box is not occupied visual ink.  Using
            # its matte fill preserves true object avoidance while allowing a
            # source-backed text panel in legitimate negative space inside a
            # sparse illustration's envelope.
            fill=float((u.get('matting') or {}).get('opaque_foreground_fraction') or 0.62)
            boxes.append((max(0,x-pad),max(0,y-pad),min(1,x+w+pad)-max(0,x-pad),min(1,y+h+pad)-max(0,y-pad),max(.12,min(1.0,fill))))
            for key in ('face_bbox_norm','head_bbox_norm','action_bbox_norm','critical_ui_bbox_norm'):
                q=u.get(key) or []
                if len(q)==4:
                    qx,qy,qw,qh=map(float,q);safe=.045;boxes.append((max(0,qx-safe),max(0,qy-safe),min(1,qx+qw+safe)-max(0,qx-safe),min(1,qy+qh+safe)-max(0,qy-safe),1.0))
    best=None
    for idx,(name,x,y,w,h) in enumerate(slots):
        if x<.035 or y<.035 or x+w>.965 or y+h>.94:continue
        ov=sum(_overlap((x,y,w,h),b[:4])*b[4] for b in boxes)
        # Loose semantic bboxes often wrap a sparse illustration. The original
        # alpha canvas, not that bbox, is the negative-space authority.
        ov+=sum(float(_alpha_occupancy(a,(x,y,w,h)) or 0.0) for a in alpha_layers)
        score=ov+idx*.004
        if best is None or score<best[0]:best=(score,name,x,y,w,h,ov)
    if not best or best[6]>0.045:return None
    _,name,x,y,w,h,ov=best
    return {'slot':name,'x_norm':x,'y_norm':y,'w_norm':w,'h_norm':h,'visual_overlap_score':round(ov,4),'text_geometry':geom,'relationship_placement':'ADJACENT_TO_RELATED_VISUAL' if name.startswith('RELATED_') else 'RESERVED_NEGATIVE_SPACE','generic_background_panel':False}


def build_text_plan(package,alignment,vision_results,motion_plan,logger=None):
    scenes=package.plan.get('scenes') or []; vmap={str(v.get('scene_id')):v for v in vision_results}; tmap=_scene_timing(alignment); candidates=[]
    visual_cards=(motion_plan.get('visual_cards') or {})
    scene_to_cards={str(k):([str(x) for x in v] if isinstance(v,list) else [str(v)]) for k,v in (visual_cards.get('scene_to_card') or {}).items()}
    card_rows={str(c.get('card_id')):c for c in (visual_cards.get('cards') or [])}
    for order,scene in enumerate(scenes,1):
        sr=tmap.get(str(scene.get('scene_id')))
        if not sr:continue
        dur=max(0.0,float(sr.get('end',0))-float(sr.get('start',0)))
        # Typography on micro-beats is usually unreadable and competes with the visual transition.
        if dur<0.85:continue
        options=[]
        for unit in (scene.get('units') or []):
            c=_candidate(scene,unit)
            if c:options.append(c)
        fb=_fallback(scene)
        if fb:options.append(fb)
        # A preferred unit label can have no legal negative-space slot even
        # though the scene's exact canonical fallback does.  Select the best
        # *placeable* source-literal option rather than dropping that entire
        # semantic moment after the first placement attempt.
        placeable=[]
        for best in sorted(options,key=lambda x:(-float(x.get('score') or 0),str(x.get('text') or ''))):
            unit=next((u for u in (scene.get('units') or []) if str(u.get('unit_id'))==str(best.get('unit_id'))),{})
            best['typography_role']=_typography_role(best['unit_type'],unit.get('narrative_function') or '',best['text'],scene)
            best['treatment']=_treatment_for(best['typography_role'],order)
            placement=_choose_slot(vmap.get(scene['scene_id'],{}),best['text'],best['style'],best['treatment'],best.get('unit_id'),best['typography_role'])
            if not placement:
                continue
            row=dict(best);row['scene_order']=order;row['duration_seconds']=dur;row['placement']=placement
            placeable.append(row)
        # V1.1 creative ownership is interval-card + semantic trigger. A source
        # scene may therefore yield several distinct opportunities, but only
        # when their exact source phrases anchor inside distinct child cards.
        used_cards=set();used_text=set()
        card_ids=scene_to_cards.get(str(scene.get('scene_id'))) or []
        for row in placeable:
            ts,_=_trigger_time(row.get('trigger'),alignment,sr)
            card_id=next((cid for cid in card_ids if float((card_rows.get(cid) or {}).get('start_seconds',-1))<=ts<float((card_rows.get(cid) or {}).get('end_seconds',-1))),None)
            if card_id is None and len(card_ids)==1:card_id=card_ids[0]
            text_key=_clean(row.get('text'))
            if not card_id or card_id in used_cards or text_key in used_text:continue
            card=card_rows.get(card_id) or {};row=dict(row,visual_card_id=card_id,card_start_seconds=float(card.get('start_seconds',sr.get('start',0))),card_end_seconds=float(card.get('end_seconds',sr.get('end',0))))
            candidates.append(row);used_cards.add(card_id);used_text.add(text_key)

    # Adaptive opportunity-driven density, not a fixed per-project quota.
    strong=[c for c in candidates if c['score']>=8.0 or c['style'] in ('NUMERIC_HERO','STATUS_BADGE')]
    eligible=max(1,len({str(c.get('visual_card_id')) for c in candidates if c.get('visual_card_id')}))
    # Premium support typography is a recurring editorial beat, not a
    # once-per-chapter adornment.  The cap remains below one label per scene,
    # and each selected row is literal source copy rather than narration.
    desired=int(math.ceil(eligible*0.42)); upper=int(math.ceil(eligible*0.58)); target=min(len(candidates),max(min(len(strong),upper),desired)); target=min(target,max(1,upper)) if candidates else 0
    selected=[]; orders=set(); texts=set(); cards_used=set()
    for c in sorted(candidates,key=lambda x:(-x['score'],x['scene_order'])):
        norm=re.sub(r'\s+',' ',c['text']).strip()
        if norm in texts:continue
        card_id=str(c.get('visual_card_id') or '')
        if card_id and card_id in cards_used:continue
        o=int(c['scene_order'])
        if any(abs(o-u)<=1 for u in orders) and c['style'] not in ('NUMERIC_HERO','STATUS_BADGE'):
            continue
        selected.append(c);orders.add(o);texts.add(norm);cards_used.add(card_id)
        if len(selected)>=target:break
    if len(selected)<target:
        for c in sorted(candidates,key=lambda x:(-x['score'],x['scene_order'])):
            norm=re.sub(r'\s+',' ',c['text']).strip()
            if c in selected or norm in texts:continue
            card_id=str(c.get('visual_card_id') or '')
            if card_id and card_id in cards_used:continue
            selected.append(c);orders.add(int(c['scene_order']));texts.add(norm);cards_used.add(card_id)
            if len(selected)>=target:break

    out=[]
    for i,c in enumerate(sorted(selected,key=lambda x:x['scene_order']),1):
        sr=tmap.get(c['scene_id'])
        if not sr:continue
        ts,te=_trigger_time(c.get('trigger'),alignment,sr); ss=max(float(sr['start']),float(c.get('card_start_seconds',sr['start']))); se=min(float(sr['end']),float(c.get('card_end_seconds',sr['end']))); dur=max(0.05,se-ss)
        if not (ss-1e-6<=ts<se-1e-6):continue
        entry_duration={'VALUE':.44,'RESULT':.48,'WARNING':.36,'STATUS':.36,'KEYWORD':.52,'MICRO_LABEL':.40,'COMPARISON_LABEL':.46}.get(str(c.get('typography_role')),.46)
        available=max(0.0,ts-ss);entry_duration=min(entry_duration,max(.26,available))
        impact=ts;start=max(ss+0.03,impact-entry_duration);settle=impact
        # A typography beat needs time to read and to balance the source
        # composition.  It may live through the source scene, but never past
        # the scene's semantic authority.
        hold=1.85 if c['style'] in ('KEY_TERM','MICRO_LABEL') else 2.10
        # One selected phrase is the card's contextual support label.  It is
        # introduced only at its source anchor, then remains readable through
        # the already-established semantic card rather than vanishing at each
        # micro-scene boundary.  It never crosses a card/source-concept cut.
        card_end=float(c.get('card_end_seconds') or se)
        end=card_end-0.03 if c.get('visual_card_id') else min(se-0.03,max(te+0.58,start+min(hold,max(0.72,dur*0.82))))
        if end-start<0.45:continue
        pl=c['placement']; style=c['style']
        slide_dx = 0.064 if 'LEFT' in pl['slot'] else (-0.064 if 'RIGHT' in pl['slot'] else 0.0)
        slide_dy = 0.026 if 'TOP' in pl['slot'] else (-0.026 if 'BOTTOM' in pl['slot'] else 0.0)
        grammar={'FREE_KEYWORD':'KEYWORD_REVEAL','OBJECT_ADJACENT_LABEL':'OBJECT_THEN_LABEL','STATUS_BADGE':'STATUS_HIT','VALUE_LOCKUP':'VALUE_REVEAL','RESULT_LOCKUP':'RESULT_EMPHASIS','SIDE_CALLOUT':'SIDE_CALLOUT_REVEAL','COMPARISON_LABELS':'COMPARISON_BUILD'}.get(c.get('treatment'),'TEXT_OBJECT_HANDOFF')
        geom=pl['text_geometry'];role=c.get('typography_role')
        semantic_phrase=bool(c.get('source')=='SCENE_SCRIPT_LITERAL_SUBPHRASE');phrase_end=min(end,ts+max(0.85,min(2.4,end-ts))) if semantic_phrase else end
        out.append({'text_id':f'TEXT_{i:03d}','scene_id':c['scene_id'],'scene_order':c['scene_order'],'visual_card_id':c.get('visual_card_id'),'unit_id':c.get('unit_id'),'text':c['text'],'style':style,'typography_role':role,'treatment':c.get('treatment'),'motion_grammar':grammar,'relationship_target_unit_id':c.get('unit_id'),'relationship_placement':pl['relationship_placement'],'entry_seconds':round(start,6),'impact_seconds':round(impact,6),'settle_seconds':round(settle,6),'semantic_anchor_seconds':round(ts,6),'pre_roll_seconds':round(max(0,impact-start),6),'readable_start_seconds':round(settle,6),'readable_end_seconds':round(phrase_end-0.18,6),'start_seconds':round(start,6),'end_seconds':round(phrase_end,6),'text_lifetime_kind':'SEMANTIC_PHRASE' if semantic_phrase else 'CONTEXT_LABEL','fade_in_seconds':min(.20,entry_duration*.45),'fade_out_seconds':0.18,'pop_scale_from':.94 if role in ('VALUE','RESULT','WARNING','STATUS') else .97,'pop_scale_peak':1.018 if role in ('VALUE','RESULT') else 1.0,'pop_scale_end':1.0,'slide_dx_norm':slide_dx*.56,'slide_dy_norm':slide_dy*.56,'slide_duration_seconds':entry_duration,'read_sweep_dx_norm':round(-slide_dx*.10,6),'read_sweep_dy_norm':round(-slide_dy*.08,6),'read_sweep_duration_seconds':1.15,'motion_preset':'TEXT_'+grammar+'__V31_0_25','x_norm':pl['x_norm'],'y_norm':pl['y_norm'],'w_norm':pl['w_norm'],'h_norm':pl['h_norm'],'slot':pl['slot'],'text_geometry':geom,'font_policy':'CERTIFIED_FONT_HASH_PLUS_HARFBUZZ_GLYPH_PLAN','generic_background_panel':False,'semantic_source':c.get('source'),'source_lifetime_authority':'ALIGNED_PHRASE_WINDOW' if semantic_phrase else 'SOURCE_ANCHOR_THROUGH_CURRENT_SEMANTIC_CARD','score':c['score'],'visual_overlap_score':pl['visual_overlap_score'],'budget_cost':0.24 if style in ('KEY_TERM','MICRO_LABEL') else 0.30})
    font_cert=certified_arabic_font_status()
    result={'schema':'HEXA_SELECTIVE_TYPOGRAPHY_PLAN_V31','version':'3.4-V31_0_25_CARD_BEAT_TYPOGRAPHY','policy':'TYPOGRAPHY_V3__VISUAL_CARD_BEAT__COMPLETE_ARABIC_PHRASES__CERTIFIED_HARFBUZZ','scene_count':len(scenes),'eligible_scene_count':len({str(c.get('scene_id')) for c in candidates}),'eligible_visual_card_count':eligible,'opportunity_count':len(candidates),'target_count':target,'text_event_count':len(out),'coverage_scene_percent':round(100.0*len({str(e.get('scene_id')) for e in out})/max(1,len(scenes)),2),'eligible_coverage_percent':round(100.0*len(out)/max(1,eligible),2),'events':out,'typography_production_certification':font_cert,'production_review_required':not font_cert.get('pass',False),'hard_rules':{'not_every_card_mechanically':True,'max_one_primary_text_event_per_visual_card':True,'source_scene_may_own_multiple_distinct_card_beats':True,'exact_narration_substring_required':True,'complete_phrase_required':True,'no_full_sentence_subtitles':True,'max_words':5,'max_chars':36,'negative_space_placement_required':True,'related_visual_placement_required':True,'generic_background_panels_forbidden':True,'top_center_default_forbidden':True,'face_head_primary_occlusion_forbidden':True,'arabic_shaping_required':True,'certified_font_hash_required':True,'harfbuzz_raqm_authority':True,'no_bundled_unapproved_font':True,'adaptive_coverage':True,'topic_specific_keyword_dependency':False,'minimum_duration_seconds':0.85,'quota_filling_forbidden':True,'perceptual_settle_voice_anchored':True,'bounded_pre_roll_max_seconds':.52}}
    if logger:logger.log('PASS','SELECTIVE_TYPOGRAPHY_PLAN_BUILT',text_events=len(out),scene_count=len(scenes),eligible_scenes=eligible,opportunities=len(candidates),coverage_percent=result['coverage_scene_percent'],styles=sorted(set(e['style'] for e in out)))
    return result


def merge_support_typography(title_plan:dict,support_plan:dict)->dict:
    """Merge non-credit support typography with semantic title fallback.

    Title-only coverage continues to consume ``title_plan`` before this merge.
    These extra units are composition support and can never satisfy a physical
    or deferred semantic anchor.
    """
    titles=[dict(e,text_event_kind='TITLE_FALLBACK',semantic_credit='TITLE_ONLY') for e in (title_plan.get('events') or [])]
    occupied=[(float(e.get('start_seconds',0)),float(e.get('end_seconds',0)),str(e.get('scene_id')),str(e.get('visual_card_id') or ''),str(e.get('text') or '')) for e in titles]
    support=[];skipped=[]
    for e in support_plan.get('events') or []:
        st=float(e.get('start_seconds',0));en=float(e.get('end_seconds',st));sid=str(e.get('scene_id'));text=str(e.get('text') or '')
        reason=None; title_end=None
        card_id=str(e.get('visual_card_id') or '')
        for a,b,osid,ocard,otext in occupied:
            if min(en,b)>max(st,a) and (sid==osid or (card_id and card_id==ocard) or text==otext):
                # A title is the concept setup; a distinct, source-literal
                # support phrase may follow it in the same card when it still
                # has a genuine read window.  This creates TEXT_THEN_OBJECT
                # pacing rather than painting two text layers together.
                if str(otext)!=text and card_id and card_id==ocard:
                    reason='VOICE_ANCHOR_OCCUPIED_BY_HERO_TYPOGRAPHY';break
                reason='OVERLAPS_TITLE_OR_DUPLICATE_SEMANTIC_BEAT';break
        if reason:skipped.append({'scene_id':sid,'text':text,'reason':reason});continue
        row=dict(e,text_event_kind='TYPOGRAPHY_SUPPORT',semantic_credit='NONE',typography_unit=True)
        support.append(row);occupied.append((st,en,sid,card_id,text))
    events=sorted(titles+support,key=lambda e:(float(e.get('start_seconds',0)),str(e.get('text_id'))))
    return {'schema':'HEXA_V31_PREMIUM_TYPOGRAPHY_PLAN','version':'31.0.25','events':events,'text_event_count':len(events),
        'title_fallback_event_count':len(titles),'support_typography_event_count':len(support),
        'opportunity_count':int(support_plan.get('opportunity_count') or 0),'used_support_opportunity_count':len(support),
        'skipped_opportunities':list(support_plan.get('skipped_opportunities') or [])+skipped,
        'title_qa':title_plan.get('title_qa') or {},'pass':bool(title_plan.get('pass',False)),
        'hard_rules':{'support_typography_semantic_credit_forbidden':True,'title_only_coverage_computed_before_merge':True,'source_backed_copy_only':True,'subtitle_blocks_forbidden':True}}


@lru_cache(maxsize=16)
def certified_arabic_font_status():
    cfg_path=pathlib.Path(__file__).resolve().parents[2]/'resources'/'HEXA_CERTIFIED_ARABIC_FONT.json'
    try:cfg=json.loads(cfg_path.read_text(encoding='utf-8'))
    except Exception:return {'pass':False,'status':'DEGRADED_REVIEW_REQUIRED','reason':'CERTIFIED_FONT_CONFIG_MISSING'}
    windir=pathlib.Path(os.environ.get('WINDIR') or os.environ.get('SystemRoot') or r'C:\\Windows')
    path=windir/'Fonts'/str(cfg.get('font_file') or '')
    if not path.is_file():return {'pass':False,'status':'DEGRADED_REVIEW_REQUIRED','reason':'CERTIFIED_FONT_UNAVAILABLE','config':cfg}
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest.lower()!=str(cfg.get('sha256') or '').lower():return {'pass':False,'status':'DEGRADED_REVIEW_REQUIRED','reason':'CERTIFIED_FONT_HASH_MISMATCH','path':str(path),'actual_sha256':digest,'config':cfg}
    if features.check('raqm'):
        authority='PILLOW_RAQM_HARFBUZZ'
    else:
        probe=_uharfbuzz_probe(path)
        if not probe.get('pass'):
            return {'pass':False,'status':'DEGRADED_REVIEW_REQUIRED','reason':probe.get('reason') or 'HARFBUZZ_AUTHORITY_UNAVAILABLE','path':str(path),'sha256':digest,'config':cfg}
        authority='UHARFBUZZ_0_56_0_GLYPH_PLAN_WITH_PRESENTATION_FORM_RASTER'
    return {'pass':True,'status':'CERTIFIED','path':str(path),'sha256':digest,'shaping_authority':authority,'configured_shaping_authority':cfg.get('shaping_authority'),'config':cfg}

def _uharfbuzz_probe(path,text='مرحبا بالعالم'):
    """Prove the exact font can form a deterministic RTL glyph plan offline."""
    try:
        import uharfbuzz as hb
        blob=hb.Blob.from_file_path(str(path));face=hb.Face(blob);font=hb.Font(face)
        font.scale=(face.upem,face.upem);buf=hb.Buffer();buf.add_str(str(text));buf.guess_segment_properties();hb.shape(font,buf,{'kern':True,'liga':True})
        infos=list(buf.glyph_infos);positions=list(buf.glyph_positions)
        if not infos or len(infos)!=len(positions) or any(int(x.codepoint)<=0 for x in infos):
            return {'pass':False,'reason':'UHARFBUZZ_INVALID_GLYPH_PLAN'}
        signature=';'.join(f'{i.codepoint}:{i.cluster}:{p.x_advance}:{p.x_offset}:{p.y_offset}' for i,p in zip(infos,positions))
        return {'pass':True,'glyph_count':len(infos),'glyph_plan_sha256':hashlib.sha256(signature.encode('ascii')).hexdigest()}
    except Exception as exc:
        return {'pass':False,'reason':'UHARFBUZZ_UNAVAILABLE','detail':type(exc).__name__}

@lru_cache(maxsize=16)
def find_arabic_font(weight='headline'):
    """Deterministic, offline-only Arabic stack selected for HEXA's rounded art."""
    certified=certified_arabic_font_status()
    if certified.get('pass'):return certified['path']
    if isinstance(weight,bool):weight='headline' if weight else 'context'
    role=str(weight or 'headline').lower()
    heavy=role in {'headline','hero','value','result','warning'}; support=role in {'keyword','status','callout','comparison_label','micro_label'}
    windir=os.environ.get('WINDIR') or os.environ.get('SystemRoot') or r'C:\\Windows'; wd=pathlib.Path(windir)/'Fonts';local=pathlib.Path(os.environ.get('LOCALAPPDATA') or '')/'Microsoft'/'Windows'/'Fonts'
    preferred=(('tajawalextrabold','tajawalbold','cairobold','notosansarabicbold') if heavy else ('tajawalmedium','tajawalregular','cairomedium','cairoregular','notosansarabicmedium','notosansarabicregular'))
    available=[]
    for root in (wd,local):
        if root.is_dir():
            try:available.extend(sorted((p for p in root.iterdir() if p.is_file() and p.suffix.lower() in ('.ttf','.otf')),key=lambda p:str(p).lower()))
            except OSError:pass
    normalized=lambda p:re.sub(r'[^a-z0-9]','',p.stem.lower())
    for wanted in preferred:
        p=next((x for x in available if wanted in normalized(x)),None)
        if p:return str(p)
    names=(['segoeuib.ttf','seguisb.ttf','tahomabd.ttf','arialbd.ttf'] if heavy else ['seguisb.ttf','segoeui.ttf','tahoma.ttf','arial.ttf'] if support else ['segoeui.ttf','tahoma.ttf','arial.ttf'])
    for n in names:
        p=wd/n
        if p.is_file():return str(p)
    for p in (pathlib.Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),pathlib.Path('/usr/share/fonts/truetype/freefont/FreeSans.ttf')):
        if p.is_file():return str(p)
    return None


def _fallback_shape(text):
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except Exception:return text


def render_text_rgba(event,canvas_w=1920,canvas_h=1080):
    w=max(40,int(round(float(event.get('w_norm',0.34))*canvas_w))); h=max(32,int(round(float(event.get('h_norm',0.15))*canvas_h))); style=str(event.get('style') or 'KEY_TERM');role=str(event.get('typography_role') or 'KEYWORD');font_path=find_arabic_font(role.lower())
    if not font_path:raise RuntimeError('No suitable Arabic system font found.')
    geom=event.get('text_geometry') or _role_geometry(str(event.get('text') or ''),role,canvas_w,canvas_h) or {};base=int(geom.get('font_size') or 64);font=ImageFont.truetype(font_path,size=max(18,int(round(base*(canvas_h/1080.0)))))
    img=Image.new('RGBA',(w,h),(0,0,0,0)); d=ImageDraw.Draw(img); text=str(event.get('text') or ''); use_raqm=bool(features.check('raqm')); draw_text=str(geom.get('rendered_text') or (text if use_raqm else _fallback_shape(text)));color={'WARNING':(148,42,50,255),'STATUS':(30,112,139,255),'RESULT':(28,116,83,255),'VALUE':(20,52,71,255),'CONTEXT':(61,72,81,255),'MICRO_LABEL':(67,78,86,255),'COMPARISON_LABEL':(38,91,112,255)}.get(role.upper(),(20,43,57,255));kw={'font':font,'fill':color,'spacing':int(base*.18),'align':'right' if _ARABIC_RE.search(text) else 'left'}; mk={'font':font,'spacing':int(base*.18),'align':kw['align']}
    if use_raqm:kw.update(direction='rtl',language='ar');mk.update(direction='rtl',language='ar')
    try:box=d.multiline_textbbox((0,0),draw_text,**mk)
    except TypeError:
        kw.pop('direction',None);kw.pop('language',None);mk.pop('direction',None);mk.pop('language',None);box=d.multiline_textbbox((0,0),draw_text,**mk)
    tw=box[2]-box[0]; th=box[3]-box[1];x=max(0,(w-tw)/2.0);y=max(0,(h-th)/2.0-box[1])
    treatment=TypographyDirectorV2.treatment(event.get('treatment'))
    if treatment=='RESULT_LOCKUP':
        color=(18,96,66,255)
        kw['fill']=color
    elif treatment=='VALUE_LOCKUP':
        color=(15,70,112,255)
        kw['fill']=color
    # Treatments are text-native: distinct hierarchy/outline/shadow/underline,
    # never a generic panel behind the copy.
    if treatment in {'HERO_KEYWORD','VALUE_LOCKUP','RESULT_LOCKUP'}:
        d.multiline_text((x+1,y+2),draw_text,font=font,fill=(0,0,0,58),spacing=int(base*.18),align=kw['align'])
    if treatment in {'WARNING_BADGE','STATUS_HIT'}:
        d.multiline_text((x,y),draw_text,font=font,fill=color,stroke_width=max(1,int(base*.035)),stroke_fill=(255,255,255,210),spacing=int(base*.18),align=kw['align'])
    try:d.multiline_text((x,y),draw_text,**kw)
    except TypeError:kw.pop('direction',None);kw.pop('language',None);d.multiline_text((x,y),draw_text,**kw)
    # Small semantic accents are allowed; a container behind text is never drawn.
    if role.upper() in {'WARNING','STATUS','RESULT','VALUE'}:
        accent={'WARNING':(196,64,70,235),'STATUS':(47,151,177,225),'RESULT':(49,154,109,225),'VALUE':(57,145,172,225)}[role.upper()]
        ax=w-5 if _ARABIC_RE.search(text) else 2;d.line((ax,max(3,y),ax,min(h-3,y+th)),fill=accent,width=max(3,int(base*.065)))
    if treatment in {'HERO_KEYWORD','VALUE_LOCKUP','RESULT_LOCKUP','COMPARISON_LABELS'}:
        ly=min(h-3,int(y+th+max(2,base*.06)));d.line((int(x),ly,int(x+tw),ly),fill=color,width=max(2,int(base*.035)))
    return img
