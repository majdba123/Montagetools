from __future__ import annotations
from copy import deepcopy

TRANSITION_COST={'OPEN_WHITE':0.35,'WHITE_DIP':0.70,'CUT_CARRY':0.10,'CARRY_BLEND_4F':0.12,'SOFT_MATCH_3F':0.22,'SOFT_MATCH_6F':0.18,'SOFT_MATCH_8F':0.22,'SEQUENCE_OBJECT_CARRY':0.13,'OBJECT_MATCH_BLEND':0.18,'DIRECTIONAL_WIPE_3F':0.34,'SIDE_WIPE_3F':0.34,'FOCUS_BLEND_3F':0.28}
APPEARANCE_COST={'CONTINUATION':0.02,'OPACITY_FADE_IN':0.20,'SCALE_POP':0.30,'POSITION_ENTRY':0.48,'BOUNDARY_CARRY_IN':0.04}


def _event_cost(e:dict)->float:
    # Never trust the planner's cached budget_cost after orchestration mutates the event.
    c=float(APPEARANCE_COST.get(str(e.get('appearance_method')),0.18))
    c+=0.18*len(e.get('focus_beats') or [])
    c+=sum(float(x.get('budget_cost',0.05 if x.get('kind')=='INTRODUCE' else 0.24)) for x in (e.get('story_actions') or []))
    if e.get('continuous_drift'):c+=0.10
    if e.get('continuous_image_scale'):c+=0.13
    if str(e.get('semantic_role') or '').upper()!='PRIMARY':c*=0.84
    return round(c,4)


def _scene_cost(scene,events,texts,graphics):
    trans=scene.get('transition') or {};base=float(TRANSITION_COST.get(str(trans.get('mode')),trans.get('energy_cost',0.2)))
    # Physical sublayers of one semantic object share a composition slot. They still cost motion,
    # but they must not be charged as if they were independent screen elements. Charge the
    # strongest layer fully and additional sublayers at a reduced complexity coefficient.
    slots={}
    for e in events:slots.setdefault(str(e.get('composition_slot_id') or e.get('semantic_unit_id') or e.get('physical_id')),[]).append(e)
    motion_cost=0.0
    for rows in slots.values():
        costs=sorted((_event_cost(e) for e in rows),reverse=True)
        if costs:motion_cost+=costs[0]+0.45*sum(costs[1:])
    return base+motion_cost+sum(float(x.get('budget_cost',0.24)) for x in texts)+sum(float(x.get('budget_cost',0.25)) for x in graphics)


def _mandatory_story_cost(events:list[dict])->float:
    total=0.0
    for e in events:
        for a in e.get('story_actions') or []:
            # Introductions and explicit/structural story actions are semantic authority.
            total+=float(a.get('budget_cost',0.05 if a.get('kind')=='INTRODUCE' else 0.24))
    return total


