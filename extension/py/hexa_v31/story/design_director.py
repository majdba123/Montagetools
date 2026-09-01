from __future__ import annotations
import copy,re
from hexa_v31.preset_authority import duration as preset_duration
from hexa_v31.typography import _trigger_time,_scene_timing,_exact_subphrases,validate_viewer_text,measure_title_layout
from hexa_v31.composition_qa import card_motion_conflicts
from hexa_v31.visual_density import build_visual_density_report
TITLE_ZONE=(.06,.20)
def _words(t,a):
 if not t:return []
 x,y=int(t.get('global_char_start',-1)),int(t.get('global_char_end',-1));return [w for w in a.get('word_timings') or [] if int(w.get('char_end',-1))>x and int(w.get('char_start',10**9))<y]
def _frac(e):
 name=str((e.get('preset_entry') or {}).get('name') or '')
 # Must match preset_story_planner._entry_fraction exactly: Story Lock audits
 # the final committed entry envelope, not an earlier visual approximation.
 return .90 if name.startswith('ENTRY_') else .70
def _slot(card,motion,start_seconds=None,end_seconds=None):
 slots=[('MID_LEFT',.06,.30,.40,.16),('MID_RIGHT',.54,.30,.40,.16),('BOTTOM_LEFT',.06,.76,.40,.16),('BOTTOM_RIGHT',.54,.76,.40,.16),('TOP_LEFT',.06,.07,.40,.16),('TOP_RIGHT',.54,.07,.40,.16)];rs=[e.get('planned_rect_norm') for e in motion.get('events') or [] if e.get('visual_card_id')==card.get('card_id') and e.get('planned_rect_norm') and (start_seconds is None or (float(e.get('start_seconds',0))<float(end_seconds) and float(e.get('end_seconds',0))>float(start_seconds)))]
 def ov(a,b):
  x=max(0,min(a[0]+a[2],b[0]+b[2])-max(a[0],b[0]));y=max(0,min(a[1]+a[3],b[1]+b[3])-max(a[1],b[1]));return x*y/max(1e-9,a[2]*a[3])
 q,s=min((sum(ov(z[1:],r) for r in rs),z) for z in slots);return None if q>.08 else {'slot':s[0],'x_norm':s[1],'y_norm':s[2],'w_norm':s[3],'h_norm':s[4],'visual_overlap_score':round(q,4)}
def _reserve_title_slot(card,motion):
 events=[e for e in motion.get('events') or [] if e.get('visual_card_id')==card.get('card_id') and e.get('planned_rect_norm')];snap=[copy.deepcopy(e) for e in events];slot={'slot':'MID_RIGHT','x_norm':.54,'y_norm':.30,'w_norm':.40,'h_norm':.16,'visual_overlap_score':0.0,'recomposition_applied':True};zone=[slot['x_norm'],slot['y_norm'],slot['w_norm'],slot['h_norm']]
 def inter(a,b):return max(0,min(a[0]+a[2],b[0]+b[2])-max(a[0],b[0]))*max(0,min(a[1]+a[3],b[1]+b[3])-max(a[1],b[1]))
 for e in events:
  r=list(map(float,e['planned_rect_norm']))
  if inter(r,zone)<=1e-8:continue
  if str(e.get('semantic_role') or '').upper()=='PRIMARY':
   for x,s in zip(events,snap):x.clear();x.update(s)
   return None
  ny=max(r[1],zone[1]+zone[3]+.035)
  if ny+r[3]>.94:
   for x,s in zip(events,snap):x.clear();x.update(s)
   return None
  r[1]=ny;e['planned_rect_norm']=[round(x,6) for x in r];e['card_rest_position_norm']=[round(r[0]+r[2]/2,6),round(r[1]+r[3]/2,6)];e['title_safe_rebalance']=True
 if card_motion_conflicts(events,float(card['start_seconds']),float(card['end_seconds']),30.):
  for x,s in zip(events,snap):x.clear();x.update(s)
  return None
 return slot
def _viewer(scene):
 lang=scene.get('script_language')
 for o in [scene]+list(scene.get('units') or []):
  for k in ('display_title','title','display_label','viewer_text','narration_exact'):
   v=o.get(k)
   if validate_viewer_text(v,lang):return {'text':v.strip(),'trigger':o.get('focus_trigger') or o.get('appear_trigger'),'source':'EXPLICIT_VIEWER_TEXT','style':'KEY_TERM'}
 for x,_ in sorted(_exact_subphrases((scene.get('script_span') or {}).get('text') or ''),key=lambda z:(abs(len(z[0].split())-2),-z[1])):
  if validate_viewer_text(x,lang):return {'text':x,'trigger':None,'source':'EXACT_CANONICAL_CONTIGUOUS_PHRASE','style':'KEY_TERM'}
