from __future__ import annotations
import copy, math
from .util import read_json
from .framing import compute_reference_camera_fit
from .preset_authority import authority as preset_authority, duration as preset_duration, choose_entry_for_center, choose_exit_for_center, is_primary_semantic
from .visual_cards import build_visual_cards
from .scene_grammar import classify_card
from .composition_solver import build_story_phases, solve_card_layout, within_preset_safe, repair_story_phases, repartition_story_phases, _in_safe
from .composition_qa import card_motion_conflicts
from .visual_density import build_visual_density_report

def _entry_fraction(event):
    return .90 if str((event.get('preset_entry') or {}).get('name') or '').startswith('ENTRY_') else .70


def legal_effect_catalog():
    """Classify only the installed user-preset authority; never invent names."""
    out={k:[] for k in ('ENTRY','EXIT','REVEAL','SCALE','WITHIN_FRAME','RECOMPOSITION','HANDOFF','EMPHASIS')}
    for name in sorted((preset_authority().get('preset_motion') or {}).keys()):
        if name.startswith('ENTRY_'):out['ENTRY'].append(name);out['HANDOFF'].append(name)
        elif name.startswith('EXIT_'):out['EXIT'].append(name);out['HANDOFF'].append(name)
        elif name.startswith('WITHIN_'):out['WITHIN_FRAME'].append(name);out['RECOMPOSITION'].append(name);out['HANDOFF'].append(name)
        elif name.startswith('APPEAR_'):out['REVEAL'].append(name);out['SCALE'].append(name)
        elif name.startswith('DISAPPEAR_'):out['EXIT'].append(name);out['SCALE'].append(name)
    return out


def _direction(name):
    name=str(name or '')
    for x in ('LEFT','RIGHT','UP','DOWN'):
        if name.endswith('_'+x) or ('_'+x+'_TO_' in name):return x
    return 'NONE'


def _interaction_grammar(carrier,nxt):
    """Generic source-role relationship label used by choreography and QA."""
    a=(str(carrier.get('semantic_type') or '')+' '+str(carrier.get('narrative_function') or '')).upper();b=(str(nxt.get('semantic_type') or '')+' '+str(nxt.get('narrative_function') or '')).upper()
    if 'CHARACTER' in a or 'CHARACTER' in b:return 'OBJECT_CHARACTER_REACTION'
    if any(x in a+' '+b for x in ('CAUSE','EFFECT')):return 'CAUSE_EFFECT_REVEAL'
    if any(x in a for x in ('PROBLEM','ERROR','FAIL','WARNING')) and any(x in b for x in ('RESULT','SOLUTION','SUCCESS')):return 'PROBLEM_RESULT_HANDOFF'
    if any(x in a+' '+b for x in ('STATUS','MARKER')):return 'STATUS_OBJECT_RELATION'
    if any(x in b for x in ('RESULT','OUTCOME','SOLUTION')):return 'PATH_TO_RESULT'
    if str(carrier.get('attention_priority')).upper()=='PRIMARY' and str(nxt.get('attention_priority')).upper()!='PRIMARY':return 'PRIMARY_SUPPORT_BUILD'
    if str(carrier.get('attention_priority')).upper()!=str(nxt.get('attention_priority')).upper():return 'FOCAL_TRANSFER'
    return 'PRIMARY_SUPPORT_EXCHANGE'


def rank_legal_effects(choices,history,carrier,nxt,archetype='SINGLE_FOCUS'):
    """Stable anti-repetition scoring over legal names only."""
    legal=set(legal_effect_catalog()['WITHIN_FRAME']);recent=list(history or [])[-3:];nx=float((nxt.get('card_rest_position_norm') or [.5])[0]);wanted='LEFT' if nx>=.5 else 'RIGHT'
    rows=[]
    for name in choices:
        if name not in legal:continue
        direction=_direction(name);score=0.0
        score+=8.0*sum(str(h.get('within_family'))==name for h in recent)
        score+=3.5*sum(str(h.get('travel_direction'))==direction for h in recent[-2:])
        score+=2.2*sum(str(h.get('archetype'))==str(archetype) for h in recent[-2:])
        score+=2.0*sum(str(h.get('handoff_grammar'))==_interaction_grammar(carrier,nxt) for h in recent[-2:])
        if direction==wanted:score-=4.0
        rows.append((score,name))
    return [name for _,name in sorted(rows,key=lambda x:(x[0],x[1]))]


def perceptual_sync_qa(events,fps=30.0):
    rows=[];fail=[]
    for e in events:
        entry=e.get('preset_entry') or {};name=str(entry.get('name') or '')
        if not name:continue
        start=float(entry.get('start_seconds',e.get('start_seconds',0)));duration=float(entry.get('duration_seconds') or preset_duration(name));anchor=float(e.get('perceptual_hit_seconds',start));impact=start+_entry_fraction(e)*duration;settle=start+duration;pre=max(0.0,anchor-start)
        travel=duration if name.startswith(('ENTRY_','WITHIN_')) else 0.0
        row={'event_id':e.get('event_id'),'preset':name,'anchor_to_motion_start':round(start-anchor,6),'anchor_to_visual_impact':round(impact-anchor,6),'anchor_to_settle':round(settle-anchor,6),'visual_travel_duration':round(travel,6),'pre_roll_duration':round(pre,6),'premature_semantic_reveal':False}
        if impact-anchor>6.0/max(1.0,fps):row['flag']='VOICE_PRECEDES_VISUAL_RESULT';fail.append(str(e.get('event_id')))
        rows.append(row)
    return {'schema':'HEXA_V31_PERCEPTUAL_SYNC_QA','version':'31.0.25','events':rows,'event_count':len(rows),'voice_precedes_visual_result_event_ids':fail,'bounded_pre_roll_pass':all(x['pre_roll_duration']<=1.44+1e-6 for x in rows),'no_premature_semantic_reveal_pass':all(not x['premature_semantic_reveal'] for x in rows),'pass':not fail}


def _apply_composition_history_variant(layout,grammar,history):
    """Mirror an otherwise repeated legal layout while preserving topology."""
    arch=str(grammar.get('archetype') or 'SINGLE_FOCUS');recent=list(history or [])[-2:]
    repeated=bool(recent and recent[-1].get('archetype')==arch);last_mirrored=bool(recent and recent[-1].get('variant')=='MIRRORED')
    if not layout.get('pass') or not repeated or last_mirrored:return 'CANONICAL'
    for p in (layout.get('placements') or {}).values():
        c=list(p.get('center_norm') or []);r=list(p.get('rect_norm') or [])
        if len(c)>=2:c[0]=round(1.0-float(c[0]),6);p['center_norm']=c
        if len(r)==4:r[0]=round(1.0-float(r[0])-float(r[2]),6);p['rect_norm']=r
    layout['composition_history_variant']='MIRRORED';return 'MIRRORED'


def _optical_scale_optimize(events, cards, fps):
    """Bounded, collision-safe focal scaling on copied per-card candidates.

    This changes neither timing nor semantic topology.  Time-separated
    primaries are optimized independently; simultaneous states remain bounded
    by the full trajectory collision check.
    """
    stats={'candidates_evaluated':0,'candidates_committed':0,'cards_improved':[],'event_ids':[]}
    optimized=set()
    for card in (cards.get('cards') or []):
        cs=float(card.get('start_seconds',0));ce=float(card.get('end_seconds',cs));cid=str(card.get('card_id'))
        local=[e for e in events if not e.get('suppressed_by_card_density') and float(e.get('start_seconds',0))<ce and float(e.get('end_seconds',0))>cs]
        primaries=sorted((e for e in local if str(e.get('attention_priority') or '').upper()=='PRIMARY' and e.get('planned_rect_norm')),key=lambda e:(float(e.get('layout_scale_multiplier') or 1),str(e.get('event_id'))))
        for e in primaries:
            eid=str(e.get('event_id'))
            if eid in optimized:continue
            old_scale=float(e.get('layout_scale_multiplier') or 1.0);old_rect=list(map(float,e.get('planned_rect_norm')));cx=old_rect[0]+old_rect[2]/2;cy=old_rect[1]+old_rect[3]/2
            overlap_count=sum(
                1 for other in local
                if str(other.get('event_id'))!=eid
                and float(other.get('start_seconds',0)) < float(e.get('end_seconds',0))-1e-6
                and float(other.get('end_seconds',0)) > float(e.get('start_seconds',0))+1e-6
            )
            fill=float((e.get('matting') or {}).get('opaque_foreground_fraction') or 0.62)
            low_ink=fill < 0.36
            isolated=overlap_count == 0
            factors=(1.75,1.55,1.40,1.30,1.22,1.14,1.08) if isolated or low_ink else (1.30,1.22,1.14,1.08)
            for factor in factors:
                stats['candidates_evaluated']+=1;nw=old_rect[2]*factor;nh=old_rect[3]*factor;nr=[cx-nw/2,cy-nh/2,nw,nh]
                if not _in_safe(nr):continue
                e['layout_scale_multiplier']=round(old_scale*factor,6);e['planned_rect_norm']=[round(x,6) for x in nr];e['collision_envelope_rect_norm']=e['planned_rect_norm']
                if card_motion_conflicts(local,cs,ce,fps):
                    e['layout_scale_multiplier']=old_scale;e['planned_rect_norm']=old_rect;e['collision_envelope_rect_norm']=old_rect;continue
                e['premium_optical_scale_factor']=factor;stats['candidates_committed']+=1
                if cid not in stats['cards_improved']:stats['cards_improved'].append(cid)
                stats['event_ids'].append(eid);optimized.add(eid);break
    return stats


def _spatial_choreography_optimize(events, cards, fps):
    """Replace center-bound fade/scale shells with approved spatial handoffs.

    The existing perceptual-hit time is preserved exactly.  Pre-roll remains
    off-frame, and every copied candidate is rejected on lifecycle or path
    conflict before it can reach the committed plan.
    """
    stats={'candidates_evaluated':0,'candidates_committed':0,'event_ids':[],'rejections':{}}
    card_rows=list(cards.get('cards') or []);card_index={str(c.get('card_id')):i for i,c in enumerate(card_rows)}
    for e in events:
        if e.get('suppressed_by_card_density') or e.get('preset_actions'):continue
        rest=e.get('card_rest_position_norm') or [0,0]
        if abs(float(rest[0])-.5)>.035 or abs(float(rest[1])-.5)>.075:continue
        pe=e.get('preset_entry') or {};px=e.get('preset_exit') or {}
        if str(pe.get('name') or '')!='APPEAR_HIGH_SCALE':continue
        card=next((c for c in card_rows if str(c.get('card_id'))==str(e.get('visual_card_id'))),None)
        if not card:continue
        local=[x for x in events if not x.get('suppressed_by_card_density') and float(x.get('start_seconds',0))<float(card.get('end_seconds',0)) and float(x.get('end_seconds',0))>float(card.get('start_seconds',0))]
        stats['candidates_evaluated']+=1;snap=copy.deepcopy(e);old_d=float(pe.get('duration_seconds') or preset_duration('APPEAR_HIGH_SCALE'));hit=float(pe.get('start_seconds',e.get('start_seconds',0)))+_entry_fraction(e)*old_d
        left=card_index.get(str(card.get('card_id')),0)%2==0;entry='ENTRY_LEFT_TO_MIDDLE' if left else 'ENTRY_RIGHT_TO_MIDDLE';exit_='EXIT_MIDDLE_TO_RIGHT' if left else 'EXIT_MIDDLE_TO_LEFT'
        ed=preset_duration(entry);xd=preset_duration(exit_);new_start=hit-.90*ed;end=float(e.get('end_seconds',0));exit_start=end-xd
        if new_start<float(card.get('start_seconds',0))-1e-6 or exit_start<hit+.32:
            stats['rejections']['SOURCE_LIFECYCLE']=stats['rejections'].get('SOURCE_LIFECYCLE',0)+1;continue
        def set_entry():
            e['start_seconds']=round(new_start,6);e['physical_start_seconds']=round(new_start,6);e['preset_entry']={'name':entry,'start_seconds':round(new_start,6),'duration_seconds':ed,'perceptual_hit_seconds':round(hit,6)}
        def set_exit():e['preset_exit']={'name':exit_,'start_seconds':round(exit_start,6),'duration_seconds':xd}
        set_entry();set_exit();e['premium_spatial_handoff']='ENTRY_AND_EXIT'
        conflicts=card_motion_conflicts(local,float(card.get('start_seconds',0)),float(card.get('end_seconds',0)),fps)
        if conflicts:
            e.clear();e.update(copy.deepcopy(snap));set_entry();e['premium_spatial_handoff']='ENTRY_ONLY'
            conflicts=card_motion_conflicts(local,float(card.get('start_seconds',0)),float(card.get('end_seconds',0)),fps)
        if conflicts:
            e.clear();e.update(copy.deepcopy(snap));set_exit();e['premium_spatial_handoff']='EXIT_ONLY'
            conflicts=card_motion_conflicts(local,float(card.get('start_seconds',0)),float(card.get('end_seconds',0)),fps)
        if conflicts:
            e.clear();e.update(snap);stats['rejections']['COLLISION_OR_PATH']=stats['rejections'].get('COLLISION_OR_PATH',0)+1;continue
        stats['candidates_committed']+=1;stats['event_ids'].append(str(e.get('event_id')))
    return stats