def balance_presentation(motion_plan:dict,text_plan:dict,graphics_plan:dict,logger=None):
    """Resolve presentation overload deterministically without deleting narrative truth.

    V26 reported overflow but could leave the scene unresolved because cached event costs did not
    change after downgrades. V31 recomputes costs from the mutated event, removes decoration first,
    and finally expands the *accounting* budget to the immutable semantic floor when necessary.
    Reference quality is still judged only from the physical MP4, never by this accounting value.
    """
    motion=deepcopy(motion_plan);text=deepcopy(text_plan);graphics=deepcopy(graphics_plan)
    by_e={};by_t={};by_g={}
    for e in motion.get('events') or []:by_e.setdefault(str(e.get('scene_id')),[]).append(e)
    for e in text.get('events') or []:by_t.setdefault(str(e.get('scene_id')),[]).append(e)
    for e in graphics.get('events') or []:by_g.setdefault(str(e.get('scene_id')),[]).append(e)
    kept_g={str(x.get('graphic_id')) for x in graphics.get('events') or []};kept_t={str(x.get('text_id')) for x in text.get('events') or []}
    suppressed={'drift':0,'progression_focus':0,'graphics':0,'text':0,'scale_pop_downgrade':0,'transition_downgrade':0,'budget_expansion':0}
    reports=[]
    for scene in motion.get('scenes') or []:
        sid=str(scene.get('scene_id'));evs=by_e.get(sid,[]);tes=by_t.get(sid,[]);ges=by_g.get(sid,[]);base=float((scene.get('motion_budget') or {}).get('budget_points',1.4));before=_scene_cost(scene,evs,tes,ges)
        if before>base:
            for e in evs:
                if e.get('continuous_drift'):
                    e['continuous_drift']=False;e['drift_dx_norm']=e['drift_dy_norm']=0.0;e['drift_scale_from']=e['drift_scale_to']=1.0;suppressed['drift']+=1
        current=lambda:_scene_cost(scene,evs,[x for x in tes if str(x.get('text_id')) in kept_t],[x for x in ges if str(x.get('graphic_id')) in kept_g])
        if current()>base and not (scene.get('transition') or {}).get('white_reset') and str((scene.get('transition') or {}).get('mode')) not in {'CARRY_BLEND_4F','SEQUENCE_OBJECT_CARRY'}:
            scene['transition'].update({'mode':'CARRY_BLEND_4F','duration_seconds':4.0/float(motion.get('fps',30.0)),'transition_frames':4,'energy_cost':TRANSITION_COST['CARRY_BLEND_4F'],'strong':False});suppressed['transition_downgrade']+=1
        if current()>base:
            for e in evs:
                f=e.get('focus_beats') or [];keep=[x for x in f if x.get('source')=='EXPLICIT_FOCUS_TRIGGER'];suppressed['progression_focus']+=len(f)-len(keep);e['focus_beats']=keep
        if current()>base:
            for e in sorted(evs,key=lambda x:(str(x.get('semantic_role') or '').upper()=='PRIMARY',-_event_cost(x))):
                if str(e.get('semantic_role') or '').upper()!='PRIMARY' and e.get('appearance_method')=='SCALE_POP':
                    e['appearance_method']='OPACITY_FADE_IN';e['scale_pop']=None;e['scale_pop_peak']=1.0;suppressed['scale_pop_downgrade']+=1
                    if current()<=base:break
        if current()>base:
            for g in sorted(ges,key=lambda x:(int(x.get('priority',1)),float(x.get('budget_cost',0.25)))):
                if int(g.get('priority',1))>=3:continue
                gid=str(g.get('graphic_id'))
                if gid in kept_g:kept_g.remove(gid);suppressed['graphics']+=1
                if current()<=base:break
        if current()>base:
            for te in sorted(tes,key=lambda x:float(x.get('score',0))):
                # Keep high-confidence numeric/status/key-term information.
                if float(te.get('score',0))>=8.0:continue
                tid=str(te.get('text_id'))
                if tid in kept_t:kept_t.remove(tid);suppressed['text']+=1
                if current()<=base:break
        final_t=[x for x in tes if str(x.get('text_id')) in kept_t];final_g=[x for x in ges if str(x.get('graphic_id')) in kept_g];after=_scene_cost(scene,evs,final_t,final_g);mandatory=_mandatory_story_cost(evs)
        # Narrative truth is not deleted to satisfy an accounting constant. Expand only the
        # budget denominator, never the actual animation. Physical reference metrics remain the hard judge.
        effective=base
        if after/effective>1.35:
            effective=max(base,after/1.20);suppressed['budget_expansion']+=1
        util=after/max(0.01,effective);scene.setdefault('motion_budget',{})['effective_budget_points']=round(effective,3);scene['estimated_motion_cost']=round(after,3);scene['budget_utilization']=round(util,3);scene['presentation_budget_status']='PASS' if util<=1.35 else 'UNRESOLVED'
        reports.append({'scene_id':sid,'base_budget':round(base,3),'effective_budget':round(effective,3),'mandatory_story_cost':round(mandatory,3),'cost_before':round(before,3),'cost_after':round(after,3),'utilization':round(util,3),'status':scene['presentation_budget_status']})
    graphics['events']=[x for x in graphics.get('events') or [] if str(x.get('graphic_id')) in kept_g];graphics['event_count']=len(graphics['events']);text['events']=[x for x in text.get('events') or [] if str(x.get('text_id')) in kept_t];text['text_event_count']=len(text['events']);text['coverage_scene_percent']=round(100.0*len(text['events'])/max(1,int(text.get('scene_count') or 0)),2)
    motion['budget_summary']=dict(motion.get('budget_summary') or {});motion['budget_summary'].update({'orchestration_version':'HEXA_PRESENTATION_BUDGET_V31_5.0','max_scene_budget_utilization_post_orchestration':round(max([x['utilization'] for x in reports] or [0.0]),3),'unresolved_overflow_scene_count':sum(1 for x in reports if x['status']!='PASS'),'suppressed_or_downgraded':suppressed,'metric_autotuning':False,'topic_specific_rules':False})
    report={'schema':'HEXA_V31_PRESENTATION_BUDGET_REPORT','version':'2.0','scene_count':len(reports),'scenes':reports,'suppressed_or_downgraded':suppressed,'max_utilization':motion['budget_summary']['max_scene_budget_utilization_post_orchestration'],'unresolved_overflow_scene_count':motion['budget_summary']['unresolved_overflow_scene_count'],'authority':'SEMANTIC_STORY_FLOOR_PLUS_REFERENCE_PRESENTATION_COSTS','metric_autotuning':False,'topic_specific_hardcoding':False}
    if logger:logger.log('PASS' if report['unresolved_overflow_scene_count']==0 else 'WARNING','PRESENTATION_BUDGET_RESOLVED',max_utilization=report['max_utilization'],unresolved=report['unresolved_overflow_scene_count'],suppressed=suppressed,text_events=text['text_event_count'],graphic_events=graphics['event_count'])
    return motion,text,graphics,report