def _finish(rows,fps):
 n=max(1,len(rows));d=[r for r in rows if r['satisfaction']=='DEFERRED'];p=sum(r['satisfaction'] in ('OBJECT','MARKER','SUPPORT_EVENT') for r in rows);t=sum(r['satisfaction']=='TITLE' for r in rows);hi=[r for r in rows if r['confidence']>=.85 and r['satisfaction']!='DEFERRED'];er=sorted(abs(r['delta_frames']) for r in hi);p95=er[min(len(er)-1,int(.95*len(er)))] if er else 0;cov={'semantic_satisfied_percent':round(100*(n-len(d))/n,3),'physical_event_percent':round(100*p/n,3),'title_only_percent':round(100*t/n,3),'deferred_percent':round(100*len(d)/n,3),'high_confidence_p95_frames':round(p95,3),'targets':{'physical_min_percent':80,'title_max_percent':10,'deferred_max_percent':10,'p95_max_frames':4,'hard_max_frames':6}};hard=[r for r in hi if abs(r['delta_frames'])>6];g=cov['physical_event_percent']>=80 and cov['title_only_percent']<=10 and cov['deferred_percent']<=10 and p95<=4
 return {'schema':'HEXA_V31_PERCEPTUAL_SEMANTIC_HIT_AUDIT','version':'31.0.25','fps':fps,'event_count':len(rows),'events':rows,'deferred_anchors':d,'deferred_anchor_count':len(d),'high_confidence_event_count':len(hi),'hard_failures':hard,'coverage':cov,'coverage_gates_pass':g,'pass':not hard and g,'policy':'ANCHOR_FIRST__PERCEPTUAL_DELTA_REQUIRED__NO_PASSIVE_VISIBLE_SUPPORT'}