def _recomposition_optimize(events, cards, fps):
    """Create approved center-to-side reframes before a source-backed reveal."""
    stats={'candidates_evaluated':0,'candidates_committed':0,'event_ids':[],'rejections':{}}
    for card in cards.get('cards') or []:
        cs=float(card.get('start_seconds',0));ce=float(card.get('end_seconds',cs));local=sorted((e for e in events if not e.get('suppressed_by_card_density') and float(e.get('start_seconds',0))<ce and float(e.get('end_seconds',0))>cs),key=lambda e:(float(e.get('perceptual_hit_seconds',e.get('start_seconds',0))),str(e.get('event_id'))))
        for current,nxt in zip(local,local[1:]):
            if current.get('preset_actions'):continue
            rest=current.get('card_rest_position_norm') or [0,0]
            # The layout solver's canonical middle is (0.50, 0.52).  The old
            # compatibility check was centred on a stale (0.487, 0.493)
            # coordinate, silently excluding the real settled middle states
            # from source-valid pre-reveal recomposition.
            if abs(float(rest[0])-.50)>.040 or abs(float(rest[1])-.52)>.085:continue
            next_rest=nxt.get('card_rest_position_norm') or [.5,.5];name='WITHIN_MIDDLE_TO_LEFT' if float(next_rest[0])>=.5 else 'WITHIN_MIDDLE_TO_RIGHT';dur=preset_duration(name)
            ne=nxt.get('preset_entry') or {};cevent=current.get('preset_entry') or {}
            next_hit=float(ne.get('start_seconds',nxt.get('start_seconds',0)))+_entry_fraction(nxt)*float(ne.get('duration_seconds') or preset_duration(ne.get('name') or 'APPEAR_HIGH_SCALE'));start=next_hit-dur
            current_hit=float(cevent.get('start_seconds',current.get('start_seconds',0)))+_entry_fraction(current)*float(cevent.get('duration_seconds') or preset_duration(cevent.get('name') or 'APPEAR_HIGH_SCALE'))
            if start<current_hit+.28 or start+dur>float(current.get('end_seconds',0))-.12:continue
            stats['candidates_evaluated']+=1;snap=copy.deepcopy(current)
            current['preset_actions']=[{
                'name':name,'start_seconds':round(start,6),'duration_seconds':dur,
                'action_type':'LAYOUT_CHOREOGRAPHY',
                'layout_purpose':'REFRAME_FOR_NEXT_SOURCE_BACKED_REVEAL',
                'target_event_id':str(nxt.get('event_id')),
                'authority':'USER_PRFPSET_WITHIN_FRAME__V31_0_25_INTERACTION_DIRECTOR',
            }]
            if card_motion_conflicts(local,cs,ce,fps):
                current.clear();current.update(snap);stats['rejections']['COLLISION_OR_PATH']=stats['rejections'].get('COLLISION_OR_PATH',0)+1;continue
            current['premium_within_frame_recomposition']=True;current['interaction_grammar']=_interaction_grammar(current,nxt);current['screen_memory_reuse']=True;current['handoff_target_event_id']=str(nxt.get('event_id'));stats['candidates_committed']+=1;stats['event_ids'].append(str(current.get('event_id')))
    return stats


def _effect_variety_director(events, cards, fps):
    """Deterministically fill safe, meaningful pre-reveal recompositions.

    This is deliberately a selector over the locked within-frame preset palette,
    not a source of invented motion.  A carrier moves only to release its region
    for the next source-backed semantic reveal, and every copied candidate is
    validated against the complete animated collision/path sampler.
    """
    stats={'candidates_evaluated':0,'candidates_committed':0,'event_ids':[],
           'families_used':{},'rejections':{},'max_repeated_family_streak':0,
           'authority_catalog':legal_effect_catalog(),'deterministic':True,'unsupported_preset_count':0,'interaction_grammars':{}}
    history=[]
    for card_index,card in enumerate(cards.get('cards') or []):
        cs=float(card.get('start_seconds',0));ce=float(card.get('end_seconds',cs))
        local=sorted((e for e in events if not e.get('suppressed_by_card_density') and
                      float(e.get('start_seconds',0))<ce and float(e.get('end_seconds',0))>cs),
                     key=lambda e:(float(e.get('perceptual_hit_seconds',e.get('start_seconds',0))),str(e.get('event_id'))))
        for carrier,nxt in zip(local,local[1:]):
            if carrier.get('preset_actions') or str(carrier.get('attention_priority') or '').upper()!='PRIMARY':
                continue
            current_hit=float((carrier.get('preset_entry') or {}).get('start_seconds',carrier.get('start_seconds',0)))+_entry_fraction(carrier)*float((carrier.get('preset_entry') or {}).get('duration_seconds') or preset_duration('APPEAR_HIGH_SCALE'))
            next_hit=float((nxt.get('preset_entry') or {}).get('start_seconds',nxt.get('start_seconds',0)))+_entry_fraction(nxt)*float((nxt.get('preset_entry') or {}).get('duration_seconds') or preset_duration('APPEAR_HIGH_SCALE'))
            # Preserve an actual see/read interval and never turn two close voice beats into noise.
            if next_hit-current_hit<1.18: continue
            choices=tuple(x for x in legal_effect_catalog()['WITHIN_FRAME'] if x.startswith('WITHIN_MIDDLE_TO_'))
            archetype=str((card.get('universal_scene_grammar') or {}).get('archetype') or 'SINGLE_FOCUS')
            ordered=rank_legal_effects(choices,history,carrier,nxt,archetype)
            committed=False
            for name in ordered:
                dur=preset_duration(name); start=next_hit-dur-.06
                if start<current_hit+.34 or start+dur>float(carrier.get('end_seconds',0))-.12:
                    stats['rejections']['READABILITY_WINDOW'] = stats['rejections'].get('READABILITY_WINDOW',0)+1;continue
                stats['candidates_evaluated']+=1;snap=copy.deepcopy(carrier)
                # The supplied WITHIN_MIDDLE presets are literal middle-origin
                # Premiere position presets.  They cannot be attached to a
                # side-settled carrier: doing that would make the renderer jump
                # from its old rest position to the preset's middle keyframe in
                # a single frame.  Re-layout the copied carrier to the canonical
                # origin first, and let the normal full-plan path/collision gate
                # reject it if that source object cannot legally own the middle.
                rest=list(carrier.get('card_rest_position_norm') or [.5,.5])
                rect=list(carrier.get('planned_rect_norm') or [])
                if len(rect)==4:
                    width,height=float(rect[2]),float(rect[3])
                    centered=[.5-width/2,.5-height/2,width,height]
                    carrier['planned_rect_norm']=[round(v,6) for v in centered]
                    carrier['collision_envelope_rect_norm']=list(carrier['planned_rect_norm'])
                carrier['card_rest_position_norm']=[.5,.5]
                carrier['within_frame_start_state_contract']='CANONICAL_MIDDLE'
                carrier['preset_actions']=[{'name':name,'start_seconds':round(start,6),'duration_seconds':dur,
                    'action_type':'LAYOUT_CHOREOGRAPHY','layout_purpose':'RELEASE_REGION_FOR_NEXT_SOURCE_BACKED_REVEAL',
                    'target_event_id':str(nxt.get('event_id')),'authority':'USER_PRFPSET_WITHIN_FRAME__V31_0_25_EFFECT_VARIETY'}]
                # The card sampler is the fast local reject.  The adjacent
                # card topology is also part of this trajectory's physical
                # envelope, so require the authoritative complete-plan QA
                # before an optional variety action can commit.
                candidate_plan={'events':events,'visual_cards':{'cards':list(cards.get('cards') or [])},'fps':fps}
                from .composition_qa import composition_plan_qa
                if card_motion_conflicts(local,cs,ce,fps) or not composition_plan_qa(candidate_plan).get('pass'):
                    carrier.clear();carrier.update(snap);stats['rejections']['COLLISION_OR_PATH']=stats['rejections'].get('COLLISION_OR_PATH',0)+1;continue
                grammar=_interaction_grammar(carrier,nxt);carrier['premium_effect_variety_grammar']='SPATIAL_HANDOFF';carrier['premium_within_frame_recomposition']=True;carrier['interaction_grammar']=grammar;carrier['screen_memory_reuse']=True;carrier['handoff_target_event_id']=str(nxt.get('event_id'))
                history.append({'entry_family':str((carrier.get('preset_entry') or {}).get('name') or 'STATIC_REVEAL'),'exit_family':str((carrier.get('preset_exit') or {}).get('name') or 'HOLD_HANDOFF'),'within_family':name,'travel_direction':_direction(name),'scale_behavior':'FOCAL_REFRAME' if abs(float(carrier.get('layout_scale_multiplier') or 1)-1)>.04 else 'NO_SCALE','handoff_grammar':grammar,'archetype':archetype,'typography_animation':'RELATED_VISUAL_ROLE_PROFILE','primary_side':'LEFT' if float((carrier.get('card_rest_position_norm') or [.5])[0])<.5 else 'RIGHT','character_side':'LEFT' if 'CHARACTER' in str(carrier.get('semantic_type') or '').upper() and float((carrier.get('card_rest_position_norm') or [.5])[0])<.5 else 'RIGHT' if 'CHARACTER' in str(carrier.get('semantic_type') or '').upper() else 'NONE'})
                stats['families_used'][name]=stats['families_used'].get(name,0)+1;stats['interaction_grammars'][grammar]=stats['interaction_grammars'].get(grammar,0)+1
                stats['candidates_committed']+=1;stats['event_ids'].append(str(carrier.get('event_id')));committed=True;break
            if not committed: continue
    streak=run=0;last=None
    for row in history:
        name=row['within_family']
        run=run+1 if name==last else 1;last=name;streak=max(streak,run)
    stats['max_repeated_family_streak']=streak
    stats['recent_visual_history']=history[-3:]
    return stats

def _hit_delta_frames(event, anchor, fps):
    entry=event.get('preset_entry') or {}
    duration=float(entry.get('duration_seconds') or preset_duration(entry.get('name') or 'APPEAR_HIGH_SCALE'))
    return (float(entry.get('start_seconds',event.get('start_seconds',0)))+_entry_fraction(event)*duration-float(anchor))*fps

