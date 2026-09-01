from __future__ import annotations
import math


def _node_map(graph:dict)->dict[str,dict]:
    return {str(n.get('node_id')):n for n in (graph.get('nodes') or [])}


def _edge_duration(dist:float,scene_duration:float,fps:float)->float:
    minimum=12.0/max(1.0,fps)
    return max(minimum,min(1.12,max(0.52,0.46+dist*0.88,scene_duration*0.18)))


def _safe_transfer_delta(src:dict,tgt:dict)->tuple[float,float,float]:
    sx,sy=map(float,src.get('center_norm') or [0.5,0.5]);tx,ty=map(float,tgt.get('center_norm') or [0.5,0.5]);vx,vy=tx-sx,ty-sy;dist=math.hypot(vx,vy)
    if dist<1e-6:return 0.0,0.0,dist
    ux,uy=vx/dist,vy/dist;sb=list(map(float,src.get('bbox_norm') or [sx-.1,sy-.1,.2,.2]));tb=list(map(float,tgt.get('bbox_norm') or [tx-.1,ty-.1,.2,.2]))
    src_extent=abs(ux)*sb[2]*.5+abs(uy)*sb[3]*.5;tgt_extent=abs(ux)*tb[2]*.5+abs(uy)*tb[3]*.5;free=max(0.0,dist-src_extent-tgt_extent)
    if free<=1e-6:return 0.0,0.0,dist
    breathing=max(0.008,min(src_extent,tgt_extent)*0.10);travel=max(0.0,free-breathing);dx,dy=ux*travel,uy*travel
    dx=max(-sb[0],min(1.0-(sb[0]+sb[2]),dx));dy=max(-sb[1],min(1.0-(sb[1]+sb[3]),dy));return dx,dy,dist


def _ordered_edge_nodes(edges:list[dict])->list[str]:
    order=[]
    for e in edges:
        for nid in (str(e.get('source') or ''),str(e.get('target') or '')):
            if nid and nid not in order:order.append(nid)
    return order


def _distributed_schedule(order:list[str],nodes:dict,scene_start:float,scene_end:float)->dict[str,float]:
    if not order:return {}
    dur=max(1e-6,scene_end-scene_start);real=[(nid,nodes.get(nid,{}).get('appear_time')) for nid in order]
    valid=[float(t) for _,t in real if t is not None]
    distinct=len(valid)>=2 and max(valid)-min(valid)>=0.10
    out={}
    if distinct:
        last=scene_start
        for nid,t in real:
            if t is None:continue
            q=max(scene_start+0.03,min(scene_end-0.18,float(t)));q=max(q,last+0.08 if last>scene_start else q);out[nid]=q;last=q
        # Untimed nodes fill the largest remaining windows without inventing topic semantics.
        missing=[nid for nid,_ in real if nid not in out]
        for i,nid in enumerate(missing):out[nid]=scene_start+dur*(0.18+0.60*(i+1)/(len(missing)+1))
        return out
    # Shared scene-level cue: stage physical story units across the shot instead of popping together.
    if len(order)==1:return {order[0]:scene_start+min(0.10,max(0.04,dur*0.08))}
    lo=0.08 if dur<1.5 else 0.10
    # Two-object long shots were a major V26 plateau source: placing the second reveal late left multi-second dead zones. In a >=3.2s two-object shot,
    # establish both semantic units in the first third, then let the hard-rule continuous 110->100
    # image motion carry an eligible object for >=3s. Denser stories may extend farther.
    if len(order)==2 and dur>=3.2: hi=0.64
    elif len(order)==2: hi=0.66 if dur>=2.2 else 0.62
    elif len(order)==3: hi=0.76 if dur>=2.2 else 0.70
    else: hi=0.84 if dur>=2.2 else 0.76
    for i,nid in enumerate(order):out[nid]=scene_start+dur*(lo+(hi-lo)*(i/max(1,len(order)-1)))
    return out