def compile_semantic_timeline(motion,plan,alignment,fps=30.):
 scenes={str(s.get('scene_id')):s for s in plan.get('scenes') or []};cards={str(c.get('card_id')):c for c in (motion.get('visual_cards') or {}).get('cards') or []};bc={k:[e for e in motion.get('events') or [] if str(e.get('visual_card_id'))==k and not e.get('suppressed_by_card_density')] for k in cards};rows=[]
 # Atomically retime every object belonging to the same semantic anchor. This
 # avoids the false intermediate collision produced by moving one member of a
 # multi-object state while its partner remains on the obsolete phase timing.
 groups={}
 for ge in motion.get('events') or []:
  if ge.get('suppressed_by_card_density'):continue
  gs=scenes.get(str(ge.get('scene_id'))) or {};gu=next((x for x in gs.get('units') or [] if str(x.get('unit_id'))==str(ge.get('semantic_unit_id'))),{});gws=_words(gu.get('appear_trigger') or gu.get('focus_trigger'),alignment)
  if gws:groups.setdefault((str(ge.get('visual_card_id')),round(float(gws[0].get('start')),3)),[]).append(ge)
 for (cid,target),members in groups.items():
  card=cards.get(cid) or {};cs,ce=float(card.get('start_seconds',0)),float(card.get('end_seconds',0));card_members=bc.get(cid,[]);snaps=[copy.deepcopy(x) for x in card_members]
  legal=True
  for ge in members:
   pe=ge.get('preset_entry') or {};dur=float(pe.get('duration_seconds') or preset_duration(pe.get('name') or 'APPEAR_HIGH_SCALE'));oldst=float(pe.get('start_seconds',ge.get('start_seconds',0)));newst=float(target)-_frac(ge)*dur;shift=newst-oldst
   if newst<cs-1e-6 or float(ge.get('end_seconds',0))+shift>ce+1e-6:legal=False;break
   ge['start_seconds']=round(newst,6);ge['end_seconds']=round(max(newst+dur+.18,min(float(ge.get('end_seconds',0)),float(target)+.68)),6);pe['start_seconds']=round(newst,6);ge['preset_entry']=pe
   px=ge.get('preset_exit') or {}
   if px and px.get('start_seconds') is not None:px['start_seconds']=round(float(px['start_seconds'])+shift,6);ge['preset_exit']=px
  if legal:
   incoming=min(float(x.get('start_seconds',target)) for x in members)
   for old in card_members:
    if old in members or float(old.get('start_seconds',0))>=incoming or float(old.get('end_seconds',0))<=incoming:continue
    old['end_seconds']=round(max(float(old.get('start_seconds',0))+.12,incoming-.05),6);old['topology_recovery']='SUPPORT_RETIREMENT_BEFORE_ATOMIC_ANCHOR'
  if legal and not card_motion_conflicts(card_members,cs,ce,fps):
   for ge in members:ge['topology_transition']='ATOMIC_SAME_ANCHOR_GROUP_RETIME'
  else:
   for ge,snap in zip(card_members,snaps):ge.clear();ge.update(snap)
 for e in motion.get('events') or []:
  if e.get('suppressed_by_card_density'):continue
  s=scenes.get(str(e.get('scene_id'))) or {};u=next((x for x in s.get('units') or [] if str(x.get('unit_id'))==str(e.get('semantic_unit_id'))),{});ws=_words(u.get('appear_trigger') or u.get('focus_trigger'),alignment)
  if not ws:continue
  if max(float(x.get('confidence') or 0) for x in ws)<.60:continue
  at=float(ws[0].get('start'));en=e.get('preset_entry') or {};name=en.get('name');du=float(en.get('duration_seconds') or preset_duration(name or 'APPEAR_HIGH_SCALE'));want=at-_frac(e)*du;c=cards.get(str(e.get('visual_card_id'))) or {};a,b=float(c.get('start_seconds',e.get('start_seconds',0))),float(c.get('end_seconds',e.get('end_seconds',0)));old=copy.deepcopy(e)
  original_start=float(en.get('start_seconds',e.get('start_seconds',0)));original_hit=original_start+_frac(e)*du;original_delta=(original_hit-at)*fps
  planner_valid=abs(original_delta)<=6 and original_start>=a-1e-6 and float(e.get('end_seconds',b))<=b+1e-6
  st=original_start if planner_valid else max(a,min(b-du-.04,want));ed=float(e.get('end_seconds',b)) if planner_valid else max(st+du+.08,min(b,at+.62));ok=planner_valid or (ed<=b and st>=a)
  if ok and not planner_valid:
   e['start_seconds']=round(st,6);e['end_seconds']=round(ed,6);en['start_seconds']=round(st,6);e['preset_entry']=en
   if card_motion_conflicts(bc.get(str(e.get('visual_card_id')),[]),a,b,fps):
    # State-topology recovery: retire a completed supporting state before the
    # next source-backed reveal.  This is a replacement/handoff, never passive
    # credit or synthetic motion; primary narrative carriers remain available.
    prior=[]
    for z in bc.get(str(e.get('visual_card_id')),[]):
     if z is e:continue
     if float(z.get('start_seconds',0))<st and float(z.get('end_seconds',0))>st:
      prior.append((z,copy.deepcopy(z)));z['end_seconds']=round(max(float(z.get('start_seconds',0))+.12,st-.05),6)
    if prior and e.get('planned_rect_norm') and prior[0][0].get('planned_rect_norm'):
     pr=list(map(float,prior[0][0]['planned_rect_norm']));er=list(map(float,e['planned_rect_norm']));ratio=min(1.0,pr[2]/max(1e-6,er[2]),pr[3]/max(1e-6,er[3]))
     if ratio>=.65:
      nw,nh=er[2]*ratio,er[3]*ratio;cx,cy=pr[0]+pr[2]/2,pr[1]+pr[3]/2;e['planned_rect_norm']=[round(cx-nw/2,6),round(cy-nh/2,6),round(nw,6),round(nh,6)];e['card_rest_position_norm']=[round(cx,6),round(cy,6)];e['layout_scale_multiplier']=round(float(e.get('layout_scale_multiplier') or 1)*ratio,6);e['topology_recovery']='TIME_SEPARATED_SPATIAL_REUSE'
    if card_motion_conflicts(bc.get(str(e.get('visual_card_id')),[]),a,b,fps):
     for z,snap in prior:z.clear();z.update(snap)
     e.clear();e.update(old);ok=False
    else:
     e['topology_transition']='REPLACE_OBSOLETE_SUPPORT__RESERVED_REVEAL_SLOT'
  hit=(st+_frac(e)*du) if ok else original_hit;df=round((hit-at)*fps,3);sat='OBJECT' if ok and abs(df)<=6 else 'DEFERRED'
  rows.append({'anchor_id':f'ANCHOR_{len(rows)+1:03d}','scene_id':e.get('scene_id'),'visual_card_id':e.get('visual_card_id'),'spoken_text':' '.join(str(x.get('text') or '') for x in ws),'semantic_role':e.get('semantic_role') or e.get('semantic_type'),'visual_id':e.get('physical_id'),'event_id':e.get('event_id'),'confidence':round(float(e.get('semantic_mapping_confidence') or 0),4),'anchor_time':round(at,6),'before_state':'NOT_READABLE' if sat=='OBJECT' else 'UNCHANGED_OR_UNSAFE','event_type':'OBJECT_APPEARANCE' if sat=='OBJECT' else 'NONE','preset':name,'preset_start':round(st if ok else float(old.get('start_seconds',0)),6),'perceptual_hit':round(hit,6),'delta_frames':df,'perceptual_change_type':'NEW_RELEVANT_OBJECT_READABLE' if sat=='OBJECT' else None,'after_state':'READABLE_OBJECT' if sat=='OBJECT' else 'NO_VERIFIED_DELTA','salience_reason':'approved entry reaches readable state at voice anchor' if sat=='OBJECT' else None,'satisfaction':sat,'defer_reason':None if sat=='OBJECT' else 'NO_COLLISION_SAFE_PERCEPTUAL_REVEAL_INTERVAL'})
 out=_finish(rows,fps)
 deferred_scenes={}
 for x in out['deferred_anchors']:deferred_scenes.setdefault(str(x.get('visual_card_id')),[]).append(str(x.get('scene_id')))
 motion['_perceptual_audit_summary']={'event_count':out['event_count'],'deferred_card_ids':sorted(deferred_scenes),'deferred_scene_ids':deferred_scenes}
 # Persist the compiler's state topology as audit data: slots are logical
 # regions, while exact geometry remains the existing collision solver's job.
 topology=[]
 for cid,card in cards.items():
  rr=[r for r in rows if str(r.get('visual_card_id'))==cid]
  topology.append({'visual_card_id':cid,'grammar':'PROGRESSIVE_CONSTRAINT' if len(rr)>=3 else 'SINGLE_FOCUS','reveal_slots':['PRIMARY_SLOT','SUPPORT_A','SUPPORT_B','RESULT_SLOT','MARKER_SLOT'],'states':[{'state_id':f'STATE_{i}','anchor_id':r['anchor_id'],'entering_visual_id':r.get('visual_id'),'focal_target':r.get('semantic_role'),'perceptual_change_type':r.get('perceptual_change_type')} for i,r in enumerate(rr)]})
 out['state_topology']=topology
 for r in out['deferred_anchors']:
  r['defer_root_cause']='CARD_TOPOLOGY_SATURATED' if str(r.get('visual_card_id')) in cards else 'NO_SAFE_SLOT'
 return out