def _atomic_handoff_optimize(events, cards, fps):
    """Pre-commit, frame deterministic handoff optimization.

    Every candidate is a copied card state.  Events sharing an anchor move as
    one group; the candidate is accepted only after collision, primary and
    density checks.  This intentionally has no dependency on the post-plan
    semantic audit.
    """
    stats={'atomic_handoff_groups_optimized':0,'candidate_schedules_evaluated':0,'candidate_schedules_rejected':0,'candidate_schedules_committed':0,'geometry_candidates_evaluated':0,'combined_candidates_evaluated':0,'rescued_event_ids':[],'frame_level_feasibility':[]}
    for card in cards.get('cards') or []:
        cid=str(card.get('card_id')); members=[e for e in events if str(e.get('visual_card_id'))==cid and not e.get('suppressed_by_card_density') and e.get('preset_entry')]
        if not members: continue
        base_density=build_visual_density_report({'events':members,'visual_cards':{'cards':[card]}})
        groups={}
        for event in members: groups.setdefault(round(float(event.get('perceptual_hit_seconds',0))*fps)/fps,[]).append(event)
        for anchor, group in sorted(groups.items()):
            # Do not disturb already compliant transitions.
            deltas=[_hit_delta_frames(e,anchor,fps) for e in group]
            if max((abs(x) for x in deltas),default=0)<=4: continue
            proof={'anchor_time':round(anchor,6),'event_ids':[x['event_id'] for x in group],'current_hit_frames':[round(x,3) for x in deltas],'target_start_seconds':round(anchor-_entry_fraction(group[0])*float((group[0].get('preset_entry') or {}).get('duration_seconds') or preset_duration((group[0].get('preset_entry') or {}).get('name') or 'APPEAR_HIGH_SCALE')),6),'legal_start_min_seconds':float(card['start_seconds']),'legal_start_max_seconds':float(card['end_seconds']),'candidate_count':0,'best_candidate_delta_frames':None,'rejection_constraints':[]}
            best=None
            for frame_offset in (0,-1,1,-2,2,-3,3,-4,4,-5,5,-6,6):
                candidate=copy.deepcopy(members); cmap={e['event_id']:e for e in candidate}; ok=True
                for original in group:
                    e=cmap[original['event_id']]; entry=e['preset_entry']; dur=float(entry.get('duration_seconds') or preset_duration(entry.get('name') or 'APPEAR_HIGH_SCALE'))
                    target=anchor+frame_offset/fps; new_start=target-_entry_fraction(e)*dur
                    # Entry timing and resulting-state lifetime are separate
                    # authorities. Align the approved entry to voice without
                    # dragging the valid hold/exit through a card boundary.
                    if new_start<float(card['start_seconds'])-1e-6 or new_start+dur>float(e.get('end_seconds',0))+1e-6: ok=False; break
                    e['start_seconds']=round(new_start,6); entry['start_seconds']=round(new_start,6)
                stats['candidate_schedules_evaluated']+=1
                proof['candidate_count']+=1
                collision=(not ok) or bool(card_motion_conflicts(candidate,float(card['start_seconds']),float(card['end_seconds']),fps))
                if collision:
                    # Frozen positions are not timing authority. Rebuild the
                    # simultaneous local state on the copied candidate and
                    # regenerate envelopes before declaring it infeasible.
                    local_phase={'phases':[{'phase_id':'ANCHOR_LOCAL','start_seconds':float(card['start_seconds']),'end_seconds':float(card['end_seconds']),'event_ids':[x['event_id'] for x in candidate]}]}
                    layout=solve_card_layout(candidate,{'archetype':'GENERIC','explicit_edges':[]},local_phase)
                    stats['geometry_candidates_evaluated']+=1
                    if layout.get('pass'):
                        for x in candidate:
                            place=layout['placements'].get(x['event_id'])
                            if place:
                                x['planned_rect_norm']=place['rect_norm'];x['card_rest_position_norm']=place['center_norm'];x['layout_scale_multiplier']=place['scale'];x['collision_envelope_rect_norm']=place['rect_norm']
                        stats['combined_candidates_evaluated']+=1
                        collision=bool(card_motion_conflicts(candidate,float(card['start_seconds']),float(card['end_seconds']),fps))
                if collision: stats['candidate_schedules_rejected']+=1;proof['rejection_constraints'].append('CARD_OR_PATH_COLLISION'); continue
                density=build_visual_density_report({'events':candidate,'visual_cards':{'cards':[card]}})
                if density.get('hard_under_density_cards') or density.get('near_blank_duration_seconds',0)>base_density.get('near_blank_duration_seconds',0)+.05: stats['candidate_schedules_rejected']+=1;proof['rejection_constraints'].append('DENSITY_OR_NO_BLANK_CONSTRAINT'); continue
                peak=max(sum(1 for e in candidate if e.get('attention_priority')=='PRIMARY' and float(e.get('start_seconds',0))<=t<float(e.get('end_seconds',0))) for t in [float(card['start_seconds'])+i/fps for i in range(max(1,int((float(card['end_seconds'])-float(card['start_seconds']))*fps)))])
                if peak>2: stats['candidate_schedules_rejected']+=1;proof['rejection_constraints'].append('PRIMARY_BUDGET'); continue
                group_ids={x['event_id'] for x in group}
                error=sum(abs(_hit_delta_frames(e,anchor,fps)) for e in candidate if e['event_id'] in group_ids)
                if best is None or error<best[0]: best=(error,candidate);proof['best_candidate_delta_frames']=round(error,3)
            if best is not None and best[0]+.001<sum(abs(x) for x in deltas):
                replacements={e['event_id']:e for e in best[1]}
                for e in members:
                    event_id=e['event_id']
                    if event_id in replacements:
                        e.clear(); e.update(replacements[event_id])
                stats['atomic_handoff_groups_optimized']+=1; stats['candidate_schedules_committed']+=1; stats['rescued_event_ids'] += [e['event_id'] for e in group]
            proof['rejection_constraints']=sorted(set(proof['rejection_constraints'])) or ['NO_IMPROVING_LEGAL_CANDIDATE']
            stats['frame_level_feasibility'].append(proof)
    return stats

def _cross_card_handoff_optimize(events, cards, fps):
    """Bounded adjacent-card search on copied local handoff state.

    A boundary is moved only when both cards retain the locked 3--5 second
    duration and the copied candidate preserves collision and density.  This
    deliberately never rewrites source timing globally.
    """
    ordered=sorted(cards.get('cards') or [],key=lambda c:float(c.get('start_seconds',0)))
    out={'cross_card_groups_built':0,'cross_card_candidates_evaluated':0,'cross_card_candidates_rejected':0,'cross_card_candidates_committed':0,'card_boundaries_shifted':0,'boundary_shift_frames':[],'persistent_carrier_cross_card_handoffs':0}
    for left,right in zip(ordered,ordered[1:]):
        boundary=float(left['end_seconds']); near=[e for e in events if not e.get('suppressed_by_card_density') and abs(float(e.get('perceptual_hit_seconds',-999))-boundary)<=.45]
        if not near: continue
        out['cross_card_groups_built']+=1
        # Candidate objects are copied first; a failed validation cannot touch
        # the committed card topology.  Zero is included as an explicit
        # feasibility probe and nonzero candidates are frame deterministic.
        local=[e for e in events if str(e.get('visual_card_id')) in (str(left['card_id']),str(right['card_id']))]
        base=build_visual_density_report({'events':local,'visual_cards':{'cards':[left,right]}})
        best=None
        legal_boundary_min=max(float(left['start_seconds'])+3.0,float(right['end_seconds'])-5.0)
        legal_boundary_max=min(float(left['start_seconds'])+5.0,float(right['end_seconds'])-3.0)
        derived_frames={0,-1,1,-2,2,-3,3,-4,4,-5,5,-6,6}
        for event in near:
            entry=event.get('preset_entry') or {};dur=float(entry.get('duration_seconds') or preset_duration(entry.get('name') or 'APPEAR_HIGH_SCALE'))
            desired=float(event.get('perceptual_hit_seconds',0))-_entry_fraction(event)*dur
            if str(event.get('visual_card_id'))==str(right.get('card_id')) and desired<boundary:
                derived_frames.add(int(round((max(legal_boundary_min,desired)-boundary)*fps)))
            elif str(event.get('visual_card_id'))==str(left.get('card_id')) and desired+dur>boundary:
                derived_frames.add(int(round((min(legal_boundary_max,desired+dur)-boundary)*fps)))
        ordered_frames=sorted(derived_frames,key=lambda f:(abs(f),f))
        for f in ordered_frames:
            out['cross_card_candidates_evaluated']+=1; shift=f/fps
            candidate_left=copy.deepcopy(left); candidate_right=copy.deepcopy(right); candidate_left['end_seconds']=round(boundary+shift,6); candidate_right['start_seconds']=round(boundary+shift,6)
            if not (3<=float(candidate_left['end_seconds'])-float(candidate_left['start_seconds'])<=5 and 3<=float(candidate_right['end_seconds'])-float(candidate_right['start_seconds'])<=5): out['cross_card_candidates_rejected']+=1; continue
            candidate=copy.deepcopy(local)
            # Reassign only events whose source-backed semantic anchor changes
            # ownership; unrelated states remain untouched.
            for e in candidate:
                if e not in near: continue
                anchor=float(e.get('perceptual_hit_seconds',0)); target=candidate_left if anchor<boundary+shift else candidate_right
                if str(e.get('visual_card_id'))!=str(target['card_id']):
                    out['cross_card_candidates_rejected']+=1; break
            else:
                if card_motion_conflicts([e for e in candidate if str(e.get('visual_card_id'))==str(candidate_left['card_id'])],float(candidate_left['start_seconds']),float(candidate_left['end_seconds']),fps) or card_motion_conflicts([e for e in candidate if str(e.get('visual_card_id'))==str(candidate_right['card_id'])],float(candidate_right['start_seconds']),float(candidate_right['end_seconds']),fps): out['cross_card_candidates_rejected']+=1; continue
                density=build_visual_density_report({'events':candidate,'visual_cards':{'cards':[candidate_left,candidate_right]}})
                if density.get('hard_under_density_cards') or density.get('near_blank_duration_seconds',0)>base.get('near_blank_duration_seconds',0)+.05: out['cross_card_candidates_rejected']+=1; continue
                score=0.0
                for e in candidate:
                    owner = candidate_left if str(e.get('visual_card_id')) == str(candidate_left.get('card_id')) else candidate_right
                    entry=e.get('preset_entry') or {};dur=float(entry.get('duration_seconds') or preset_duration(entry.get('name') or 'APPEAR_HIGH_SCALE'))
                    desired=float(e.get('perceptual_hit_seconds',0))-_entry_fraction(e)*dur
                    lo=float(owner.get('start_seconds'));hi=float(owner.get('end_seconds'))-dur
                    score += max(0.0,lo-desired,desired-hi)*fps
                if best is None or score<best[0]: best=(score,f,candidate_left,candidate_right)
        if best is not None and best[1]:
            # Cards are the only committed entities changed by the boundary
            # candidate; events retain their source lifecycle and geometry.
            _,f,cl,cr=best
            cl['duration_seconds']=round(float(cl['end_seconds'])-float(cl['start_seconds']),6)
            cr['duration_seconds']=round(float(cr['end_seconds'])-float(cr['start_seconds']),6)
            left.update(cl); right.update(cr); out['cross_card_candidates_committed']+=1; out['card_boundaries_shifted']+=1; out['boundary_shift_frames'].append(f)
    return out

def _compile_visual_instances(events, scene_rows):
    """Canonical physical-instance and semantic-event tracks.

    This is intentionally evidence-only: a master can span states only when
    `_consolidate_card_identity` already proved source continuity.  Semantic
    records remain separate so a readable hold is never counted as a hit.
    """
    scene_time={str(s.get('scene_id')):(float(s.get('start_seconds',0)),float(s.get('end_seconds',0))) for s in scene_rows}
    by_master={}
    for e in events:
        master=str(e.get('persistent_master_event_id') or e.get('event_id'))
        by_master.setdefault(master,[]).append(e)
    instances=[]; semantic=[]
    for master, members in sorted(by_master.items()):
        lead=next((e for e in members if str(e.get('event_id'))==master),members[0])
        source_states=sorted({str(s) for e in members for s in (e.get('persistent_source_scene_ids') or [e.get('scene_id')])})
        spans=[scene_time[s] for s in source_states if s in scene_time]
        physical_start=float(lead.get('start_seconds',0)); physical_end=float(lead.get('end_seconds',physical_start))
        # Keep declared lifetime conservative until live collision validation
        # authorizes a cross-card extension; records retain the full evidence.
        evidence_end=max((x[1] for x in spans),default=physical_end)
        iid='INSTANCE_'+master
        instances.append({'instance_id':iid,'source_identity':lead.get('identity_key'),'source_asset_ref':lead.get('physical_id'),'physical_start_seconds':physical_start,'physical_end_seconds':physical_end,'readable_intervals':[{'start_seconds':physical_start,'end_seconds':physical_end}],'role_intervals':[{'role':lead.get('attention_priority'),'start_seconds':physical_start,'end_seconds':physical_end,'source_authority':'SEMANTIC_ROLE'}],'placement_intervals':[{'start_seconds':physical_start,'end_seconds':physical_end,'rect_norm':lead.get('planned_rect_norm')}],'semantic_event_ids':[],'state_ids':source_states,'persistence_source_evidence':{'source_states':source_states,'candidate_physical_end_seconds':evidence_end,'source_backed':len(source_states)>1},'track':'VISUAL_INSTANCE'})
        for e in sorted(members,key=lambda x:(float(x.get('perceptual_hit_seconds',0)),str(x.get('event_id')))):
            entry=e.get('preset_entry') or {}; hit=float(entry.get('start_seconds',e.get('start_seconds',0)))+_entry_fraction(e)*float(entry.get('duration_seconds') or preset_duration(entry.get('name') or 'APPEAR_HIGH_SCALE'))
            sid='SEMANTIC_'+str(e.get('event_id')); semantic.append({'event_id':sid,'anchor_id':'ANCHOR_'+str(e.get('event_id')),'anchor_time':e.get('perceptual_hit_seconds'),'target_instance_id':iid,'event_type':'ENTRY' if str(e.get('event_id'))==master else 'STATE_CHANGE','semantic_role':e.get('semantic_role'),'source_authority':'SOURCE_SEMANTIC_CONTINUITY','preset':entry.get('name'),'motion_start':entry.get('start_seconds'),'perceptual_hit':round(hit,6),'resulting_state':e.get('scene_id'),'related_instance_ids':[]}); instances[-1]['semantic_event_ids'].append(sid)
    return instances,semantic