def build_story_state_machine(scene:dict,graph:dict,*,scene_start:float,scene_end:float,fps:float=30.0)->dict:
    """Turn the single semantic-acting graph into a voice-timed visual state machine.

    V31 never requires causality in order to tell a visual story. Causal TRANSFER edges create
    stateful Position motion when physically safe. Non-causal actionable edges create staged
    semantic introductions/attention handoffs. Connected subobjects are reveal-only and are never
    translated away from their source art. This guarantees meaningful temporal progression without
    manufacturing false cause/effect.
    """
    dur=max(1.0/fps,scene_end-scene_start);nodes=_node_map(graph);actionable=[e for e in (graph.get('edges') or []) if bool(e.get('actionable')) and float(e.get('confidence',0))>=0.54]
    actionable=sorted(actionable,key=lambda e:(-int(e.get('priority',0)),10**9 if nodes.get(str(e.get('source')),{}).get('appear_time') is None else float(nodes.get(str(e.get('source')),{}).get('appear_time')),str(e.get('source')),str(e.get('target'))))
    order=_ordered_edge_nodes(actionable);schedule=_distributed_schedule(order,nodes,scene_start,scene_end)
    actions=[];states=[{'state_id':'ESTABLISH','time_seconds':round(scene_start,6),'kind':'ESTABLISH'}]
    # Every staged introduction is a real visual story beat even when no causal travel is justified.
    for i,nid in enumerate(order):
        t=schedule.get(nid,scene_start);node=nodes.get(nid,{})
        actions.append({'action_id':f'INTRODUCE_{nid}','kind':'INTRODUCE','node_id':nid,'target_node_id':None,'start_seconds':round(t,6),'end_seconds':round(min(scene_end,t+max(12.0/fps,min(0.56,dur*0.18))),6),'dx_norm':0.0,'dy_norm':0.0,'hold_after':True,'render_mode':'APPEARANCE_AUTHORITY','authority':'SEMANTIC_ACTING_SCHEDULE','confidence':0.90,'priority':86-int(i),'motion_role':node.get('motion_role'),'semantic_purpose':'STAGED_SEMANTIC_INTRODUCTION'})
        states.append({'state_id':f'INTRODUCE_{i+1}','time_seconds':round(t,6),'kind':'INTRODUCE','node':nid})

    cursor=scene_start+min(0.44,max(0.16,dur*0.16));transfer_count=0
    intro_end={str(a.get('node_id')):float(a.get('end_seconds',scene_start)) for a in actions if a.get('kind')=='INTRODUCE'}
    compiled_edges=[];fallback_handoffs=set()
    for i,e in enumerate(actionable[:5]):
        src=nodes.get(str(e.get('source')));tgt=nodes.get(str(e.get('target')))
        if not src or not tgt:continue
        mode=str(e.get('action_mode') or '')
        pair=(str(e.get('source') or ''),str(e.get('target') or ''))
        if mode!='TRANSFER' or not bool(e.get('causal')):
            compiled_edges.append({'source':pair[0],'target':pair[1],'requested_action_mode':mode,'resolved_action_mode':'REVEAL_HANDOFF' if mode=='REVEAL_HANDOFF' else 'ATTENTION_HANDOFF','physical_position_action':False,'reason':'NON_TRANSFER_SEMANTIC_HANDOFF'})
            continue
        # TRANSFER in the graph is a promise that geometry and duration were plausible. The compiler
        # still performs a final physical/timing check. If runtime timing makes the 12-frame move
        # impossible, downgrade to a semantic handoff rather than silently dropping the story beat.
        if not src.get('animation_safe',False) or str(src.get('animation_mode'))!='TRANSLATE_SAFE':
            compiled_edges.append({'source':pair[0],'target':pair[1],'requested_action_mode':'TRANSFER','resolved_action_mode':'REVEAL_HANDOFF','physical_position_action':False,'reason':'SOURCE_NOT_TRANSLATE_SAFE'});fallback_handoffs.add(pair);continue
        dx,dy,dist=_safe_transfer_delta(src,tgt);minimum=12.0/max(1.0,fps)
        if math.hypot(dx,dy)<0.028:
            compiled_edges.append({'source':pair[0],'target':pair[1],'requested_action_mode':'TRANSFER','resolved_action_mode':'REVEAL_HANDOFF','physical_position_action':False,'reason':'NO_VISIBLE_COLLISION_SAFE_TRAVEL'});fallback_handoffs.add(pair);continue
        src_intro=schedule.get(str(src.get('node_id')),scene_start);tgt_intro=schedule.get(str(tgt.get('node_id')),scene_end-0.10)
        earliest=max(cursor,intro_end.get(str(src.get('node_id')),src_intro)+0.04)
        latest=scene_end-0.08
        if latest-earliest<minimum-1e-6:
            compiled_edges.append({'source':pair[0],'target':pair[1],'requested_action_mode':'TRANSFER','resolved_action_mode':'REVEAL_HANDOFF','physical_position_action':False,'reason':'INSUFFICIENT_LEGAL_12_FRAME_WINDOW'});fallback_handoffs.add(pair);continue
        dd=_edge_duration(dist,dur,fps)
        preferred_end=max(earliest+minimum,min(latest,tgt_intro+min(0.12,max(0.05,dur*0.035))))
        start=max(earliest,preferred_end-dd);end=min(latest,max(start+minimum,start+dd))
        if end-start<minimum-1e-6:
            compiled_edges.append({'source':pair[0],'target':pair[1],'requested_action_mode':'TRANSFER','resolved_action_mode':'REVEAL_HANDOFF','physical_position_action':False,'reason':'POST_SCHEDULE_WINDOW_TOO_SHORT'});fallback_handoffs.add(pair);continue
        actions.append({'action_id':f"TRANSFER_{src['node_id']}_TO_{tgt['node_id']}",'kind':'POSITION_TRANSFER','node_id':src['node_id'],'target_node_id':tgt['node_id'],'start_seconds':round(start,6),'end_seconds':round(end,6),'dx_norm':round(dx,6),'dy_norm':round(dy,6),'hold_after':True,'render_mode':'MOTION','interpolation':'BEZIER_EASE_IN_OUT','motion_profile':'JERK_LIMITED_S_CURVE_7','motion_blur_enabled':True,'minimum_frames':12,'authority':e.get('authority'),'confidence':float(e.get('confidence',0)),'priority':int(e.get('priority',0)),'motion_role':'ACTOR','semantic_purpose':'SOURCE_TO_TARGET_TRANSFER'})
        compiled_edges.append({'source':pair[0],'target':pair[1],'requested_action_mode':'TRANSFER','resolved_action_mode':'POSITION_TRANSFER','physical_position_action':True,'reason':'COMPILED'})
        states.append({'state_id':f'TRANSFER_{transfer_count+1}','time_seconds':round(start,6),'kind':'TRANSFER','actor':src['node_id'],'target':tgt['node_id']});states.append({'state_id':f'RECEIVE_{transfer_count+1}','time_seconds':round(end,6),'kind':'RECEIVE','actor':src['node_id'],'target':tgt['node_id']});cursor=end+max(0.10,4.0/max(1.0,fps));transfer_count+=1

    # Attention handoff is represented as a state boundary, not a decorative pulse. A transfer
    # downgraded by the physical compiler receives the same semantic handoff instead of vanishing.
    for e in actionable:
        pair=(str(e.get('source') or ''),str(e.get('target') or ''))
        if str(e.get('action_mode'))=='TRANSFER' and bool(e.get('causal')) and pair not in fallback_handoffs:continue
        tgt=str(e.get('target') or '');t=schedule.get(tgt)
        if t is not None:states.append({'state_id':f'HANDOFF_{len(states)}','time_seconds':round(t,6),'kind':'ATTENTION_HANDOFF','target':tgt,'authority':e.get('authority'),'causal_fallback':pair in fallback_handoffs})
    states=sorted(states,key=lambda x:(float(x.get('time_seconds',scene_start)),str(x.get('state_id'))));states.append({'state_id':'SETTLE','time_seconds':round(scene_end,6),'kind':'SETTLE'})
    physical=[a for a in actions if a.get('render_mode')=='MOTION'];introductions=[a for a in actions if a.get('kind')=='INTRODUCE']
    return {'schema':'HEXA_VISUAL_STORY_STATE_MACHINE_V31','version':'4.0','scene_id':scene.get('scene_id'),'scene_start':scene_start,'scene_end':scene_end,'states':states,'actions':actions,'story_action_count':len(actions),'physical_action_count':len(physical),'causal_action_count':len(physical),'introduction_action_count':len(introductions),'story_eligible':bool(graph.get('story_eligible')),'story_eligibility_reasons':graph.get('story_eligibility_reasons') or [],'causal_reveal_order':order,'reveal_schedule':{k:round(v,6) for k,v in schedule.items()},'compiled_edge_resolutions':compiled_edges,'compiled_transfer_count':sum(1 for x in compiled_edges if x.get('resolved_action_mode')=='POSITION_TRANSFER'),'downgraded_transfer_count':sum(1 for x in compiled_edges if x.get('requested_action_mode')=='TRANSFER' and x.get('resolved_action_mode')!='POSITION_TRANSFER'),'topic_specific_rules':False,'hard_rule_position_min_frames':12,'single_story_truth_schema':graph.get('schema')}