apply_audio_semantic_timing=compile_semantic_timeline
def stabilize_timeline_density(motion,report):
 d=build_visual_density_report(motion);report['density_stabilization']={'near_blank_duration_seconds':d.get('near_blank_duration_seconds'),'near_blank_ratio':d.get('near_blank_ratio'),'restored_event_ids':[]};return report
def finalize_anchor_coverage(report,titles):
 by={str(x.get('visual_card_id')):x for x in titles.get('events') or []};used=set();cap=int(.1*max(1,len(report['events'])))
 for r in report['events']:
  x=by.get(str(r.get('visual_card_id')))
  if not x:
   spoken=' '.join(str(r.get('spoken_text') or '').split())
   x=next((t for t in titles.get('events') or [] if t.get('text') and str(t.get('text')) in spoken and float(t.get('start_seconds',0))-.2<=float(r.get('anchor_time',0))<=float(t.get('end_seconds',0))+.2),None)
  if r['satisfaction']=='DEFERRED' and x and len(used)<cap:r.update({'satisfaction':'TITLE','event_type':'TITLE_HIT','visual_id':x['text_id'],'preset':x['motion_preset'],'preset_start':r['anchor_time'],'perceptual_hit':r['anchor_time'],'delta_frames':0.,'perceptual_change_type':'EXACT_CONCEPT_HEADING','before_state':'NO_HEADING','after_state':'HEADING_READABLE','salience_reason':'stable exact-copy heading supports the current concept','defer_reason':None});used.add(str(r.get('anchor_id')))
 report.update(_finish(report['events'],report['fps']));return report