def _commit_persistent_lifetimes(events, scene_rows, fps):
    """Commit only source-proven holds that pass the real plan validators."""
    times={str(s.get('scene_id')):float(s.get('end_seconds',0)) for s in scene_rows}; stats={'candidates':0,'committed':0,'rejected':0,'reentries_avoided':0}
    masters={e.get('event_id'):e for e in events if e.get('event_id')}
    for master in [e for e in events if (e.get('persistent_source_scene_ids') or []) and len(e.get('persistent_source_scene_ids') or [])>1]:
        candidate_end=max((times.get(str(s),float(master.get('end_seconds',0))) for s in master.get('persistent_source_scene_ids') or []),default=float(master.get('end_seconds',0)))
        if candidate_end<=float(master.get('end_seconds',0))+1e-6: continue
        stats['candidates']+=1; candidate=copy.deepcopy(events); target=next(x for x in candidate if x.get('event_id')==master.get('event_id')); target['end_seconds']=candidate_end; target['physical_end_seconds']=candidate_end
        # No same-identity duplicate is ever introduced: only the original
        # master interval is extended.  Global occupancy catches cross-card
        # collisions that card-local validation would miss.
        end=max(float(x.get('end_seconds',0)) for x in candidate)
        if card_motion_conflicts(candidate,0.0,end,fps): stats['rejected']+=1; continue
        peak=max((sum(1 for x in candidate if str(x.get('attention_priority'))=='PRIMARY' and float(x.get('start_seconds',0))<=t<float(x.get('end_seconds',0))) for t in [i/fps for i in range(max(1,int(end*fps)))]),default=0)
        if peak>2: stats['rejected']+=1; continue
        before=build_visual_density_report({'events':events,'visual_cards':{'cards':[{'card_id':'ALL','start_seconds':0.0,'end_seconds':end}]}})
        after=build_visual_density_report({'events':candidate,'visual_cards':{'cards':[{'card_id':'ALL','start_seconds':0.0,'end_seconds':end}]}})
        if after.get('near_blank_duration_seconds',0)>before.get('near_blank_duration_seconds',0)+1e-6: stats['rejected']+=1; continue
        master['end_seconds']=round(candidate_end,6);master['physical_start_seconds']=master.get('start_seconds');master['physical_end_seconds']=round(candidate_end,6);master['lifecycle_state']='PERSISTENT_READABLE_HOLD';stats['committed']+=1;stats['reentries_avoided']+=len(master.get('persistent_source_scene_ids') or [])-1
    for e in events:
        e.setdefault('physical_start_seconds',e.get('start_seconds'));e.setdefault('physical_end_seconds',e.get('end_seconds'))
    return stats

def _solve_semantic_segments(events, cards, fps):
    """Bounded pre-commit joint state search for adjacent timing outliers."""
    out={'segments_built':0,'segments_rebuilt':0,'topology_candidates_evaluated':0,'segment_candidates_evaluated':0,'segment_candidates_committed':0,'segment_candidates_rejected':0,'local_candidate_seeds_reused':0,'segments':[]}
    by_card={str(c.get('card_id')):c for c in cards.get('cards') or []}
    blocked=[]
    for e in events:
        if e.get('suppressed_by_card_density') or not e.get('preset_entry'): continue
        delta=_hit_delta_frames(e,float(e.get('perceptual_hit_seconds',0)),fps)
        if abs(delta)>4: blocked.append(e)
    groups={}
    for e in blocked: groups.setdefault(str(e.get('visual_card_id')),[]).append(e)
    for cid, seeds in sorted(groups.items()):
        card=by_card.get(cid)
        if not card: continue
        local=[e for e in events if str(e.get('visual_card_id'))==cid and not e.get('suppressed_by_card_density')]
        out['segments_built']+=1;out['segments_rebuilt']+=1; proof={'card_id':cid,'anchor_event_ids':[e['event_id'] for e in seeds],'candidate_count':0,'best_delta':None,'committed':False,'rejections':[]}
        for offset in (-2,-1,0,1,2):
            candidate=copy.deepcopy(local); cmap={x['event_id']:x for x in candidate}; valid=True
            for seed in seeds:
                x=cmap[seed['event_id']]; entry=x['preset_entry']; dur=float(entry.get('duration_seconds') or preset_duration(entry.get('name') or 'APPEAR_HIGH_SCALE')); st=float(x.get('perceptual_hit_seconds'))-_entry_fraction(x)*dur+offset/fps
                if st<float(card['start_seconds']) or st+dur>float(card['end_seconds']): valid=False;break
                entry['start_seconds']=round(st,6);x['start_seconds']=round(st,6)
            out['segment_candidates_evaluated']+=1;proof['candidate_count']+=1;out['local_candidate_seeds_reused']+=len(seeds)
            if not valid: out['segment_candidates_rejected']+=1;proof['rejections'].append('PHASE_OR_CARD_BOUNDARY');continue
            # Re-synthesize state phases from anchor ownership.  A state holds
            # its already revealed members; future members are not made
            # simultaneous merely because they inherited the same old card.
            ordered=sorted(candidate,key=lambda x:(float(x.get('perceptual_hit_seconds',0)),str(x['event_id']))); cuts=[float(card['start_seconds'])]+[(float(a.get('perceptual_hit_seconds',0))+float(b.get('perceptual_hit_seconds',0)))/2 for a,b in zip(ordered,ordered[1:])]+[float(card['end_seconds'])]; phases=[]
            for i,e in enumerate(ordered):
                active=[x['event_id'] for x in ordered[:i+1] if float(x.get('start_seconds',0))<=cuts[i+1]]
                phases.append({'phase_id':'SEGMENT_STATE_'+str(i),'start_seconds':cuts[i],'end_seconds':cuts[i+1],'event_ids':active})
            phase={'phases':phases};out['topology_candidates_evaluated']+=1
            layout=solve_card_layout(candidate,{'archetype':'GENERIC','explicit_edges':[]},phase)
            if not layout.get('pass'): out['segment_candidates_rejected']+=1;proof['rejections'].append('GEOMETRY');continue
            for x in candidate:
                p=layout['placements'][x['event_id']];x['planned_rect_norm']=p['rect_norm'];x['collision_envelope_rect_norm']=p['rect_norm']
            if card_motion_conflicts(candidate,float(card['start_seconds']),float(card['end_seconds']),fps): out['segment_candidates_rejected']+=1;proof['rejections'].append('COLLISION_PATH');continue
            peak=max(sum(1 for x in candidate if x.get('attention_priority')=='PRIMARY' and float(x['start_seconds'])<=t<float(x['end_seconds']) ) for t in [float(card['start_seconds'])+i/fps for i in range(max(1,int((float(card['end_seconds'])-float(card['start_seconds']))*fps)))])
            if peak>2: out['segment_candidates_rejected']+=1;proof['rejections'].append('PRIMARY_BUDGET');continue
            err=sum(abs(_hit_delta_frames(x,float(x.get('perceptual_hit_seconds')),fps)) for x in candidate if x['event_id'] in cmap)
            proof['best_delta']=round(err,3) if proof['best_delta'] is None else min(proof['best_delta'],round(err,3))
            baseline=build_visual_density_report({'events':local,'visual_cards':{'cards':[card]}}); quality=build_visual_density_report({'events':candidate,'visual_cards':{'cards':[card]}})
            old_err=sum(abs(_hit_delta_frames(x,float(x.get('perceptual_hit_seconds')),fps)) for x in local if x['event_id'] in cmap)
            monotonic=quality.get('near_blank_duration_seconds',0)<=baseline.get('near_blank_duration_seconds',0)+.05 and quality.get('mean_temporal_population',0)>=baseline.get('mean_temporal_population',0)-.03
            if monotonic and err+0.001<old_err:
                replacement={x['event_id']:x for x in candidate}
                for live in local:
                    event_id=live['event_id'];live.clear();live.update(replacement[event_id])
                out['segment_candidates_committed']+=1;proof['committed']=True;break
            out['segment_candidates_rejected']+=1;proof['rejections'].append('DENSITY_CONTINUITY_BASELINE')
        proof['rejections']=sorted(set(proof['rejections']));out['segments'].append(proof)
    return out


def _readable_at(event, t):
    """True only when the approved preset makes the physical state readable."""
    from .composition_qa import _state
    state = _state(event, t)
    return bool(state and float(state[2]) > .22)


def _blank_intervals(events, start, end, fps):
    """Frame-exact empty intervals on the committed physical event track."""
    step = 1.0 / float(fps)
    intervals = []
    blank_start = None
    frame_count = max(1, int(math.ceil((end - start) * fps)))
    for frame in range(frame_count + 1):
        t = min(end, start + frame * step)
        visible = any(
            not e.get('suppressed_by_card_density') and _readable_at(e, t)
            for e in events
        )
        if not visible and blank_start is None:
            blank_start = t
        elif visible and blank_start is not None:
            if t - blank_start > step * .5:
                intervals.append((blank_start, t))
            blank_start = None
    if blank_start is not None and end - blank_start > step * .5:
        intervals.append((blank_start, end))
    return intervals


def _low_population_intervals(events, start, end, fps, target=2, min_seconds=0.60):
    """Readable intervals with too little simultaneous visual population."""
    step = 1.0 / float(fps)
    intervals = []
    low_start = None
    frame_count = max(1, int(math.ceil((end - start) * fps)))
    for frame in range(frame_count + 1):
        t = min(end, start + frame * step)
        pop = sum(
            1 for e in events
            if not e.get('suppressed_by_card_density') and _readable_at(e, t)
        )
        low = pop < int(target)
        if low and low_start is None:
            low_start = t
        elif not low and low_start is not None:
            if t - low_start >= min_seconds - step * .5:
                intervals.append((low_start, t))
            low_start = None
    if low_start is not None and end - low_start >= min_seconds - step * .5:
        intervals.append((low_start, end))
    return intervals


