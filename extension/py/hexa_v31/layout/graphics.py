from __future__ import annotations


def _vmap(vision_results):
    out={}
    for s in vision_results:
        units={str(u.get('semantic_unit_id')):u for u in (s.get('units') or []) if u.get('semantic_unit_id')}
        out[str(s.get('scene_id'))]=(s,units)
    return out


def _tmap(alignment): return {str(x.get('scene_id')):x for x in (alignment.get('scene_timings') or [])}


def _explicit_directives(scene:dict):
    """Return only explicit builder-native graphic directives.

    V23 inferred arrows from generic relationships. In real production that could
    draw a second, stylistically foreign arrow on top of an illustration that
    already communicated the relationship. V31 never synthesizes relationship
    graphics from semantics alone; the recovered image objects themselves carry
    the storytelling motion. A graphic is legal only when the scene package
    explicitly asks for one.
    """
    rows=[]
    for key in ('semantic_graphics','builder_elements','graphics'):
        raw=scene.get(key) or []
        if isinstance(raw,dict): raw=[raw]
        if isinstance(raw,list): rows.extend(raw)
    for u in scene.get('units') or []:
        raw=u.get('builder_elements') or u.get('semantic_graphics') or []
        if isinstance(raw,dict): raw=[raw]
        if isinstance(raw,list):
            for r in raw:
                if isinstance(r,dict):
                    rr=dict(r);rr.setdefault('source_unit_id',u.get('unit_id'));rows.append(rr)
                else: rows.append(r)
    out=[]
    for r in rows:
        if isinstance(r,str): out.append({'kind':r})
        elif isinstance(r,dict): out.append(dict(r))
    return out


def build_graphics_plan(plan:dict, alignment:dict, vision_results:list[dict], logger=None)->dict:
    vm=_vmap(vision_results); tm=_tmap(alignment); events=[]; rejected_implicit=0
    for scene in (plan.get('scenes') or []):
        sid=str(scene.get('scene_id')); timing=tm.get(sid); vv=vm.get(sid)
        if not timing or not vv: continue
        _,phys=vv; st=float(timing['start']); en=float(timing['end']); dur=max(0.05,en-st)
        directives=_explicit_directives(scene)
        # Count generic relationships only as diagnostics; they never authorize an arrow.
        for u in scene.get('units') or []:
            if u.get('interaction_target') or u.get('relationship'): rejected_implicit+=1
        if not directives: continue
        for d in directives[:1]:
            kind=str(d.get('kind') or d.get('type') or '').upper().replace(' ','_')
            ev=None
            if kind=='ARROW':
                src=str(d.get('source_unit_id') or d.get('from_unit_id') or '')
                tgt=str(d.get('target_unit_id') or d.get('to_unit_id') or '')
                if src in phys and tgt in phys:
                    ev={'kind':'ARROW','from_norm':list(phys[src]['center_norm']),'to_norm':list(phys[tgt]['center_norm']),'reason':'EXPLICIT_BUILDER_DIRECTIVE','priority':3,'budget_cost':0.26}
            elif kind=='DIVIDER':
                ev={'kind':'DIVIDER','x_norm':float(d.get('x_norm',0.5)),'reason':'EXPLICIT_BUILDER_DIRECTIVE','priority':2,'budget_cost':0.20}
            elif kind in {'X_MARK','CHECK_MARK'}:
                target=str(d.get('target_unit_id') or d.get('unit_id') or '')
                if target in phys:
                    b=phys[target]['bbox_norm'];x,y,w,h=map(float,b)
                    ev={'kind':kind,'center_norm':[min(0.92,x+w),max(0.08,y)],'reason':'EXPLICIT_BUILDER_DIRECTIVE','priority':3,'budget_cost':0.22}
            elif kind=='FOCUS_RING':
                target=str(d.get('target_unit_id') or d.get('unit_id') or '')
                if target in phys:
                    ev={'kind':'FOCUS_RING','bbox_norm':list(phys[target]['bbox_norm']),'reason':'EXPLICIT_BUILDER_DIRECTIVE','priority':2,'budget_cost':0.18}
            if not ev: continue
            start=st+min(max(0.16,dur*0.30),max(0.05,dur-0.20));graphic_cap=0.54 if kind=='ARROW' else 0.78;end=min(en-0.03,start+min(graphic_cap,max(0.40,dur*0.30)))
            if end-start<0.28: continue
            ev.update({'graphic_id':f'GRAPHIC_{len(events)+1:03d}','scene_id':sid,'start_seconds':round(start,6),'end_seconds':round(end,6),'fade_in_seconds':0.09,'fade_out_seconds':0.09})
            events.append(ev)
    result={
        'schema':'HEXA_SEMANTIC_GRAPHICS_PLAN_V31','version':'3.0',
        'policy':'EXPLICIT_BUILDER_DIRECTIVES_ONLY__NATIVE_OBJECT_STORY_FIRST__PRESET_DERIVED_ARROW_WIPE',
        'event_count':len(events),'events':events,
        'diagnostics':{'implicit_relationships_not_rendered_as_arrows':rejected_implicit},
        'hard_rules':{
            'max_one_semantic_graphic_per_scene':True,
            'no_decorative_icon_spam':True,
            'explicit_builder_directive_required':True,
            'automatic_relationship_arrow_forbidden':True,
            'native_object_choreography_has_priority':True,
            'topic_specific_graphic_rules_forbidden':True,
            'presentation_budget_required':True,
        }
    }
    if logger:logger.log('PASS','SEMANTIC_GRAPHICS_PLAN_BUILT',graphic_events=len(events),policy=result['policy'],implicit_relationship_arrows_suppressed=rejected_implicit)
    return result