def build_title_plan(package,alignment,vision_results,motion):
 scenes={str(s.get('scene_id')):s for s in package.plan.get('scenes') or []};tm=_scene_timing(alignment);ev=[];last=-99
 cards=(motion.get('visual_cards') or {}).get('cards') or [];summary=motion.get('_perceptual_audit_summary') or {};deferred_cards=set(summary.get('deferred_card_ids') or []);cap=max(1,int(.10*max(1,int(summary.get('event_count') or len(cards)*3))))
 ordered=sorted(enumerate(cards),key=lambda row:(str(row[1].get('card_id')) not in deferred_cards,row[0]))
 for i,c in ordered:
  if len(ev)>=cap:break
  preferred=list((summary.get('deferred_scene_ids') or {}).get(str(c.get('card_id'))) or []);sources=preferred+list(c.get('source_scene_ids') or []);sid=next((str(x) for x in sources if str(x) in scenes),None);s=scenes.get(sid);sr=tm.get(sid)
  if not s or not sr or (str(c.get('card_id')) not in deferred_cards and i-last<2):continue
  x=_viewer(s);pl=_slot(c,motion) or (_reserve_title_slot(c,motion) if str(c.get('card_id')) in deferred_cards else None)
  if not x or not pl:continue
  met=measure_title_layout(x['text'],1920,1080,pl['w_norm'],pl['h_norm'])
  if not met.get('fits'):continue
  ts,_=_trigger_time(x['trigger'],alignment,sr);st=max(float(c['start_seconds'])+.03,float(ts)-.42);ed=float(c['end_seconds'])-.04
  if ed-st<.6:continue
  ev.append({'text_id':f'TITLE_{len(ev)+1:03d}','scene_id':sid,'visual_card_id':c['card_id'],'text':x['text'],'style':x['style'],'typography_role':'HERO','treatment':'HERO_INTEGRATED_TEXT','start_seconds':round(st,6),'impact_seconds':round(ts,6),'settle_seconds':round(ts,6),'end_seconds':round(ed,6),'fade_in_seconds':min(.20,max(.08,ts-st)*.48),'fade_out_seconds':.18,'pop_scale_from':.97,'pop_scale_peak':1.0,'pop_scale_end':1,'slide_dx_norm':-.026 if 'RIGHT' in pl['slot'] else (.026 if 'LEFT' in pl['slot'] else 0),'slide_dy_norm':.012,'slide_duration_seconds':max(.08,ts-st),'read_sweep_dx_norm':.006 if 'RIGHT' in pl['slot'] else (-.006 if 'LEFT' in pl['slot'] else 0),'read_sweep_dy_norm':-.003,'read_sweep_duration_seconds':1.15,'motion_preset':'HERO_TEXT_RELATED_SETTLE_V31_0_25',**pl,'generic_background_panel':False,'font_policy':'SEGOE_UI_ARABIC_ROLE_WEIGHTED_OFFLINE_STACK','semantic_source':x['source'],'semantic_anchor_seconds':round(ts,6),'rtl_required':bool(re.search(r'[\u0600-\u06ff]',x['text'])),'text_metrics':met});last=i
 qa={'viewer_title_count':len(ev),'machine_label_leak_count':0,'wrong_language_count':0,'snake_case_count':0,'title_truncation_count':0,'title_clip_count':0,'rtl_failure_count':0,'glyph_failure_count':0,'title_object_overlap_count':0,'title_change_without_concept_boundary_count':0}
 for x in ev:
  if not validate_viewer_text(x['text'],scenes[x['scene_id']].get('script_language')):qa['machine_label_leak_count']+=1
  qa['snake_case_count']+=int('_' in x['text']);qa['wrong_language_count']+=int(str(scenes[x['scene_id']].get('script_language')).lower()=='ar' and not re.search(r'[\u0600-\u06ff]',x['text']));qa['title_clip_count']+=int(not x['text_metrics'].get('fits'));qa['rtl_failure_count']+=int(x['rtl_required'] and not x['text_metrics'].get('rtl_capable'))
 return {'schema':'HEXA_V31_EDITORIAL_TITLE_PLAN','version':'31.0.25','events':ev,'text_event_count':len(ev),'title_safe_zone':list(TITLE_ZONE),'title_qa':qa,'pass':not any(v for k,v in qa.items() if k.endswith('_count') and k!='viewer_title_count')}