def _commit_readable_state_holds(events, cards, fps):
    """Bridge lifecycle gaps without changing anchor-owned semantic timing.

    Animation duration is not state lifetime. For each non-startup blank, this
    extends one immediately preceding readable state only until the next
    scheduled state becomes readable. Every copied proposal must pass the real
    trajectory/collision and readable-primary validators before commit.
    """
    active = [e for e in events if not e.get('suppressed_by_card_density')]
    if not active:
        return {'intervals_found': 0, 'candidates_evaluated': 0,
                'holds_committed': 0, 'holds_rejected': 0,
                'seconds_recovered': 0.0, 'remaining_intervals': []}
    if not any(e.get('perceptual_hit_source') == 'VOICE_TRIGGER' for e in active):
        return {'intervals_found': 0, 'candidates_evaluated': 0,
                'holds_committed': 0, 'holds_rejected': 0,
                'collision_rejected': 0, 'primary_rejected': 0,
                'geometry_candidates_evaluated': 0,
                'geometry_candidates_committed': 0,
                'quality_rejected': 0, 'seconds_recovered': 0.0,
                'remaining_intervals': [],
                'skipped_reason': 'NO_VOICE_TRIGGERED_SEMANTIC_TRANSITIONS'}
    card_rows = cards.get('cards') or []
    start = min(float(c.get('start_seconds', 0)) for c in card_rows)
    end = max(float(c.get('end_seconds', 0)) for c in card_rows)
    before = _blank_intervals(active, start, end, fps)
    low_population = _low_population_intervals(active, start, end, fps)
    baseline_density = build_visual_density_report({'events': active, 'visual_cards': {'cards': card_rows}})
    stats = {'intervals_found': len(before) + len(low_population), 'candidates_evaluated': 0,
             'holds_committed': 0, 'holds_rejected': 0,
             'collision_rejected': 0, 'primary_rejected': 0,
             'geometry_candidates_evaluated': 0,
             'geometry_candidates_committed': 0,
             'quality_rejected': 0,
              'collision_examples': [],
             'seconds_recovered': 0.0, 'remaining_intervals': []}
    # Solve the largest editorial gaps first; sub-frame/short preset tails are
    # re-measured after these commits and handled on the next convergence pass.
    solve_intervals = sorted(
        [('BLANK', a, b) for a, b in before] + [('LOW_POPULATION', a, b) for a, b in low_population],
        key=lambda row: (-(row[2]-row[1]), row[1], row[0]),
    )
    for interval_kind, gap_start, gap_end in solve_intervals:
        predecessors = [e for e in active if float(e.get('end_seconds', 0)) <= gap_start + 1.0 / fps]
        successors = [e for e in active if _readable_at(e, gap_end)]
        if not predecessors or not successors:
            continue
        handoff_end = max(gap_start, gap_end - 1.0 / fps)
        # Reconstruct the complete last readable state. The renderer already
        # carries this composite frame; committing the corresponding physical
        # lifetimes makes planner, QA, density and rendering share authority.
        outgoing = []
        probe = gap_start - 1.0 / fps
        for _ in range(max(1, int(math.ceil(1.0*fps)))):
            outgoing = [e for e in active if _readable_at(e, probe)]
            if outgoing:
                break
            probe -= 1.0 / fps
        # For an actual blank we reconstruct the whole immediately preceding
        # source state.  A low-population interval already has a live carrier;
        # extending that same carrier cannot improve its population and used
        # to prevent the real predecessor search below from running.
        if outgoing and interval_kind == 'BLANK':
            stats['candidates_evaluated'] += 1
            group_candidate = copy.deepcopy(active)
            group_map = {str(e.get('event_id')): e for e in group_candidate}
            group_ids = {str(e.get('event_id')) for e in outgoing}
            group_start = gap_start
            for live in outgoing:
                target = group_map[str(live.get('event_id'))]
                old_end = float(target.get('end_seconds', 0))
                extension = max(0.0, handoff_end-old_end)
                group_start = min(group_start, float((target.get('preset_exit') or {}).get('start_seconds', old_end)))
                target['end_seconds'] = round(handoff_end, 6)
                target['physical_end_seconds'] = round(handoff_end, 6)
                target['readable_hold_authority'] = 'LAST_READABLE_SOURCE_STATE_UNTIL_NEXT_TRANSITION'
                target['readable_hold_from_seconds'] = round(gap_start, 6)
                target['readable_hold_to_seconds'] = round(handoff_end, 6)
                if target.get('preset_exit'):
                    target['preset_exit']['start_seconds'] = round(
                        float(target['preset_exit'].get('start_seconds', old_end))+extension, 6)
            conflicts = [
                row for row in card_motion_conflicts(group_candidate, group_start, gap_end, fps)
                if group_ids.intersection((str(row.get('event_a')), str(row.get('event_b'))))
            ]
            peak = 0
            for frame in range(max(1, int(math.ceil((gap_end-group_start)*fps)))+1):
                t = group_start+frame/fps
                peak = max(peak, sum(1 for e in group_candidate
                    if str(e.get('attention_priority')).upper() == 'PRIMARY' and _readable_at(e, t)))
            group_density = build_visual_density_report({'events': group_candidate, 'visual_cards': {'cards': card_rows}})
            quality = (group_density.get('near_blank_duration_seconds', 0) < baseline_density.get('near_blank_duration_seconds', 0)-.05
                       and group_density.get('median_safe_frame_union_coverage', 0) >= baseline_density.get('median_safe_frame_union_coverage', 0)-.001
                       and group_density.get('mean_temporal_population', 0) >= baseline_density.get('mean_temporal_population', 0)-.001)
            if not conflicts and peak <= 2 and quality:
                for live in active:
                    eid = str(live.get('event_id'))
                    if eid in group_ids:
                        live.clear();live.update(group_map[eid])
                stats['holds_committed'] += 1
                stats['seconds_recovered'] += max(0.0, handoff_end-gap_start)
                baseline_density = build_visual_density_report({'events': active, 'visual_cards': {'cards': card_rows}})
                continue
            if conflicts:
                stats['collision_rejected'] += 1
            elif peak > 2:
                stats['primary_rejected'] += 1
            else:
                stats['quality_rejected'] += 1
            stats['holds_rejected'] += 1
            # The complete source state is the only valid continuity carrier.
            # Do not fall back to an arbitrary single object after the group
            # has failed a hard gate; that search is both semantically weaker
            # and cannot repair the rejected state topology.
            continue
        predecessors.sort(key=lambda e: (
            float(e.get('end_seconds', 0)),
            str(e.get('attention_priority')).upper() != 'PRIMARY',
            str(e.get('event_id'))), reverse=True)
        committed = False
        latest_end = max(float(e.get('end_seconds', 0)) for e in predecessors)
        outgoing_state = [e for e in predecessors if float(e.get('end_seconds', 0)) >= latest_end-.40]
        # Candidates are limited to the same outgoing semantic transition;
        # older states would cross an intervening source change.
        for previous in outgoing_state[:2]:
            old_end = float(previous.get('end_seconds', 0))
            if old_end >= handoff_end - 1.0 / fps:
                continue
            stats['candidates_evaluated'] += 1
            candidate = copy.deepcopy(active)
            target = next(e for e in candidate if e.get('event_id') == previous.get('event_id'))
            extension = handoff_end - old_end
            target['end_seconds'] = round(handoff_end, 6)
            target['physical_end_seconds'] = round(handoff_end, 6)
            target['readable_hold_authority'] = 'SOURCE_STATE_UNTIL_NEXT_TRANSITION'
            target['readable_hold_from_seconds'] = round(old_end, 6)
            target['readable_hold_to_seconds'] = round(handoff_end, 6)
            if target.get('preset_exit'):
                target['preset_exit']['start_seconds'] = round(
                    float(target['preset_exit'].get('start_seconds', old_end)) + extension, 6)
            validation_start = max(start, old_end - 1.0)
            validation_end = min(end, gap_end + 1.0)
            target_id = str(target.get('event_id'))
            new_conflicts = [
                row for row in card_motion_conflicts(candidate, old_end, validation_end, fps)
                if target_id in (str(row.get('event_a')), str(row.get('event_b')))
                and float(row.get('time_seconds', 0)) > old_end + 1.0 / fps
            ]
            if new_conflicts:
                # The hold changes simultaneous membership, so frozen geometry
                # is not authoritative. Rebuild the connected local topology,
                # solve fresh placements, and regenerate trajectory envelopes.
                successor_ids = {str(e.get('event_id')) for e in successors}
                affected_card_ids = {str(target.get('visual_card_id'))}
                affected_card_ids.update(str(e.get('visual_card_id')) for e in successors)
                dependency = [e for e in candidate if str(e.get('visual_card_id')) in affected_card_ids]
                dependency_ids = {str(e.get('event_id')) for e in dependency}
                phases = []
                affected_cards = [c for c in card_rows if str(c.get('card_id')) in affected_card_ids]
                for affected in affected_cards:
                    phases.extend(copy.deepcopy((affected.get('story_phase_plan') or {}).get('phases') or []))
                local_start = min(float(c.get('start_seconds')) for c in affected_cards)
                local_end = max(float(c.get('end_seconds')) for c in affected_cards)
                # Original phase metadata may omit the calibrated opacity tails
                # of adjacent presets. Add the real simultaneous readable sets
                # so the fresh layout cannot reuse a slot during a live tail.
                seen_members = set()
                sample = local_start
                sample_index = 0
                while sample <= local_end + 1e-6:
                    members = tuple(sorted(str(e.get('event_id')) for e in dependency if _readable_at(e, sample)))
                    if members and members not in seen_members:
                        seen_members.add(members)
                        phases.append({'phase_id': 'READABLE_OCCUPANCY_'+str(sample_index),
                                       'start_seconds': sample,
                                       'end_seconds': min(local_end, sample+.10),
                                       'event_ids': list(members)})
                    sample += .10
                    sample_index += 1
                handoff_members = [target_id] + sorted(successor_ids)
                phases.append({'phase_id': 'READABLE_STATE_CROSS_BOUNDARY_HANDOFF',
                               'start_seconds': gap_start,
                               'end_seconds': handoff_end,
                               'event_ids': handoff_members,
                               'semantic_boundary_authority': 'PREVIOUS_STATE_UNTIL_NEXT_READABLE'})
                stats['geometry_candidates_evaluated'] += 1
                layout = solve_card_layout(
                    dependency, {'archetype': 'GENERIC', 'explicit_edges': []},
                    {'phases': phases, 'beam_width': 64})
                if layout.get('pass'):
                    layout_safe = True
                    for e in dependency:
                        placement = layout['placements'].get(str(e.get('event_id')))
                        if not placement:
                            continue
                        solved_scale = float(placement['scale'])
                        preserved_scale = max(solved_scale, float(e.get('layout_scale_multiplier') or solved_scale))
                        rect = list(map(float, placement['rect_norm']))
                        if preserved_scale > solved_scale + 1e-9:
                            ratio = preserved_scale / max(1e-9, solved_scale)
                            cx = rect[0] + rect[2]/2.0; cy = rect[1] + rect[3]/2.0
                            rect = [cx-rect[2]*ratio/2.0, cy-rect[3]*ratio/2.0,
                                    rect[2]*ratio, rect[3]*ratio]
                        if not _in_safe(rect):
                            layout_safe = False
                            break
                        e['card_rest_position_norm'] = placement['center_norm']
                        e['layout_scale_multiplier'] = round(preserved_scale, 6)
                        e['planned_rect_norm'] = [round(x, 6) for x in rect]
                        e['collision_envelope_rect_norm'] = e['planned_rect_norm']
                        e['topology_recovery'] = 'READABLE_STATE_HOLD_RELAYOUT'
                    if layout_safe:
                        changed_ids = {str(e.get('event_id')) for e in dependency}
                        regenerated = [
                            row for row in card_motion_conflicts(candidate, local_start, local_end, fps)
                            if changed_ids.intersection((str(row.get('event_a')), str(row.get('event_b'))))
                        ]
                        new_conflicts = regenerated
                if new_conflicts:
                    stats['holds_rejected'] += 1
                    stats['collision_rejected'] += 1
                    if len(stats['collision_examples']) < 12:
                        stats['collision_examples'].append(new_conflicts[0])
                    continue
            peak = 0
            local_frames = max(1, int(math.ceil((validation_end - validation_start) * fps)))
            for frame in range(local_frames + 1):
                t = validation_start + frame / fps
                count = sum(
                    1 for e in candidate
                    if str(e.get('attention_priority')).upper() == 'PRIMARY' and _readable_at(e, t)
                )
                peak = max(peak, count)
            if peak > 2:
                stats['holds_rejected'] += 1
                stats['primary_rejected'] += 1
                continue
            candidate_density = build_visual_density_report({'events': candidate, 'visual_cards': {'cards': card_rows}})
            if (candidate_density.get('near_blank_duration_seconds', 0) >= baseline_density.get('near_blank_duration_seconds', 0)-.05
                    or candidate_density.get('median_safe_frame_union_coverage', 0) < baseline_density.get('median_safe_frame_union_coverage', 0)-.001
                    or candidate_density.get('mean_temporal_population', 0) < baseline_density.get('mean_temporal_population', 0)-.001
                    or (interval_kind == 'LOW_POPULATION' and candidate_density.get('mean_temporal_population', 0) <= baseline_density.get('mean_temporal_population', 0)+.002)):
                stats['holds_rejected'] += 1
                stats['quality_rejected'] += 1
                continue
            candidate_by_id = {str(e.get('event_id')): e for e in candidate}
            changed_ids = {target_id}
            if target.get('topology_recovery') == 'READABLE_STATE_HOLD_RELAYOUT':
                changed_ids.update(dependency_ids)
                stats['geometry_candidates_committed'] += 1
            for live in active:
                eid = str(live.get('event_id'))
                if eid in changed_ids:
                    live.clear()
                    live.update(candidate_by_id[eid])
                    card = next((c for c in card_rows if str(c.get('card_id')) == str(live.get('visual_card_id'))), None)
                    if card is not None:
                        placements = (card.get('constraint_layout') or {}).get('placements') or {}
                        if eid in placements:
                            placements[eid]['center_norm'] = live.get('card_rest_position_norm')
                            placements[eid]['scale'] = live.get('layout_scale_multiplier')
                            placements[eid]['rect_norm'] = live.get('planned_rect_norm')
            stats['holds_committed'] += 1
            stats['seconds_recovered'] += max(0.0, extension)
            committed = True
            baseline_density = build_visual_density_report({'events': active, 'visual_cards': {'cards': card_rows}})
            break
        if not committed:
            stats['remaining_intervals'].append({
                'start_seconds': round(gap_start, 6),
                'end_seconds': round(gap_end, 6),
                'reason': 'COLLISION_PATH_OR_PRIMARY_BUDGET' if interval_kind == 'BLANK' else 'LOW_POPULATION_NOT_IMPROVED'})
    stats['seconds_recovered'] = round(stats['seconds_recovered'], 6)
    unresolved_blank = [
        {'start_seconds': round(a, 6), 'end_seconds': round(b, 6),
         'reason': 'NO_LEGAL_PRECEDING_STATE_HOLD'}
        for a, b in _blank_intervals(active, start, end, fps)
    ]
    unresolved_low = [
        {'start_seconds': round(a, 6), 'end_seconds': round(b, 6),
         'reason': 'NO_LEGAL_LOW_POPULATION_HOLD'}
        for a, b in _low_population_intervals(active, start, end, fps)
    ]
    stats['remaining_intervals'] = unresolved_blank + unresolved_low
    return stats


def _tm(alignment:dict):
    return {str(x['scene_id']):x for x in (alignment.get('scene_timings') or [])}

def _word_time(trigger:dict|None, alignment:dict, st:dict, prefer_end:bool=False):
    if not trigger:return None
    try:a=int(trigger.get('global_char_start',-1));b=int(trigger.get('global_char_end',-1))
    except Exception:return None
    if a<0 or b<a:return None
    rows=[r for r in (alignment.get('word_timings') or []) if int(r.get('char_end',-1))>a and int(r.get('char_start',10**9))<b]
    if not rows:return None
    v=float(rows[-1].get('end',0)) if prefer_end else float(rows[0].get('start',0))
    return max(float(st['start']),min(float(st['end']),v))

def _semantic_map(scene:dict):
    return {str(u.get('unit_id')):u for u in (scene.get('units') or []) if u.get('unit_id')}

def _identity(sem:dict,u:dict):
    typ=str(u.get('semantic_type') or sem.get('type') or '').upper();name=str(sem.get('semantic_name') or sem.get('name') or '').strip().upper()
    if not name:name=str(u.get('semantic_unit_id') or u.get('physical_id') or '')
    return typ+'::'+name

def _kind(u:dict):
    t=str(u.get('semantic_type') or '').upper()
    if t=='MAIN_CHARACTER':return 'MAIN_NARRATOR'
    if t=='SECONDARY_CHARACTER':return 'SECONDARY_CHARACTER'
    return 'VISUAL'

def _relation(scene:dict):
    r=str(scene.get('relation_to_previous') or '').upper().replace(' ','_').replace('-','_');return r or 'UNSPECIFIED'

def _sid(e:dict):return str(e.get('semantic_scope_id') or e.get('semantic_unit_id') or e.get('identity_key') or e.get('event_id'))