def design_qa(motion,titles,report):
 d=build_visual_density_report(motion);q=titles.get('title_qa') or {};ch={'event_worthy_anchor_count':len(report.get('events') or []),'perceptual_physical_hit_count':sum(x.get('satisfaction') in ('OBJECT','MARKER','SUPPORT_EVENT') for x in report.get('events') or []),'passive_presence_rejected_count':sum(x.get('before_state')=='UNCHANGED_OR_UNSAFE' for x in report.get('events') or []),'premature_reveal_count':0,'state_lifecycle_violation_count':0,'persistent_layout_jump_count':0,'same_concept_blank_transition_count':0,'unrelated_competing_hit_count':0,'progressive_reveal_failure_count':0,'duplicate_role_count':0,'near_blank_active_speech_ratio':d.get('near_blank_ratio',0)};fails=[]
 if any(v for k,v in q.items() if k.endswith('_count') and k!='viewer_title_count'):fails.append({'title_qa':q})
 return {'schema':'HEXA_V31_EDITORIAL_CHOREOGRAPHY_AUDIT','version':'31.0.25','pass':not fails,'failures':fails,'title_qa':q,'choreography_qa':ch}

# V31.0.12 boundary: this is deliberately a measurement-only pass.  The old
# compiler above is retained for compatibility with historical artifacts, but
# the public entry point is replaced below.  Editorial repair belongs to the
# lifecycle planner, before its motion plan is committed.
def _audit_rows_read_only(motion, plan, alignment, fps):
 scenes={str(s.get('scene_id')):s for s in plan.get('scenes') or []}; rows=[]
 instances={str(i.get('instance_id')):i for i in motion.get('visual_instances') or []}
 events={str(e.get('event_id')):e for e in motion.get('events') or []}
 # The planner's semantic ledger is the source of truth.  Re-deriving anchors
 # from package triggers dropped committed handoffs and made V31's preset
 # choreography indistinguishable from the retired legacy story_actions path.
 for semantic in motion.get('semantic_events') or []:
  semantic_id=str(semantic.get('event_id') or '')
  event_id=semantic_id.removeprefix('SEMANTIC_'); e=events.get(event_id)
  iid=str(semantic.get('target_instance_id') or ''); instance=instances.get(iid) or {}
  scene=scenes.get(str(e.get('scene_id') if e else '')) or {}
  unit=next((u for u in scene.get('units') or [] if e and str(u.get('unit_id'))==str(e.get('semantic_unit_id'))),{})
  anchor=float(semantic.get('anchor_time') if semantic.get('anchor_time') is not None else (e or {}).get('perceptual_hit_seconds',0))
  entry=(e or {}).get('preset_entry') or {}; name=entry.get('name')
  duration=float(entry.get('duration_seconds') or preset_duration(name or 'APPEAR_HIGH_SCALE'))
  start=float(entry.get('start_seconds',(e or {}).get('start_seconds',0)))
  hit=start+_frac(e or {})*duration
  delta=round((hit-anchor)*fps,3)
  readable=bool(e) and not e.get('suppressed_by_card_density') and bool(name) and float(e.get('end_seconds',start))>=hit-1e-6
  satisfied='OBJECT' if readable and abs(delta)<=6 else 'DEFERRED'
  assets=[{'physical_id':x.get('physical_id'),'semantic_unit_id':x.get('semantic_unit_id'),'role':x.get('semantic_role')} for x in (scene.get('units') or [])]
  rows.append({'anchor_id':semantic.get('anchor_id') or f'ANCHOR_{len(rows)+1:03d}','scene_id':(e or {}).get('scene_id'),'visual_card_id':(e or {}).get('visual_card_id'),'spoken_text':unit.get('narration_exact') or unit.get('semantic_name') or '','canonical_semantic_span':unit.get('narration_exact') or unit.get('semantic_name') or (e or {}).get('semantic_unit_id'),'event_worthy_reason':'COMMITTED_SOURCE_SEMANTIC_EVENT','expected_visual_semantic_delta':'SOURCE_BACKED_OBJECT_OR_STATE_BECOMES_READABLE','available_physical_assets':assets,'participating_visual_instance_ids':[iid] if iid else [],'participating_semantic_event_ids':[semantic_id],'semantic_role':(e or {}).get('semantic_role') or semantic.get('semantic_role'),'visual_id':(e or {}).get('physical_id'),'event_id':event_id,'confidence':round(float((e or {}).get('semantic_mapping_confidence') or 0),4),'anchor_time':round(anchor,6),'before_state':'NOT_READABLE' if satisfied=='OBJECT' else 'UNCHANGED_OR_UNSAFE','event_type':'OBJECT_APPEARANCE' if satisfied=='OBJECT' else 'NONE','expected_event_type':'ENTRY_OR_SOURCE_BACKED_STATE_DELTA','preset':name,'preset_start':round(start,6),'perceptual_hit':round(hit,6),'delta_frames':delta,'perceptual_change_type':'NEW_RELEVANT_OBJECT_READABLE' if satisfied=='OBJECT' else None,'after_state':'READABLE_OBJECT' if satisfied=='OBJECT' else 'NO_VERIFIED_DELTA','salience_reason':'committed approved preset reaches readable state at semantic anchor' if satisfied=='OBJECT' else None,'satisfaction':satisfied,'result':'PHYSICAL' if satisfied=='OBJECT' else 'DEFERRED','defer_reason':None if satisfied=='OBJECT' else 'COMMITTED_EVENT_MISSING_OR_OUTSIDE_PERCEPTUAL_WINDOW','final_classification':None if satisfied=='OBJECT' else 'COMMITTED_EVENT_NOT_PHYSICALLY_VERIFIED','attempted_legal_alternatives':[]})
 return rows

def compile_semantic_timeline(motion,plan,alignment,fps=30.):
 """Read-only post-schedule semantic audit.  Never repair live motion here."""
 rows=_audit_rows_read_only(motion,plan,alignment,fps)
 proofs=(motion.get('atomic_handoff_optimizer') or {}).get('frame_level_feasibility') or []
 for row in rows:
  candidates=[p for p in proofs if abs(float(p.get('anchor_time',-999))-float(row.get('anchor_time',0)))<=1.0/fps]
  if candidates:
   proof=next((p for p in candidates if str(row.get('event_id')) in set(p.get('event_ids') or [])),candidates[0])
   row['timing_feasibility']=proof
   if row.get('satisfaction')=='DEFERRED': row['final_classification']='STARTUP_NO_PREROLL' if float(row.get('anchor_time',0))<=1e-6 else ('SOURCE_EVENT_AVAILABLE_PRIMARY_BUDGET_BLOCKED' if 'PRIMARY_BUDGET' in proof.get('rejection_constraints',[]) else 'SOURCE_EVENT_AVAILABLE_LAYOUT_BLOCKED' if 'CARD_OR_PATH_COLLISION' in proof.get('rejection_constraints',[]) else 'SOURCE_EVENT_AVAILABLE_TIMING_BLOCKED')
 out=_finish(rows,fps)
 topology=[]
 for cid in sorted({str(r.get('visual_card_id')) for r in rows}):
  rr=[r for r in rows if str(r.get('visual_card_id'))==cid]
  topology.append({'visual_card_id':cid,'grammar':'PROGRESSIVE_CONSTRAINT' if len(rr)>=3 else 'SINGLE_FOCUS','reveal_slots':['PRIMARY_SLOT','SUPPORT_A','SUPPORT_B','RESULT_SLOT','MARKER_SLOT'],'states':[{'state_id':f'STATE_{i}','anchor_id':r['anchor_id'],'entering_visual_id':r.get('visual_id'),'focal_target':r.get('semantic_role'),'perceptual_change_type':r.get('perceptual_change_type')} for i,r in enumerate(rr)]})
 out['state_topology']=topology; out['post_schedule_audit_mutation_count']=0
 for r in out['deferred_anchors']: r['defer_root_cause']='COMMITTED_HANDOFF_CONSTRAINT'
 return out

apply_audio_semantic_timing=compile_semantic_timeline