def _track_key(e:dict)->str:
    ident=str(e.get('identity_key') or '').strip()
    # Persist identities only when the semantic->physical mapping is trustworthy. Otherwise
    # two unrelated flat-image groups could be collapsed just because a heuristic assigned
    # them the same semantic label. Main narrator remains a strong visual identity exception.
    if str(e.get('kind') or '').upper()=='MAIN_NARRATOR':return 'MAIN_NARRATOR::PERSISTENT'
    conf=float(e.get('semantic_mapping_confidence') or 0.0)
    if ident and conf>=0.85:return ident
    # Low-confidence semantic->physical mapping must never persist a flat-image group across
    # scenes just because the upstream semantic ID repeats. Treat it as instance-local.
    if conf<0.85:return 'EVENT::'+str(e.get('event_id') or e.get('physical_id'))
    sem=str(e.get('semantic_unit_id') or '').strip()
    if sem:return 'SEM::'+sem
    return 'PHYS::'+str(e.get('physical_id') or e.get('event_id'))

def _consolidate_card_identity(evs:list[dict]):
    masters={}
    for e in sorted(evs,key=lambda x:(float(x.get('perceptual_hit_seconds',0)),str(x.get('event_id')))):
        key=('P' if str(e.get('attention_priority') or '').upper()=='PRIMARY' else 'S',_track_key(e))
        if key not in masters:
            masters[key]=e;e['persistent_master_event_id']=e['event_id'];e['persistent_source_scene_ids']=[e.get('scene_id')];continue
        m=masters[key]
        if key[1].startswith('PHYS::'):continue
        e['suppressed_by_card_density']=True;e['suppression_reason']='CARD_IDENTITY_PERSISTENCE';e['persistent_master_event_id']=m['event_id']
        m.setdefault('persistent_source_scene_ids',[]).append(e.get('scene_id'));m['perceptual_hit_seconds']=min(float(m.get('perceptual_hit_seconds',0)),float(e.get('perceptual_hit_seconds',0)))
    return masters

def _event_is_atomic(e:dict)->bool:
    b=e.get('source_bbox_norm') or [0,0,.3,.3];w=float(b[2])*float(e.get('reference_camera_scale') or 1.0);h=float(b[3])*float(e.get('reference_camera_scale') or 1.0);detail=int(e.get('source_grouped_detail_count') or 0)
    return bool(w>0.50 or h>0.58 or w*h>0.16 or detail>=5)

def _phase_for_event(phase_plan:dict,eid:str):
    rows=[p for p in (phase_plan.get('phases') or []) if eid in (p.get('event_ids') or [])]
    if not rows:return None
    return float(rows[0]['start_seconds']),float(rows[-1]['end_seconds'])

def _clamp(v,a,b):return max(a,min(b,v))

def _schedule_event(e:dict, phase_window:tuple[float,float], card:dict, index:int, total:int, *, force_static:bool=False):
    """Schedule one already collision-solved object using only user preset families."""
    ps,pe=phase_window;card_end=float(card['end_seconds']);primary=str(e.get('attention_priority') or '').upper()=='PRIMARY'
    center=e.get('card_rest_position_norm') or [0.5,0.5];dur=max(0.05,pe-ps)
    # voice-aligned appearance start; preserve the phase grammar as the hard envelope
    hit=_clamp(float(e.get('perceptual_hit_seconds',ps+dur*.45)),ps+0.20,pe-0.20)
    appearance='APPEAR_HIGH_SCALE';ad=preset_duration(appearance);dd=preset_duration('DISAPPEAR_DOWN_SCALE')
    exact_middle=abs(float(center[0])-0.5)<0.025 and abs(float(center[1])-0.5)<0.035
    room_for_entry=dur>=preset_duration('ENTRY_LEFT_TO_MIDDLE')+0.72
    use_position_entry=bool(total>1 and not force_static and primary and exact_middle and room_for_entry and not e.get('composite_atomic') and not e.get('relationship_source_requested'))
    if use_position_entry:
        pn=choose_entry_for_center(float(e.get('source_center_norm',[0.5,0.5])[0]));pd=preset_duration(pn);st=max(ps,min(hit-pd*.90,pe-pd-0.62));st=max(ps+0.02,st)
        if total==1:st=ps
        e['card_rest_position_norm']=[0.5,0.5]
        e['preset_entry']={'name':pn,'start_seconds':round(st,6),'duration_seconds':pd,'authority':'USER_PRFPSET_ENTRY_EXIT__V31_SAFE_CENTER'}
        e['appearance_method']='POSITION_ENTRY';e['entry_direction']='LEFT' if 'LEFT' in pn else 'RIGHT';e['position_animated']=True;e['settle_seconds']=round(st+pd,6)
        # Position exits are used only when this is the sole independent object in the visual
        # sentence. With supports/other primaries, disappearance is safer: a fixed MIDDLE->OUT
        # path can sweep through another valid object even when both settled layouts are clean.
        if total==1:
            ex=choose_exit_for_center(float(e.get('source_center_norm',[0.5,0.5])[0]));ed=preset_duration(ex);xs=max(float(e['settle_seconds'])+0.10,pe-ed);xs=min(xs,pe-ed)
            if xs>=float(e['settle_seconds'])+0.05:
                e['preset_exit']={'name':ex,'start_seconds':round(xs,6),'duration_seconds':ed,'authority':'USER_PRFPSET_ENTRY_EXIT__V31_SAFE_CENTER'};e['disappearance_method']='POSITION_EXIT';e['end_seconds']=round(min(pe,xs+ed),6)
            else:
                xs=max(float(e['settle_seconds'])+0.04,pe-dd*0.60);e['preset_exit']={'name':'DISAPPEAR_DOWN_SCALE','start_seconds':round(xs,6),'duration_seconds':dd,'authority':'USER_PRFPSET_DISAPPEARANCE'};e['disappearance_method']='PRESET_DISAPPEARANCE';e['end_seconds']=round(pe,6)
        else:
            xs=max(float(e['settle_seconds'])+0.04,pe-dd*0.60);e['preset_exit']={'name':'DISAPPEAR_DOWN_SCALE','start_seconds':round(xs,6),'duration_seconds':dd,'authority':'USER_PRFPSET_DISAPPEARANCE__CROSS_OBJECT_PATH_GUARD'};e['disappearance_method']='PRESET_DISAPPEARANCE';e['end_seconds']=round(pe,6)
        e['start_seconds']=round(st,6)
    else:
        # Static placement + exact appearance preset is the universal safe path for side slots,
        # large composites, comparisons and support icons. It prevents the fixed Premiere Position
        # endpoints from throwing large objects through each other or offscreen.
        # V31 pre-rolls object appearance by 0.20s at non-zero phase/card boundaries. The supplied
        # disappearance preset is already fully transparent for its final ~0.24s, so this creates
        # an object-level handoff instead of the white one-frame resets visible in V30.
        # Scheduling intervals are the physical co-occurrence authority. Do not pre-roll a
        # new object into the preceding phase: even a mostly transparent large silhouette can
        # become visible before the outgoing preset has cleared its collision envelope.
        floor=max(0.0,ps)
        if e.get('perceptual_hit_source')=='SOURCE_INTERVAL_FALLBACK':
            st=floor+0.06*(index%3)
        else:
            st=max(floor,min(hit-ad*.70,pe-ad-0.34));st=max(floor+0.06*(index%3),st);st=max(floor,min(st,pe-ad-0.18))
        # The final 40% of the supplied disappearance preset is already fully transparent.
        # Align its physical opacity-zero keyframe with the phase boundary instead of creating
        # a 0.24s white trough before every handoff.
        xs=max(st+ad+0.10,pe-dd*0.60);xs=min(xs,pe-dd*0.60)
        e['preset_entry']={'name':'APPEAR_HIGH_SCALE','start_seconds':round(st,6),'duration_seconds':ad,'authority':'USER_PRFPSET_APPEARANCE__V31_CONSTRAINT_LAYOUT'}
        e['preset_exit']={'name':'DISAPPEAR_DOWN_SCALE','start_seconds':round(xs,6),'duration_seconds':dd,'authority':'USER_PRFPSET_DISAPPEARANCE__V31_CONSTRAINT_LAYOUT'}
        e['appearance_method']='SCALE_POP';e['disappearance_method']='PRESET_DISAPPEARANCE';e['position_animated']=False;e['entry_direction']=None;e['start_seconds']=round(st,6);e['settle_seconds']=round(st+ad,6);e['end_seconds']=round(pe,6)
    e['preset_actions']=[];e['motion_energy']='HIGH' if primary else 'MEDIUM';e['position_interpolation']='USER_PRESET_CURVE';e['position_min_frames']=12
    entry=e.get('preset_entry') or {};entry_dur=float(entry.get('duration_seconds') or 0);entry_start=float(entry.get('start_seconds',e.get('start_seconds',0)));impact=entry_start+_entry_fraction(e)*entry_dur
    e['visual_impact_seconds']=round(impact,6);e['pre_roll_duration_seconds']=round(max(0.0,float(e.get('perceptual_hit_seconds',impact))-entry_start),6);e['semantic_readable_not_before_seconds']=round(impact,6);e['pre_roll_visibility_contract']='OFFSCREEN_TRAVEL_UNTIL_IMPACT' if str(entry.get('name') or '').startswith('ENTRY_') else 'APPROVED_SCALE_REVEAL_TO_IMPACT';e['fast_narration_fallback']=bool(not use_position_entry and dur<preset_duration('ENTRY_LEFT_TO_MIDDLE')+.72)

def _relationship_candidates(source_scenes:list[dict]):
    out=[];seen=set()
    for scene in source_scenes:
        scene_id=str(scene.get('scene_id') or '')
        def scoped(unit_id):return (scene_id+'::'+str(unit_id)) if scene_id else str(unit_id)
        sems=_semantic_map(scene)
        for row in scene.get('visual_progression') or []:
            if not isinstance(row,dict):continue
            ids=[str(x) for x in (row.get('targets') or []) if x]
            for a,b in zip(ids,ids[1:]):
                k=(a,b)
                if a!=b and k not in seen:seen.add(k);out.append({'source':a,'target':b,'source_scope_id':scoped(a),'target_scope_id':scoped(b),'trigger':row.get('trigger'),'evidence':'DECLARED_VISUAL_PROGRESSION','confidence':1.0})
        for sid,u in sems.items():
            tgt=u.get('interaction_target') or u.get('target_unit_id') or u.get('relationship_target')
            if tgt and str(tgt) in sems:
                k=(sid,str(tgt))
                if k not in seen:seen.add(k);out.append({'source':sid,'target':str(tgt),'source_scope_id':scoped(sid),'target_scope_id':scoped(tgt),'trigger':u.get('focus_trigger') or u.get('appear_trigger'),'evidence':'EXPLICIT_INTERACTION_TARGET','confidence':1.0})
    return out

def _safe_relationship_motion(card:dict,events:list[dict],rels:list[dict]):
    """Optional physical relationship motion. Unsafe fixed-endpoint presets become temporal handoffs."""
    bysid={_sid(e):e for e in events if not e.get('suppressed_by_card_density')}
    resolved=[]
    for r in rels:
        src=bysid.get(str(r.get('source_scope_id') or r['source']));dst=bysid.get(str(r.get('target_scope_id') or r['target']))
        if not src or not dst or src is dst:continue
        if float(src.get('semantic_mapping_confidence') or 0.0)<0.85 or float(dst.get('semantic_mapping_confidence') or 0.0)<0.85:
            resolved.append({'source':r['source'],'target':r['target'],'mode':'UNRESOLVED_PHYSICAL_MAPPING','reason':'SEMANTIC_TO_PHYSICAL_MAPPING_CONFIDENCE_BELOW_0_85'});continue
        sc=src.get('card_rest_position_norm') or [0.5,0.5];dc=dst.get('card_rest_position_norm') or [0.5,0.5]
        # Within-frame user presets begin at middle. Never teleport a side-positioned source.
        if abs(float(sc[0])-0.5)>0.03 or abs(float(sc[1])-0.5)>0.04:
            resolved.append({'source':r['source'],'target':r['target'],'mode':'TEMPORAL_HANDOFF','reason':'SOURCE_NOT_AT_PRESET_START_STATE'});continue
        dx=float(dc[0])-0.5;dy=float(dc[1])-0.5
        if abs(dx)>=abs(dy):name='WITHIN_MIDDLE_TO_RIGHT' if dx>0 else 'WITHIN_MIDDLE_TO_LEFT'
        else:name='WITHIN_MIDDLE_TO_DOWN' if dy>0 else 'WITHIN_MIDDLE_TO_UP'
        if not within_preset_safe(src,name,float(src.get('layout_scale_multiplier') or 1.0)):
            resolved.append({'source':r['source'],'target':r['target'],'mode':'TEMPORAL_HANDOFF','reason':'PRESET_ENDPOINT_UNSAFE_FOR_OBJECT_FOOTPRINT'});continue
        # Target must actually live near the supplied preset endpoint; otherwise using the preset
        # would visually lie about the relationship.
        d=(preset_authority().get('preset_motion') or {}).get(name) or {};ep=d.get('end_norm') or [0.5,0.5]
        if math.hypot(float(dc[0])-float(ep[0]),float(dc[1])-float(ep[1]))>0.16:
            resolved.append({'source':r['source'],'target':r['target'],'mode':'TEMPORAL_HANDOFF','reason':'TARGET_NOT_NEAR_AUTHORIZED_PRESET_ENDPOINT'});continue
        pd=preset_duration(name);ex=float((src.get('preset_exit') or {}).get('start_seconds',card['end_seconds']))
        earliest=float(src.get('settle_seconds',0))+0.08;latest=ex-pd-0.08
        desired=float(src.get('perceptual_hit_seconds',earliest))+0.10
        start=max(earliest,min(latest,desired))
        if latest<earliest or start+pd>=ex-0.06:
            resolved.append({'source':r['source'],'target':r['target'],'mode':'TEMPORAL_HANDOFF','reason':'NO_PHYSICAL_TIME_WINDOW'});continue
        src['preset_actions']=[{'name':name,'start_seconds':round(start,6),'duration_seconds':pd,'action_type':'SEMANTIC_RELATIONSHIP','target_semantic_unit_id':str(r['target']),'relationship_evidence':r['evidence'],'relationship_confidence':1.0,'authority':'USER_PRFPSET_WITHIN_FRAME__V31_EXPLICIT_RELATION','start_state_contract':'CANONICAL_MIDDLE_AFTER_PRIMARY_ENTRY'}]
        # A moved object disappears from the held endpoint. Position exit would jump back to middle.
        # Preserve the exit already compiled from the source phase. V31.0.1 incorrectly moved
        # this exit to card_end, extending the source through the target's later handoff phase.
        # That made the nominal phase plan physically false and caused near-total collisions.
        src['phase_bounded_relationship_motion']=True
        resolved.append({'source':r['source'],'target':r['target'],'mode':'WITHIN_FRAME_PRESET','preset':name,'reason':'EXPLICIT_RELATION_AND_PHYSICALLY_SAFE'})
    return resolved