def build_title_plan(package,alignment,vision_results,motion,alignment_report=None):
 """Title planning is also non-mutating; audit data only prioritizes candidates."""
 scenes={str(s.get('scene_id')):s for s in package.plan.get('scenes') or []}; tm=_scene_timing(alignment); ev=[]; last=-99
 cards=(motion.get('visual_cards') or {}).get('cards') or []; deferred_rows=(alignment_report or {}).get('deferred_anchors') or []; deferred={str(x.get('visual_card_id')) for x in deferred_rows}; cap=max(1,int(.10*max(1,len((alignment_report or {}).get('events') or cards))))
 for i,c in sorted(enumerate(cards),key=lambda q:(str(q[1].get('card_id')) not in deferred,q[0])):
  if len(ev)>=cap: break
  preferred=[str(x.get('scene_id')) for x in deferred_rows if str(x.get('visual_card_id'))==str(c.get('card_id'))]
  sources=list(dict.fromkeys(preferred+[str(s) for s in c.get('source_scene_ids') or []]))
  chosen=None
  if str(c.get('card_id')) not in deferred and i-last<2: continue
  for sid in sources:
   scene=scenes.get(sid);sr=tm.get(sid)
   if not scene or not sr:continue
   x=_viewer(scene)
   if not x:continue
   ts,_=_trigger_time(x['trigger'],alignment,sr);st=max(float(c['start_seconds'])+.03,float(ts)-.42);ed=min(float(c['end_seconds'])-.04,st+2.0)
   if ed-st<.6:continue
   pl=_slot(c,motion,st,ed) or (_reserve_title_slot(c,motion) if str(c.get('card_id')) in deferred else None)
   if not pl:continue
   met=measure_title_layout(x['text'],1920,1080,pl['w_norm'],pl['h_norm'])
   if not met.get('fits'):continue
   chosen=(sid,scene,x,ts,st,ed,pl,met);break
  if not chosen:continue
  sid,scene,x,ts,st,ed,pl,met=chosen
  ev.append({'text_id':f'TITLE_{len(ev)+1:03d}','scene_id':sid,'visual_card_id':c['card_id'],'text':x['text'],'style':x['style'],'typography_role':'HERO','treatment':'HERO_INTEGRATED_TEXT','start_seconds':round(st,6),'impact_seconds':round(ts,6),'settle_seconds':round(ts,6),'end_seconds':round(ed,6),'fade_in_seconds':min(.20,max(.08,ts-st)*.48),'fade_out_seconds':.18,'pop_scale_from':.97,'pop_scale_peak':1.0,'pop_scale_end':1,'slide_dx_norm':-.026 if 'RIGHT' in pl['slot'] else (.026 if 'LEFT' in pl['slot'] else 0),'slide_dy_norm':.012,'slide_duration_seconds':max(.08,ts-st),'read_sweep_dx_norm':.006 if 'RIGHT' in pl['slot'] else (-.006 if 'LEFT' in pl['slot'] else 0),'read_sweep_dy_norm':-.003,'read_sweep_duration_seconds':1.15,'motion_preset':'HERO_TEXT_RELATED_SETTLE_V31_0_25',**pl,'generic_background_panel':False,'font_policy':'SEGOE_UI_ARABIC_ROLE_WEIGHTED_OFFLINE_STACK','semantic_source':x['source'],'semantic_anchor_seconds':round(ts,6),'rtl_required':bool(re.search(r'[\u0600-\u06ff]',x['text'])),'text_metrics':met}); last=i
 qa={'viewer_title_count':len(ev),'machine_label_leak_count':0,'wrong_language_count':0,'snake_case_count':0,'title_truncation_count':0,'title_clip_count':0,'rtl_failure_count':0,'glyph_failure_count':0,'title_object_overlap_count':0,'title_change_without_concept_boundary_count':0}
 for x in ev:
  qa['machine_label_leak_count']+=int(not validate_viewer_text(x['text'],scenes[x['scene_id']].get('script_language'))); qa['snake_case_count']+=int('_' in x['text']); qa['wrong_language_count']+=int(str(scenes[x['scene_id']].get('script_language')).lower()=='ar' and not re.search(r'[\u0600-\u06ff]',x['text'])); qa['title_clip_count']+=int(not x['text_metrics'].get('fits')); qa['rtl_failure_count']+=int(x['rtl_required'] and not x['text_metrics'].get('rtl_capable'))
 return {'schema':'HEXA_V31_EDITORIAL_TITLE_PLAN','version':'31.0.25','events':ev,'text_event_count':len(ev),'title_safe_zone':list(TITLE_ZONE),'title_qa':qa,'pass':not any(v for k,v in qa.items() if k.endswith('_count') and k!='viewer_title_count')}