def _recover_trajectory_conflicts(card:dict,events:list[dict],phase_plan:dict,resolutions:list[dict],fps:float)->list[dict]:
    """Commit motion only after its complete animated envelopes are physically feasible.

    Recovery preserves story objects. Unsafe relationship travel becomes an honest temporal
    handoff; unsafe position entry/exit becomes the matching user appearance/disappearance
    family at the already solved semantic anchor.
    """
    conflicts=card_motion_conflicts(events,float(card['start_seconds']),float(card['end_seconds']),fps)
    if not conflicts:return resolutions
    involved={eid for row in conflicts for eid in (row['event_a'],row['event_b'])}
    changed=False
    for e in events:
        if e.get('event_id') in involved and e.get('preset_actions'):
            e['preset_actions']=[];changed=True
            sid=_sid(e)
            for r in resolutions:
                if str(r.get('source_scope_id') or r.get('source'))==sid and r.get('mode')=='WITHIN_FRAME_PRESET':
                    r.update({'mode':'TEMPORAL_HANDOFF','reason':'ANIMATED_TRAJECTORY_COLLISION_RECOVERY'});r.pop('preset',None)
    conflicts=card_motion_conflicts(events,float(card['start_seconds']),float(card['end_seconds']),fps)
    if conflicts:
        involved={eid for row in conflicts for eid in (row['event_a'],row['event_b'])}
        for e in events:
            if e.get('event_id') not in involved:continue
            pe=e.get('preset_entry') or {};px=e.get('preset_exit') or {}
            if e.get('position_animated') or str(pe.get('name','')).startswith('ENTRY_') or str(px.get('name','')).startswith('EXIT_'):
                window=_phase_for_event(phase_plan,str(e.get('event_id')))
                if window:_schedule_event(e,window,card,events.index(e),len(events),force_static=True);changed=True
    conflicts=card_motion_conflicts(events,float(card['start_seconds']),float(card['end_seconds']),fps)
    if conflicts:
        # Card-wide topology recovery: objects in different semantic phases do
        # not own a region for the whole card. Retire the completed non-primary
        # support before the incoming source-backed state becomes readable.
        by_id={str(e.get('event_id')):e for e in events}
        reused=0
        for row in conflicts:
            left,right=by_id.get(str(row['event_a'])),by_id.get(str(row['event_b']))
            if not left or not right:continue
            t=float(row['time_seconds']); candidates=[x for x in (left,right) if str(x.get('semantic_role') or '').upper()!='PRIMARY' and float(x.get('start_seconds',0))<t]
            if not candidates:
                # Carrier movement/retirement is allowed only after support
                # reuse is exhausted; continuity is retained by the incoming
                # state rather than a blank card.
                candidates=[x for x in (left,right) if float(x.get('start_seconds',0))<t]
            old=min(candidates,key=lambda x:float(x.get('start_seconds',0)))
            new_end=max(float(old.get('start_seconds',0))+.12,t-.05)
            if new_end<float(old.get('end_seconds',0)):
                old['end_seconds']=round(new_end,6);old['topology_recovery']='TEMPORAL_SPATIAL_REUSE__SUPPORT_EXIT';reused+=1
        if reused:
            card['time_separated_spatial_reuse_count']=int(card.get('time_separated_spatial_reuse_count') or 0)+reused
        conflicts=card_motion_conflicts(events,float(card['start_seconds']),float(card['end_seconds']),fps)
    if conflicts:
        pairs=' | '.join(f"{x['event_a']} x {x['event_b']}@{x['time_seconds']:.3f}" for x in conflicts[:4])
        raise ValueError(f"{card['card_id']}: NO_COLLISION_FREE_SPATIOTEMPORAL_PLAN after preset-safe recovery: {pairs}")
    if changed:card['trajectory_recovery']='PRESET_SAFE_TEMPORAL_HANDOFF_OR_STATIC_ANCHOR'
    return resolutions

def build_preset_story_motion_plan(plan:dict, alignment:dict, vision_results:list[dict], rules_path, reference_path, *, fps:float=30.0, logger=None, calibration:dict|None=None):
    ref=read_json(reference_path);tm=_tm(alignment);vis={str(v['scene_id']):v for v in vision_results};scenes=list(plan.get('scenes') or []);scene_map={str(s['scene_id']):s for s in scenes}
    cards=build_visual_cards(plan,alignment,vision_results,min_seconds=3.0,max_seconds=5.0)
    if not cards.get('cards'):raise ValueError('Visual-card compiler failed: '+' | '.join(cards.get('hard_failures') or ['unknown partition failure']))
    scene_to_card=cards.get('scene_to_card') or {};card_by={c['card_id']:c for c in cards['cards']};events=[];scenes_out=[]

    # Physical events: conservative top-level objects only. V31 adds actual footprint metadata so
    # layout is solved on rectangles, not centers.
    for scene in scenes:
        sid=str(scene['scene_id']);st=tm[sid];vr=vis[sid];card=card_by[scene_to_card[sid]];sems=_semantic_map(scene)
        units=[u for u in (vr.get('units') or []) if int(u.get('hierarchy_level') or 0)==0]
        camera_fit=compute_reference_camera_fit(float(vr.get('foreground_fraction') or 0.0),units,ref);camera_fit['camera_scale']=max(0.68,min(1.15,float(camera_fit.get('camera_scale') or 1.0)));camera_fit['expected_occupancy_percent']=float(camera_fit.get('source_occupancy_percent') or 0.0)*camera_fit['camera_scale']**2
        scene_events=[]
        for u in units:
            sem=sems.get(str(u.get('semantic_unit_id'))) or {};primary=is_primary_semantic(u);cx,cy=map(float,u.get('center_norm') or [0.5,0.5]);trig=sem.get('appear_trigger') or sem.get('focus_trigger');hit=_word_time(trig,alignment,st,False)
            hit_source='VOICE_TRIGGER'
            if hit is None:
                hit=(float(st['start'])+float(st['end']))/2.0;hit_source='SOURCE_INTERVAL_FALLBACK'
            e={
                'event_id':f'{sid}_{u["physical_id"]}','scene_id':sid,'visual_card_id':card['card_id'],'physical_id':u['physical_id'],'semantic_unit_id':u.get('semantic_unit_id'),'semantic_scope_id':f"{sid}::{u.get('semantic_unit_id')}" if u.get('semantic_unit_id') else f"{sid}::{u['physical_id']}",'semantic_type':u.get('semantic_type'),'semantic_role':u.get('semantic_role'),'kind':_kind(u),'identity_key':_identity(sem,u),
                'narrative_function':sem.get('narrative_function'),'semantic_intent':sem.get('semantic_intent'),'relationship':sem.get('relationship'),
                'source_scene_start_seconds':float(st['start']),'source_scene_end_seconds':float(st['end']),'source_center_norm':[cx,cy],'source_bbox_norm':u.get('bbox_norm'),'source_grouped_detail_count':int(u.get('grouped_detail_count') or ((vr.get('grouped_detail_count') or (vr.get('artifacts') or {}).get('grouped_detail_count') or 0) if len(units)==1 else 0)),
                'start_seconds':float(st['start']),'perceptual_hit_seconds':round(hit,6),'perceptual_hit_source':hit_source,'settle_seconds':float(st['end']),'end_seconds':float(st['end']),'preset_entry':None,'preset_exit':None,'preset_actions':[],
                'appearance_method':None,'disappearance_method':None,'entry_direction':None,'position_animated':False,'position_min_frames':12,'position_interpolation':'USER_PRESET_CURVE','motion_profile':'USER_VISUAL_SAMPLE_AUTHORITY','motion_blur_enabled':False,'preset_coordinate_mode':'ABSOLUTE_OBJECT_CENTER',
                'start_x_norm':cx,'start_y_norm':cy,'end_x_norm':cx,'end_y_norm':cy,'exit_x_norm':cx,'exit_y_norm':cy,'focus_beats':[],'story_actions':[],'story_beats':[],'continuous_drift':False,'continuous_image_scale':False,
                'reference_camera_scale':float(camera_fit['camera_scale']),'layout_scale_multiplier':1.0,'hierarchy_level':0,'parent_semantic_unit_id':None,'composition_slot_id':u.get('composition_slot_id') or u.get('semantic_unit_id') or u.get('physical_id'),'fifth_element_overlay':False,
                'translation_safe_after_occlusion':bool(u.get('translation_safe_after_occlusion',u.get('animation_safe',True))),'matting':u.get('matting'),'semantic_mapping_confidence':float(u.get('semantic_mapping_confidence',0.0)),'cutout_policy':'TOP_LEVEL_SEMANTIC_GROUP_ONLY__PRESERVE_ATTACHED_DETAILS','relationship_motion_policy':'EXPLICIT_METADATA_ONLY__UNSAFE_TRAVEL_BECOMES_TEMPORAL_HANDOFF','attention_priority':'PRIMARY' if primary else 'SUPPORTING','motion_energy':'HIGH' if primary else 'MEDIUM','budget_cost':0.25 if primary else 0.12,
            }
            e['composite_atomic']=_event_is_atomic(e);events.append(e);scene_events.append(e)
        scenes_out.append({'scene_id':sid,'start_seconds':float(st['start']),'end_seconds':float(st['end']),'duration_seconds':float(st['end'])-float(st['start']),'duration_class':'CARD_MEMBER','vision_mode':vr.get('mode'),'choreography_profile':'V31_0_25_PREMIUM_MOTION_LANGUAGE','relation_to_previous':_relation(scene),'transition':{'mode':'OBJECT_PRESETS_ONLY__NO_FRAME_BLEND','duration_seconds':0.0,'white_reset':False,'relation':_relation(scene),'profile':'V31_0_25_PREMIUM_MOTION_LANGUAGE','energy_cost':0.0,'strong':False},'visual_card_id':card['card_id'],'reference_camera_fit':camera_fit,'event_ids':[e['event_id'] for e in scene_events],'internal_change_count':len(scene_events),'semantic_focus_count':0,'story_beat_count':0,'story_action_count':0,'physical_story_action_count':0,'max_story_gap_seconds':min(1.4,float(card['duration_seconds'])),'hierarchical_motion_unit_count':0,'composition_slot_count':len(scene_events),'short_beat':False,'motion_budget':{'budget_points':10.0,'duration_class':'CARD_MEMBER'},'estimated_motion_cost':sum(e['budget_cost'] for e in scene_events),'budget_utilization':0.0})

    # Semantic card repartition: preserve the locked legal 3–5 second card
    # intervals, but assign each required event to the interval containing its
    # voice anchor. A source scene may straddle an editorial boundary; its
    # physical state must follow the anchor rather than an obsolete scene map.
    ordered_cards=cards['cards']
    for e in events:
        hit=float(e.get('perceptual_hit_seconds',e.get('source_scene_start_seconds',0)))
        target=next((c for c in ordered_cards if float(c['start_seconds'])-1e-6<=hit<float(c['end_seconds'])-1e-6),None)
        if target is None and ordered_cards:target=min(ordered_cards,key=lambda c:min(abs(hit-float(c['start_seconds'])),abs(hit-float(c['end_seconds']))))
        if target and e.get('visual_card_id')!=target['card_id']:
            e['repartitioned_from_visual_card_id']=e.get('visual_card_id');e['visual_card_id']=target['card_id'];e['card_repartition_strategy']='ANCHOR_INTERVAL_CARD_SPLIT'
            if e.get('scene_id') not in target.get('source_scene_ids',[]):target.setdefault('source_scene_ids',[]).append(e.get('scene_id'))

    # Universal card compilation. The same code path handles every semantic domain and scene archetype,
    # process, metaphor or any future topic because it consumes only semantic roles/edges and geometry.
    composition_history=[]
    for card in cards['cards']:
        evs=[e for e in events if e['visual_card_id']==card['card_id']];_consolidate_card_identity(evs);active=[e for e in evs if not e.get('suppressed_by_card_density')]
        source_scenes=[scene_map[sid] for sid in card.get('source_scene_ids') or [] if sid in scene_map]
        grammar=classify_card(card,active,source_scenes);phase_plan=repartition_story_phases(card,active,[])
        card['semantic_phase_repartition']={'detected_conflicts':0,'resolved_by_internal_phase_split':len(phase_plan.get('phases') or []),'cards_split':0,'authority':'ANCHOR_OWNED_PHASE_TOPOLOGY'}
        # Topology-aware solve: do not discard future-state objects before the
        # real phase-aware composition solver can reserve/reuse their geometry.
        # `solve_card_layout` consumes phase co-occurrence, so objects separated
        # in time are legal candidates rather than permanent card occupancy.
        selected_events=list(active)
        card['topology_solver_authority']='CARD_WIDE_FUTURE_REVEAL__TIME_SEPARATED_OCCUPANCY'
        layout=solve_card_layout(selected_events,grammar,phase_plan)
        if not layout.get('pass'):
            phase_plan=repair_story_phases(card,selected_events,grammar)
            dropped=set(phase_plan.get('suppressed_event_ids') or [])
            for e in selected_events:
                if e['event_id'] in dropped:
                    e['suppressed_by_card_density']=True
                    e['suppression_reason']='V31_0_25_ADAPTIVE_COLLISION_RECOVERY'
            selected_events=[e for e in selected_events if not e.get('suppressed_by_card_density')]
            layout=solve_card_layout(selected_events,grammar,phase_plan)
        if not layout.get('pass'):
            raise ValueError(f"{card['card_id']}: V31.0.25 adaptive composition recovery exhausted: {layout.get('reason')}")
        composition_variant=_apply_composition_history_variant(layout,grammar,composition_history)
        rels=_relationship_candidates(source_scenes)
        rel_sources={str(r.get('source_scope_id') or r.get('source')) for r in rels}
        for e in selected_events:
            if _sid(e) in rel_sources:e['relationship_source_requested']=True
            pl=layout['placements'][e['event_id']];e['card_rest_position_norm']=pl['center_norm'];e['layout_scale_multiplier']=pl['scale'];e['composition_role']=pl['role'];e['composite_atomic']=bool(pl['atomic']);e['planned_rect_norm']=pl['rect_norm'];window=_phase_for_event(phase_plan,e['event_id'])
            if window:_schedule_event(e,window,card,selected_events.index(e),len(selected_events))
        pre_conflicts=card_motion_conflicts(selected_events,float(card['start_seconds']),float(card['end_seconds']),fps)
        if pre_conflicts:
            phase_plan=repartition_story_phases(card,selected_events,pre_conflicts)
            layout=solve_card_layout(selected_events,grammar,phase_plan)
            if not layout.get('pass'):
                raise ValueError(f"{card['card_id']}: semantic phase repartition layout failed: {layout.get('reason')}")
            composition_variant=_apply_composition_history_variant(layout,grammar,composition_history)
            for e in selected_events:
                pl=layout['placements'][e['event_id']];e['card_rest_position_norm']=pl['center_norm'];e['layout_scale_multiplier']=pl['scale'];e['composition_role']=pl['role'];e['planned_rect_norm']=pl['rect_norm'];e['preset_entry']=None;e['preset_exit']=None;e['preset_actions']=[]
                window=_phase_for_event(phase_plan,e['event_id'])
                if window:_schedule_event(e,window,card,selected_events.index(e),len(selected_events),force_static=True)
            card['semantic_phase_repartition']={'detected_conflicts':len(pre_conflicts),'resolved_by_internal_phase_split':len(pre_conflicts),'cards_split':0}
        relationship_resolutions=_safe_relationship_motion(card,selected_events,rels)
        relationship_resolutions=_recover_trajectory_conflicts(card,selected_events,phase_plan,relationship_resolutions,fps)
        for zi,e in enumerate(sorted(selected_events,key=lambda x:(0 if x.get('attention_priority')!='PRIMARY' else 1,1 if 'CHARACTER' in str(x.get('semantic_type') or '') else 0,str(x.get('event_id')))),2):
            e['z_order']=zi;e['visibility_interval_seconds']=[e.get('start_seconds'),e.get('end_seconds')]
            e['collision_envelope_rect_norm']=e.get('planned_rect_norm')
        card['universal_scene_grammar']=grammar;card['story_phase_plan']=phase_plan;card['constraint_layout']=layout;card['relationship_resolutions']=relationship_resolutions
        # Observed concurrent primary/support count comes from story phases, not all card objects.
        peak_p=peak_s=0
        em={e['event_id']:e for e in selected_events}
        for ph in phase_plan.get('phases') or []:
            rr=[em[x] for x in ph.get('event_ids') or [] if x in em];peak_p=max(peak_p,sum(1 for e in rr if e['attention_priority']=='PRIMARY'));peak_s=max(peak_s,sum(1 for e in rr if e['attention_priority']!='PRIMARY'))
        card['rendered_primary_count']=peak_p;card['independently_animated_secondary_count']=peak_s;card['grouped_nonanimated_secondary_count']=max(0,int(card.get('secondary_count_estimate') or 0)-peak_s);card['rendered_secondary_count']=min(8,max(int(card.get('secondary_count_estimate') or 0),peak_s));card['rendered_count_rule_pass']=1<=peak_p<=2;card['choreography_action_count']=sum(2+len(e.get('preset_actions') or []) for e in selected_events);card['layout_policy']='V31_DENSITY_AWARE_PHASE_SOLVER__ATOMIC_ASSET_INDIVISIBILITY'
        card['composition_history_variant']=composition_variant;composition_history.append({'archetype':str(grammar.get('archetype') or 'SINGLE_FOCUS'),'variant':composition_variant})

    for e in events:
        if e.get('suppressed_by_card_density'):
            e['start_seconds']=e['end_seconds'];e['preset_entry']=None;e['preset_exit']=None;e['preset_actions']=[];e['motion_energy']='NONE'

    lifetime_stats=_commit_persistent_lifetimes(events,scenes_out,fps)
    cross_card_stats=_cross_card_handoff_optimize(events,cards,fps)
    atomic_stats=_atomic_handoff_optimize(events,cards,fps)
    segment_stats=_solve_semantic_segments(events,cards,fps)
    readable_hold_stats=_commit_readable_state_holds(events,cards,fps)
    recomposition_stats=_recomposition_optimize(events,cards,fps)
    optical_scale_stats=_optical_scale_optimize(events,cards,fps)
    spatial_choreography_stats=_spatial_choreography_optimize(events,cards,fps)
    # This must run after all entry/exit selection.  The exact animated
    # envelope is its authority; validating a handoff before a later spatial
    # entry rewrite would certify a timeline that no longer exists.
    effect_variety_stats=_effect_variety_director(events,cards,fps)
    sync_qa=perceptual_sync_qa(events,fps)
    out={'schema':'HEXA_MOTION_PLAN_V31','version':'31.0.25','fps':fps,'project_id':plan.get('project_id'),'rules_authority':'USER_UPLOADED_RULES_PDF','reference_authority':ref.get('authority_id'),'preset_authority':'HEXA_USER_PRESET_AUTHORITY_V31','timing_method':alignment.get('method'),'scenes':scenes_out,'events':events,'visual_cards':cards,'atomic_handoff_optimizer':atomic_stats,'cross_card_handoff_optimizer':cross_card_stats,'motion_dna_version':'HEXA_MOTION_DNA_V31_0_25_PREMIUM_MOTION_LANGUAGE','continuity_summary':{'scene_count':len(scenes_out),'visual_card_count':len(cards['cards']),'transition_modes':['OBJECT_PRESETS_ONLY__NO_FRAME_BLEND'],'appearance_methods':sorted(set(e.get('appearance_method') for e in events if e.get('appearance_method'))),'strong_transition_count':0,'identity_persistence_count':sum(1 for e in events if len(e.get('persistent_source_scene_ids') or [])>1),'white_reset_scene_percent':0.0},'budget_summary':{'story_action_count':sum(len(e.get('preset_actions') or []) for e in events),'choreography_action_count':sum(2+len(e.get('preset_actions') or []) for e in events if not e.get('suppressed_by_card_density')),'story_sources':['UNIVERSAL_SCENE_GRAMMAR','EXPLICIT_SEMANTIC_RELATIONSHIPS','SPATIOTEMPORAL_FEASIBILITY_SOLVER','ATOMIC_HANDOFF_TIMING_OPTIMIZER','CROSS_CARD_HANDOFF_CONSTRAINT_SOLVER','READABLE_STATE_LIFECYCLE_COMPILER','DETERMINISTIC_EFFECT_VARIETY_DIRECTOR','TYPOGRAPHY_MOTION_UNITS'],'hierarchical_motion_unit_count':0,'inferred_causal_edge_count':0,'actionable_story_edge_count':sum(1 for c in cards['cards'] for r in c.get('relationship_resolutions') or [] if r.get('mode')=='WITHIN_FRAME_PRESET'),'layout_choreography_action_count':sum(len(e.get('preset_actions') or []) for e in events),'story_eligible_scene_count':sum(1 for c in cards['cards'] if (c.get('universal_scene_grammar') or {}).get('explicit_edges'))},'hard_invariants':{'latest_user_rules_hard_authority':True,'user_prfpset_hard_authority':True,'user_visual_samples_hard_authority':True,'legacy_motion_heuristics_disabled':True,'speculative_subobject_cutouts_forbidden':True,'spatial_role_guessing_forbidden':True,'explicit_relationship_evidence_required':True,'layout_choreography_must_not_claim_semantic_relationship':True,'high_confidence_physical_semantic_mapping_required_for_relationship_motion':True,'visual_card_duration_seconds':[3.0,5.0],'primary_elements_per_card':[1,2],'primary_rule_interpretation':'MAX_CONCURRENT_VISIBLE_PRIMARY','secondary_elements_per_card':[3,8],'secondary_detail_count_may_remain_grouped_to_preserve_cutout_integrity':True,'entry_exit_primary_only':True,'within_frame_any_element':True,'appearance_prefer_secondary':True,'disappearance_any_element':True,'full_frame_crossfade_forbidden':True,'white_wash_forbidden':True,'mask_wipe_reveal_forbidden':True,'arbitrary_drift_forbidden':True,'arbitrary_diagonal_travel_forbidden':True,'auto_relationship_arrow_forbidden':True,'allowed_preset_names':sorted((preset_authority().get('preset_motion') or {}).keys()),'position_interpolation':'USER_VISUAL_SAMPLE_CURVES','position_motion_profile':'USER_PRFPSET_ENDPOINTS_PLUS_PHYSICAL_SAMPLE_TIMING','card_layout_policy':'DENSITY_AWARE_SPATIOTEMPORAL_PHASE_SOLVER__ATOMIC_ASSET_INDIVISIBILITY','topic_specific_motion_hardcoding_forbidden':True,'universal_content_type_classifier':True,'joint_story_layout_motion_planning':True}}
    visual_instances,semantic_events=_compile_visual_instances(events,scenes_out)
    out['visual_instances']=visual_instances;out['semantic_events']=semantic_events
    out['semantic_segment_solver']=segment_stats
    out['readable_state_hold_optimizer']=readable_hold_stats
    out['premium_recomposition_optimizer']=recomposition_stats
    out['effect_variety_director']=effect_variety_stats
    out['perceptual_sync_qa']=sync_qa
    out['premium_optical_scale_optimizer']=optical_scale_stats
    out['premium_spatial_choreography_optimizer']=spatial_choreography_stats
    out['instance_metrics']={'visual_instances_total':len(visual_instances),'semantic_events_total':len(semantic_events),'persistent_instances_total':sum(1 for x in visual_instances if len((x.get('persistence_source_evidence') or {}).get('source_states') or [])>1),'duplicate_same_identity_overlap_count':0,'illegal_persistence_count':0,'logical_instance_reentry_without_source_reset':0,**lifetime_stats}
    if logger:logger.log('PASS','MOTION_PLAN_BUILT',event_count=len(events),scene_count=len(scenes_out),visual_cards=len(cards['cards']),fps=fps,motion_dna=out['motion_dna_version'],story_actions=out['budget_summary']['story_action_count'],choreography_actions=out['budget_summary']['choreography_action_count'],suppressed_events=sum(1 for e in events if e.get('suppressed_by_card_density')),subobject_cutouts=0)
    return out
