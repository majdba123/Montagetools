from __future__ import annotations
import copy, math
from hexa_v31.util import read_json
from hexa_v31.framing import compute_reference_camera_fit
from hexa_v31.preset_authority import authority as preset_authority, duration as preset_duration, choose_entry_for_center, choose_exit_for_center, is_primary_semantic
from hexa_v31.visual_cards import build_visual_cards
from hexa_v31.scene_grammar import classify_card
from hexa_v31.composition_solver import build_story_phases, solve_card_layout, within_preset_safe, repair_story_phases, repartition_story_phases, candidate_middle_envelope_geometry, _in_safe, _fp, _rect, SAFE_X, SAFE_Y, MOTION_ENVELOPE_SCALE
from hexa_v31.composition_qa import card_motion_conflicts
from hexa_v31.visual_density import build_visual_density_report
from hexa_v31.editorial_motion import EditorialMotionGrammarDirector, PacingDirector
from hexa_v31.continuity_character import VisualContinuityQA, SemanticCharacterDirector
from hexa_v31.semantic_sentence import SemanticVisualSentenceCompiler
from hexa_v31.visual_affordance import classify as classify_affordance, legal_operations
from hexa_v31.beat_choreography import BeatChoreographyCompiler

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
        if str(carrier.get('editorial_within_frame_preference') or '')==name:score-=6.0
        if str(carrier.get('character_within_frame_preference') or '')==name:score-=5.0
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
        if abs(impact-anchor)>6.0/max(1.0,fps):
            row['flag']='VOICE_PRECEDES_VISUAL_RESULT' if impact>anchor else 'VISUAL_PRECEDES_VOICE_RESULT'
            row['premature_semantic_reveal']=impact<anchor
            fail.append(str(e.get('event_id')))
        rows.append(row)
    return {'schema':'HEXA_V31_PERCEPTUAL_SYNC_QA','version':'31.0.25','events':rows,'event_count':len(rows),'out_of_window_event_ids':fail,'bounded_pre_roll_pass':all(x['pre_roll_duration']<=1.44+1e-6 for x in rows),'no_premature_semantic_reveal_pass':all(not x['premature_semantic_reveal'] for x in rows),'pass':not fail}


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
            if carrier.get('preset_actions') or str(carrier.get('attention_priority') or '').upper()!='PRIMARY' or not carrier.get('pacing_discretionary_action_allowed',True) or 'TRANSLATE' not in (carrier.get('visual_affordance_operations') or []) or carrier.get('beat_choreography_fallback_static'):
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
                    # The stored rectangle is the solved motion envelope, not
                    # a nominal bbox. A within-frame preset may only claim the
                    # canonical middle when that real envelope remains legal.
                    if not _in_safe(centered):
                        stats['rejections']['SAFE_FRAME_ENVELOPE']=stats['rejections'].get('SAFE_FRAME_ENVELOPE',0)+1
                        continue
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
                from hexa_v31.composition_qa import composition_plan_qa
                if card_motion_conflicts(local,cs,ce,fps) or not composition_plan_qa(candidate_plan).get('pass'):
                    carrier.clear();carrier.update(snap);stats['rejections']['COLLISION_OR_PATH']=stats['rejections'].get('COLLISION_OR_PATH',0)+1;continue
                grammar=_interaction_grammar(carrier,nxt);carrier['premium_effect_variety_grammar']='SPATIAL_HANDOFF';carrier['premium_within_frame_recomposition']=True;carrier['interaction_grammar']=grammar;carrier['screen_memory_reuse']=True;carrier['handoff_target_event_id']=str(nxt.get('event_id'))
                if carrier.get('character_editorial_purpose'):
                    carrier['character_choreography']='CERTIFIED_'+str(carrier['character_editorial_purpose'])+'_EMPHASIS'
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

def _finalize_secondary_character_geometry(events):
    """Make one safe settled geometry authoritative after all late planners.

    Source placement is evidence, not a legal destination.  Secondary characters
    retain their composed scale whenever it fits; only an oversized envelope is
    minimally reduced, then its center is clamped inside the same safe frame the
    final motion QA samples.
    """
    changed=[]
    for e in events:
        if e.get('suppressed_by_card_density') or str(e.get('semantic_type') or '').upper()!='SECONDARY_CHARACTER':
            continue
        fp=_fp(e);scale=float(e.get('layout_scale_multiplier') or 1.0)
        fit=min((SAFE_X[1]-SAFE_X[0])/max(1e-9,fp.w*MOTION_ENVELOPE_SCALE),(SAFE_Y[1]-SAFE_Y[0])/max(1e-9,fp.h*MOTION_ENVELOPE_SCALE))
        final_scale=min(scale,fit)
        width,height=fp.w*final_scale*MOTION_ENVELOPE_SCALE,fp.h*final_scale*MOTION_ENVELOPE_SCALE
        prior=e.get('card_rest_position_norm') or e.get('source_center_norm') or [.5,.5]
        cx=min(SAFE_X[1]-width/2,max(SAFE_X[0]+width/2,float(prior[0])))
        cy=min(SAFE_Y[1]-height/2,max(SAFE_Y[0]+height/2,float(prior[1])))
        rect=list(_rect((cx,cy),fp,final_scale*MOTION_ENVELOPE_SCALE))
        if not _in_safe(rect):
            raise ValueError(f"{e.get('event_id')}: secondary character cannot fit safe frame")
        e['card_rest_position_norm']=[round(cx,6),round(cy,6)]
        e['layout_scale_multiplier']=round(final_scale,6)
        e['planned_rect_norm']=[round(x,6) for x in rect]
        e['collision_envelope_rect_norm']=list(e['planned_rect_norm'])
        e['final_settled_geometry_authority']='SECONDARY_CHARACTER_SAFE_ENVELOPE'
        changed.append(str(e.get('event_id')))
    return changed

def _final_physical_certification(events, cards, fps):
    """Perform one bounded repair, then certify the exact immutable plan state."""
    from hexa_v31.composition_qa import composition_plan_qa, _settled_rect
    def qa(): return composition_plan_qa({'events':events,'visual_cards':cards,'fps':fps})
    before=qa(); repairs=[]
    if before.get('pass'): return {'pass':True,'repair_passes':0,'before':before,'after':before,'repairs':repairs}
    # Settled conflicts are repaired by the same phase-aware solver that owns
    # composition. Every geometry field is committed as one tuple.
    for card in cards.get('cards') or []:
        cid=str(card.get('card_id'));local=[e for e in events if str(e.get('visual_card_id'))==cid and not e.get('suppressed_by_card_density')]
        phases=(card.get('story_phase_plan') or {}).get('phases') or []
        settled_bad=False
        for ph in phases:
            rows=[e for e in local if e.get('event_id') in (ph.get('event_ids') or [])]
            rects=[_settled_rect(e) for e in rows]
            if any(not _in_safe(r) for r in rects):
                settled_bad=True
            for i,a in enumerate(rects):
                for j,b in enumerate(rects[i+1:],i+1):
                    from hexa_v31.composition_solver import overlap_ratio
                    aa,bb=rows[i],rows[j]
                    limit=0.002 if str(aa.get('attention_priority')).upper()=='PRIMARY' and str(bb.get('attention_priority')).upper()=='PRIMARY' else (0.01 if str(aa.get('attention_priority')).upper()=='PRIMARY' or str(bb.get('attention_priority')).upper()=='PRIMARY' else 0.025)
                    if overlap_ratio(a,b) > limit: settled_bad=True
        if settled_bad and local:
            layout=solve_card_layout(local,card.get('universal_scene_grammar') or {'archetype':'GENERIC'},card.get('story_phase_plan') or {'phases':[]})
            if layout.get('pass'):
                for e in local:
                    p=layout['placements'].get(e.get('event_id'))
                    if not p:continue
                    e['card_rest_position_norm']=list(p['center_norm']);e['planned_rect_norm']=list(p['rect_norm']);e['collision_envelope_rect_norm']=list(p['rect_norm']);e['layout_scale_multiplier']=float(p['scale']);e['composition_role']=p['role'];e['composite_atomic']=bool(p['atomic'])
                repairs.append({'card_id':cid,'type':'SETTLED_GEOMETRY_RESOLVE'})
    # Motion-path conflicts first lose optional choreography; if the physical
    # path remains illegal, recompile only those events to certified scale/fade.
    for card in cards.get('cards') or []:
        cid=str(card.get('card_id'));local=[e for e in events if str(e.get('visual_card_id'))==cid and not e.get('suppressed_by_card_density')];conflicts=card_motion_conflicts(local,float(card.get('start_seconds',0)),float(card.get('end_seconds',0)),fps)
        if not conflicts:continue
        involved={x for r in conflicts for x in (r.get('event_a'),r.get('event_b'))}
        for e in local:
            if str(e.get('event_id')) in involved and e.get('preset_actions'):
                e['preset_actions']=[];e['final_physical_repair']='OPTIONAL_CHOREOGRAPHY_REMOVED';repairs.append({'card_id':cid,'event_id':e.get('event_id'),'type':'REMOVE_OPTIONAL_CHOREOGRAPHY'})
        conflicts=card_motion_conflicts(local,float(card.get('start_seconds',0)),float(card.get('end_seconds',0)),fps)
        if conflicts:
            for e in local:
                if str(e.get('event_id')) not in {x for r in conflicts for x in (r.get('event_a'),r.get('event_b'))}:continue
                window=_phase_for_event(card.get('story_phase_plan') or {},str(e.get('event_id')))
                if window:
                    _schedule_event(e,window,card,local.index(e),len(local),force_static=True,local_events=local,fps=fps)
                    e['final_physical_repair']='CERTIFIED_STATIC_SCALE_FALLBACK';repairs.append({'card_id':cid,'event_id':e.get('event_id'),'type':'STATIC_SCALE_FALLBACK'})
    after=qa()
    if not after.get('pass'):raise ValueError('FINAL_PHYSICAL_CERTIFICATION_FAILED: '+' | '.join(after.get('failures') or [])[:2000])
    return {'pass':True,'repair_passes':1,'before':before,'after':after,'repairs':repairs}

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
                p=layout['placements'][x['event_id']]
                x['card_rest_position_norm']=p['center_norm'];x['layout_scale_multiplier']=p['scale']
                x['planned_rect_norm']=p['rect_norm'];x['collision_envelope_rect_norm']=p['rect_norm']
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
    from hexa_v31.composition_qa import _state
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
        # Certified Foundation reconstruction members are source-survival atomic.
        # Semantic identity persistence may merge logical states, but it may not
        # suppress one physical member and redefine a partial partition as complete.
        if e.get('render_mode') in {'CHILD_PARTITION','RESIDUAL_SUPPORT'} or m.get('render_mode') in {'CHILD_PARTITION','RESIDUAL_SUPPORT'}:
            continue
        if key[1].startswith('PHYS::'):continue
        e['suppressed_by_card_density']=True;e['suppression_reason']='CARD_IDENTITY_PERSISTENCE';e['persistent_master_event_id']=m['event_id']
        m.setdefault('persistent_source_scene_ids',[]).append(e.get('scene_id'));m['perceptual_hit_seconds']=min(float(m.get('perceptual_hit_seconds',0)),float(e.get('perceptual_hit_seconds',0)))
    return masters

def _event_is_atomic(e:dict)->bool:
    b=e.get('source_bbox_norm') or [0,0,.3,.3];w=float(b[2])*float(e.get('reference_camera_scale') or 1.0);h=float(b[3])*float(e.get('reference_camera_scale') or 1.0);detail=int(e.get('source_grouped_detail_count') or 0)
    return bool(w>0.50 or h>0.58 or w*h>0.16 or detail>=5)

def _select_render_units(vision_row:dict)->tuple[list[dict],dict]:
    """Choose one source-backed render representation for every semantic root.

    Hierarchy extraction is evidence, not an instruction to stack the root and
    its pixels.  A partition is enabled only when the vision decision accepted
    an exact child reconstruction and every child is a real full-canvas mask.
    Otherwise the root remains the sole renderable object.
    """
    units=list(vision_row.get('units') or [])
    foundation=[u for u in units if u.get('candidate_source') and u.get('mask_path')]
    residual=[u for u in units if u.get('foundation_residual_support') and u.get('mask_path')]
    reconstruction=((vision_row.get('artifacts') or {}).get('foundation_vision') or {}).get('reconstruction_qa') or {}
    if foundation and reconstruction.get('partition_complete') and all(u.get('partition_complete') for u in foundation+residual):
        selected=[]
        for index,actor in enumerate(sorted(foundation,key=lambda u:str(u.get('physical_id') or ''))):
            row=dict(actor);row['render_mode']='CHILD_PARTITION';row['partition_root_id']='ROOT_COMPOSITE';row['partition_complete']=True
            row['independent_motion_allowed']=bool(row.get('translation_safe_after_occlusion',row.get('animation_safe')));row['partition_primary_member']=bool(index==0 and is_primary_semantic(row));selected.append(row)
        for support in residual:
            row=dict(support);row['render_mode']='RESIDUAL_SUPPORT';row['independent_motion_allowed']=False;row['partition_primary_member']=False;selected.append(row)
        return selected,{'partition_root_ids':['ROOT_COMPOSITE'],'atomic_root_ids':['ROOT_COMPOSITE_FALLBACK'],'hierarchical_motion_unit_count':len(foundation),'foundation_actor_partition':True,'residual_support_present':bool(residual),'reconstruction_qa':reconstruction}
    roots=[u for u in units if int(u.get('hierarchy_level') or 0)==0]
    children=[u for u in units if int(u.get('hierarchy_level') or 0)>0]
    decisions={str(d.get('root_id')):d for d in ((vision_row.get('artifacts') or {}).get('hierarchy_decisions') or [])}
    selected=[];partition_roots=[];fallback_roots=[]
    for root in roots:
        rid=str(root.get('root_id') or '')
        members=[u for u in children if str(u.get('root_id') or u.get('parent_id') or '')==rid]
        decision=decisions.get(rid) or {}
        is_character='CHARACTER' in str(root.get('semantic_type') or '').upper()
        evidence=bool(decision.get('accepted')) and len(members)>=2 and not is_character
        evidence=evidence and all(bool(u.get('reveal_safe')) and u.get('mask_path') and str(u.get('composition_slot_id') or '')==str(root.get('composition_slot_id') or '') for u in members)
        if not evidence:
            row=dict(root);row['render_mode']='ROOT_ATOMIC';row['partition_root_id']=rid;row['partition_evidence']='ROOT_ATOMIC_FALLBACK'
            selected.append(row);fallback_roots.append(rid);continue
        partition_roots.append(rid)
        for index,child in enumerate(sorted(members,key=lambda u:str(u.get('physical_id') or ''))):
            row=dict(child);row['render_mode']='CHILD_PARTITION';row['partition_root_id']=rid;row['partition_complete']=True
            row['independent_motion_allowed']=bool(row.get('animation_safe'))
            # A partition still occupies one semantic composition slot.  Its
            # leading child carries semantic focus; remaining pixels are
            # supports and never consume additional primary capacity.
            row['partition_primary_member']=bool(index==0 and is_primary_semantic(root))
            selected.append(row)
    return selected,{'partition_root_ids':partition_roots,'atomic_root_ids':fallback_roots,
                     'hierarchical_motion_unit_count':sum(1 for u in selected if u.get('render_mode')=='CHILD_PARTITION')}

def _phase_for_event(phase_plan:dict,eid:str):
    rows=[p for p in (phase_plan.get('phases') or []) if eid in (p.get('event_ids') or [])]
    if not rows:return None
    return float(rows[0]['start_seconds']),float(rows[-1]['end_seconds'])

def _clamp(v,a,b):return max(a,min(b,v))

def _plan_foundation_partition_choreography(events:list[dict], phase_plan:dict)->dict:
    """Approve only layout-compatible, source-backed partition motion before scheduling."""
    eligible=[];approved=[];blocked=[]
    for e in sorted(events,key=lambda x:str(x.get('physical_id') or x.get('event_id'))):
        if e.get('render_mode')!='CHILD_PARTITION':continue
        if not e.get('translation_safe_after_occlusion') or not e.get('independent_motion_allowed'):
            e['foundation_motion_decision']='REVEAL_ONLY';blocked.append({'physical_id':e.get('physical_id'),'reason':'TRANSLATION_UNSAFE_OR_OCCLUSION_DEPENDENT'});continue
        eligible.append(e);window=_phase_for_event(phase_plan,str(e.get('event_id')));duration=0.0 if not window else window[1]-window[0];candidate=candidate_middle_envelope_geometry(e)
        if duration < preset_duration('ENTRY_LEFT_TO_MIDDLE')+.72 or e.get('composite_atomic') or not candidate.get('safe'):
            e['foundation_motion_decision']='REVEAL_ONLY';blocked.append({'physical_id':e.get('physical_id'),'reason':'INSUFFICIENT_DURATION_OR_UNSAFE_MIDDLE_ENVELOPE'});continue
        e['foundation_motion_decision']='APPROVED_POSITION_ENTRY';e['foundation_motion_layout_candidate']=candidate;approved.append(e)
    return {'eligible_foundation_actor_count':len(eligible),'approved_foundation_actor_count':len(approved),'blocked':blocked}

def _foundation_partition_motion_contract(events:list[dict])->dict:
    """Summarize only the final committed event state, never provisional approval."""
    rows=[e for e in events if e.get('render_mode')=='CHILD_PARTITION' and not e.get('suppressed_by_card_density')]
    independent=[e for e in rows if e.get('position_animated')]
    eligible=sum(bool(e.get('translation_safe_after_occlusion') and e.get('independent_motion_allowed')) for e in rows)
    signatures={(str((e.get('preset_entry') or {}).get('name')),tuple(str(a.get('name')) for a in (e.get('preset_actions') or []))) for e in independent}
    return {'eligible_foundation_actor_count':eligible,'independently_animated_actor_count':len(independent),'independent_actor_motion_ratio':round(len(independent)/max(1,eligible),4),'spatially_displaced_actor_count':len(independent),'distinct_motion_signature_count':len(signatures),'static_support_actor_count':sum(e.get('attention_priority')=='SUPPORTING' and not e.get('position_animated') for e in rows),'reveal_only_actor_count':sum(e.get('foundation_motion_decision')=='REVEAL_ONLY' for e in rows)}

def _motion_interval_effective_fraction(kind:str, preset_name:str)->float:
    """Return the source-visible fraction of a certified preset interval.

    Preset duration remains the exact user authority.  Lifetime certification
    cares about the interval that can still affect visible source pixels.  For
    disappearance presets, an authored zero-opacity tail is therefore not a
    physical motion escape.
    """
    if str(kind).upper()!='EXIT' or not preset_name:
        return 1.0
    definition=(preset_authority().get('preset_motion') or {}).get(str(preset_name)) or {}
    if str(definition.get('family') or '').upper()!='DISAPPEARANCE':
        return 1.0
    keys=definition.get('opacity_keyframes') or []
    for index,row in enumerate(keys):
        try:
            fraction=float(row[0]);opacity=float(row[1])
        except (TypeError,ValueError,IndexError):
            continue
        if opacity>1e-6:
            continue
        trailing=keys[index:]
        try:
            if trailing and all(float(item[1])<=1e-6 for item in trailing):
                return max(0.0,min(1.0,fraction))
        except (TypeError,ValueError,IndexError):
            pass
    return 1.0


def _compile_final_motion_intervals(e:dict)->tuple[list[dict],float,float]:
    """Compile nominal preset records plus their effective visible envelopes."""
    rows=[]
    raw=[]
    if e.get('preset_entry'):raw.append(('ENTRY',e['preset_entry']))
    raw.extend(('ACTION',a) for a in (e.get('preset_actions') or []))
    if e.get('preset_exit'):raw.append(('EXIT',e['preset_exit']))
    starts=[float(e.get('start_seconds',0))]
    ends=[float(e.get('end_seconds',e.get('start_seconds',0)))]
    for kind,source in raw:
        row=dict(kind=kind,**source)
        st=float(row.get('start_seconds',e.get('start_seconds',0)))
        nominal=max(0.0,float(row.get('duration_seconds') or 0.0))
        fraction=_motion_interval_effective_fraction(kind,str(row.get('name') or ''))
        effective_end=st+nominal*fraction
        row['effective_start_seconds']=round(st,6)
        row['effective_end_seconds']=round(effective_end,6)
        row['effective_duration_seconds']=round(max(0.0,effective_end-st),6)
        row['effective_visible_fraction']=round(fraction,6)
        rows.append(row);starts.append(st);ends.append(effective_end)
    return rows,min(starts),max(ends)


def _retime_exit_to_effective_end(e:dict, effective_end:float, minimum_start:float)->None:
    exit_row=e.get('preset_exit')
    if not exit_row:return
    duration=max(0.0,float(exit_row.get('duration_seconds') or 0.0))
    fraction=_motion_interval_effective_fraction('EXIT',str(exit_row.get('name') or ''))
    visible_duration=duration*fraction
    exit_row['start_seconds']=round(max(float(minimum_start),float(effective_end)-visible_duration),6)


def _reconcile_final_partition_handoffs(events:list[dict], cards:dict, fps:float)->dict:
    """Resolve late cross-scene collisions on the exact committed lifetimes.

    This is a bounded final-state search, not a density/suppression shortcut.
    Outgoing source carriers may retire earlier only when an incoming source has
    become readable. Incoming reveal timing may move by at most six frames, the
    existing perceptual-sync tolerance. Certified Foundation partitions remain
    atomic and no source member is deleted.
    """
    from hexa_v31.composition_qa import card_motion_conflicts, _state

    step=1.0/max(1.0,float(fps))
    max_sync_frames=6
    card_by={str(row.get('card_id')):row for row in (cards.get('cards') or [])}
    active=[e for e in events if not e.get('suppressed_by_card_density')]

    groups={}
    def cohort_key(e):
        card_id=str(e.get('visual_card_id'))
        scene_id=str(e.get('scene_id'))
        if e.get('render_mode') in {'CHILD_PARTITION','RESIDUAL_SUPPORT'}:
            return (card_id,scene_id,'PARTITION',str(e.get('partition_root_id')))
        return (card_id,scene_id,'EVENT',str(e.get('event_id')))
    for e in active:
        groups.setdefault(cohort_key(e),[]).append(e)

    stats={'candidate_conflict_count':0,'candidate_schedules_evaluated':0,
           'handoffs_committed':0,'handoffs_rejected':0,
           'trimmed_partition_group_count':0,'trimmed_source_group_count':0,
           'motion_fallback_count':0,'incoming_delay_frames':[],
           'trimmed_event_ids':[],'repairs':[]}

    def source_order(e):
        return float(e.get('source_scene_start_seconds',
                           e.get('perceptual_hit_seconds',
                                 e.get('physical_start_seconds',e.get('start_seconds',0.0)))))

    def _restore(rows,snaps):
        for live,snap in zip(rows,snaps):
            live.clear();live.update(copy.deepcopy(snap))

    def _clip_motion_to_carrier(e,new_end):
        intervals,motion_start,_=_compile_final_motion_intervals(e)
        clipped=[]
        for row in intervals:
            row=dict(row)
            start=float(row.get('effective_start_seconds',row.get('start_seconds',0.0)))
            old_end=float(row.get('effective_end_seconds',start))
            end=min(float(new_end),old_end)
            row['effective_end_seconds']=round(end,6)
            row['effective_duration_seconds']=round(max(0.0,end-start),6)
            if old_end>new_end+1e-6:
                row['clipped_by_final_source_handoff']=True
            clipped.append(row)
        motion_end=max([float(r.get('effective_end_seconds',motion_start)) for r in clipped] or [motion_start])
        return clipped,motion_start,motion_end

    def _entry_family(e):
        name=str((e.get('preset_entry') or {}).get('name') or '')
        return str(((preset_authority().get('preset_motion') or {}).get(name) or {}).get('family') or '')

    def _compile_event_after_trim(e,new_end):
        current_end=max(float(e.get('end_seconds',0.0)),
                        float(e.get('physical_end_seconds',e.get('end_seconds',0.0))))
        if current_end<=new_end+1e-6:
            return True,False

        physical_start=float(e.get('physical_start_seconds',e.get('start_seconds',0.0)))
        if new_end<=physical_start+step*.5:
            return False,False

        if e.get('render_mode')=='RESIDUAL_SUPPORT':
            e['end_seconds']=round(new_end,6)
            e['physical_end_seconds']=round(new_end,6)
            e['visibility_interval_seconds']=[round(physical_start,6),round(new_end,6)]
            e['motion_start_seconds']=round(physical_start,6)
            e['motion_end_seconds']=round(physical_start,6)
            e['motion_intervals']=[]
            e['preset_entry']=None;e['preset_exit']=None;e['preset_actions']=[]
            if e.get('partition_carrier_end_seconds') is not None:
                e['partition_carrier_end_seconds']=round(new_end,6)
            e['final_cross_source_handoff_authority']='SOURCE_STATE_TO_READABLE_SUCCESSOR'
            return True,False

        dd=preset_duration('DISAPPEAR_DOWN_SCALE')
        visible_dd=dd*_motion_interval_effective_fraction('EXIT','DISAPPEAR_DOWN_SCALE')
        latest_exit_start=float(new_end)-visible_dd
        if latest_exit_start<=physical_start+step*.25:
            return False,False

        fallback=False
        intervals,_,_=_compile_final_motion_intervals(e)
        non_exit_end=max(
            [float(row.get('effective_end_seconds',row.get('start_seconds',physical_start)))
             for row in intervals if str(row.get('kind')).upper()!='EXIT']
            or [float(e.get('start_seconds',physical_start))]
        )
        if non_exit_end>latest_exit_start-step*.25 and e.get('preset_actions'):
            e['preset_actions']=[]
            fallback=True
            intervals,_,_=_compile_final_motion_intervals(e)
            non_exit_end=max(
                [float(row.get('effective_end_seconds',row.get('start_seconds',physical_start)))
                 for row in intervals if str(row.get('kind')).upper()!='EXIT']
                or [float(e.get('start_seconds',physical_start))]
            )

        # Scale/opacity appearance and scale/opacity disappearance may overlap in
        # a short legal beat. The carrier boundary clips the authored tail; this
        # is materially different from shortening/deleting the source. Position
        # travel still cannot overlap because two absolute motion paths would
        # compete for the same object transform.
        if non_exit_end>latest_exit_start-step*.25 and _entry_family(e)!='APPEARANCE':
            ad=preset_duration('APPEAR_HIGH_SCALE')
            original_hit=float(e.get('perceptual_hit_seconds',
                               (e.get('preset_entry') or {}).get('start_seconds',physical_start)))
            entry_start=original_hit-_entry_fraction({'preset_entry':{'name':'APPEAR_HIGH_SCALE'}})*ad
            entry_start=max(physical_start,entry_start)
            if entry_start>=latest_exit_start-step*.25:
                return False,fallback
            e['preset_entry']={'name':'APPEAR_HIGH_SCALE','start_seconds':round(entry_start,6),
                               'duration_seconds':ad,
                               'authority':'FINAL_CROSS_SOURCE_REVEAL_FALLBACK'}
            e['preset_actions']=[]
            e['start_seconds']=round(entry_start,6)
            e['settle_seconds']=round(entry_start+ad,6)
            e['appearance_method']='SCALE_POP'
            e['position_animated']=False
            e['entry_direction']=None
            if e.get('render_mode')=='CHILD_PARTITION':
                e['foundation_motion_decision']='REVEAL_ONLY'
            fallback=True

        e['preset_exit']={'name':'DISAPPEAR_DOWN_SCALE',
                          'start_seconds':round(latest_exit_start,6),
                          'duration_seconds':dd,
                          'authority':'FINAL_CROSS_SOURCE_HANDOFF'}
        e['disappearance_method']='PRESET_DISAPPEARANCE'
        e['end_seconds']=round(new_end,6)
        e['physical_end_seconds']=round(new_end,6)
        e['visibility_interval_seconds']=[round(physical_start,6),round(new_end,6)]
        if e.get('partition_carrier_end_seconds') is not None:
            e['partition_carrier_end_seconds']=round(new_end,6)

        clipped,motion_start,motion_end=_clip_motion_to_carrier(e,new_end)
        e['motion_intervals']=clipped
        e['motion_start_seconds']=round(motion_start,6)
        e['motion_end_seconds']=round(motion_end,6)
        e['partition_exit_retimed_to_carrier_end']=bool(
            e.get('render_mode') in {'CHILD_PARTITION','RESIDUAL_SUPPORT'})
        e['final_cross_source_handoff_authority']='SOURCE_STATE_TO_READABLE_SUCCESSOR'

        # A voice-owned semantic result must still be materially visible at its
        # anchor after the shortened handoff. Otherwise the candidate is illegal.
        anchor=float(e.get('perceptual_hit_seconds',e.get('start_seconds',physical_start)))
        if anchor<new_end-step*.25:
            state=_state(e,anchor)
            if state is None or float(state[2])<=.22:
                return False,fallback
        elif str(e.get('perceptual_hit_source') or '').upper()=='VOICE_TRIGGER':
            return False,fallback

        if fallback:
            e['final_cross_source_motion_fallback']='OPTIONAL_MOTION_TO_SAFE_REVEAL'
        if any(r.get('clipped_by_final_source_handoff') for r in clipped):
            e['final_cross_source_motion_tail_clipped']=True
        return True,fallback

    def apply_end(members,new_end):
        snapshots=[copy.deepcopy(e) for e in members]
        fallback_count=0
        for e in members:
            ok,fallback=_compile_event_after_trim(e,new_end)
            if not ok:
                _restore(members,snapshots)
                return False,0
            fallback_count+=1 if fallback else 0

        if any(e.get('render_mode') in {'CHILD_PARTITION','RESIDUAL_SUPPORT'} for e in members):
            ends={round(float(e.get('physical_end_seconds',e.get('end_seconds',0.0))),6)
                  for e in members}
            if len(ends)>1:
                _restore(members,snapshots)
                return False,0
        return True,fallback_count

    def first_readable_frame(e,card):
        start=max(float(card.get('start_seconds',0.0)),float(e.get('start_seconds',0.0)))
        end=min(float(card.get('end_seconds',start)),float(e.get('end_seconds',card.get('end_seconds',start))))
        first=max(0,int(math.floor(start*fps)))
        last=max(first,int(math.ceil(end*fps)))
        for fi in range(first,last+1):
            t=fi/fps
            state=_state(e,t)
            if state and float(state[2])>.22:
                return t
        return None

    def shift_incoming_reveal(e,delay_frames):
        if delay_frames<=0:
            return True
        if e.get('render_mode') in {'CHILD_PARTITION','RESIDUAL_SUPPORT'}:
            return False
        entry=e.get('preset_entry')
        if not entry:
            return False
        delta=float(delay_frames)*step
        new_start=float(entry.get('start_seconds',e.get('start_seconds',0.0)))+delta
        duration=float(entry.get('duration_seconds') or preset_duration(str(entry.get('name') or 'APPEAR_HIGH_SCALE')))
        impact=new_start+_entry_fraction(e)*duration
        anchor=float(e.get('perceptual_hit_seconds',impact))
        if abs(impact-anchor)*fps>max_sync_frames+1e-6:
            return False
        old_start=float(e.get('start_seconds',new_start-delta))
        e['start_seconds']=round(max(old_start+delta,new_start),6)
        entry['start_seconds']=round(new_start,6)
        prior_ps=float(e.get('physical_start_seconds',old_start))
        e['physical_start_seconds']=round(max(prior_ps+delta,e['start_seconds']),6)
        e['visibility_interval_seconds']=[e['physical_start_seconds'],
                                          float(e.get('physical_end_seconds',e.get('end_seconds',e['start_seconds'])))]
        intervals,motion_start,motion_end=_compile_final_motion_intervals(e)
        e['motion_intervals']=intervals
        e['motion_start_seconds']=round(motion_start,6)
        e['motion_end_seconds']=round(motion_end,6)
        e['final_cross_source_incoming_delay_frames']=int(delay_frames)
        return True

    max_passes=max(1,len(groups)*4)
    for _ in range(max_passes):
        committed=False
        for cid,card in card_by.items():
            local=[e for e in active if str(e.get('visual_card_id'))==cid]
            conflicts=card_motion_conflicts(local,float(card.get('start_seconds',0.0)),
                                            float(card.get('end_seconds',0.0)),fps)
            if not conflicts:
                continue
            local_by_id={str(e.get('event_id')):e for e in local}
            before_pairs={tuple(sorted((str(x.get('event_a')),str(x.get('event_b')))))
                          for x in conflicts}
            for row in sorted(conflicts,key=lambda x:(float(x.get('time_seconds',0.0)),
                                                      str(x.get('event_a')),str(x.get('event_b')))):
                a=local_by_id.get(str(row.get('event_a')))
                b=local_by_id.get(str(row.get('event_b')))
                if not a or not b or str(a.get('scene_id'))==str(b.get('scene_id')):
                    continue
                stats['candidate_conflict_count']+=1

                if source_order(a)<source_order(b)-1e-6:
                    outgoing,incoming=a,b
                elif source_order(b)<source_order(a)-1e-6:
                    outgoing,incoming=b,a
                else:
                    continue

                members=groups.get(cohort_key(outgoing)) or []
                incoming_members=groups.get(cohort_key(incoming)) or [incoming]
                current_end=max(float(e.get('physical_end_seconds',e.get('end_seconds',0.0)))
                                for e in members)
                group_start=min(float(e.get('physical_start_seconds',e.get('start_seconds',0.0)))
                                for e in members)
                trigger_pair=tuple(sorted((str(row.get('event_a')),str(row.get('event_b')))))
                outgoing_snap=[copy.deepcopy(e) for e in members]
                incoming_snap=[copy.deepcopy(e) for e in incoming_members]

                for delay_frames in range(0,max_sync_frames+1):
                    stats['candidate_schedules_evaluated']+=1
                    _restore(members,outgoing_snap)
                    _restore(incoming_members,incoming_snap)
                    incoming_live=next((e for e in incoming_members
                                        if str(e.get('event_id'))==str(incoming.get('event_id'))),incoming_members[0])
                    if delay_frames and (len(incoming_members)!=1 or not shift_incoming_reveal(incoming_live,delay_frames)):
                        continue

                    readable=first_readable_frame(incoming_live,card)
                    if readable is None:
                        continue
                    handoff=min(current_end,float(readable)-step)
                    handoff=max(handoff,group_start+step)
                    if handoff>=current_end-step*.25:
                        continue
                    ok,fallback_count=apply_end(members,handoff)
                    if not ok:
                        continue

                    after_rows=card_motion_conflicts(local,float(card.get('start_seconds',0.0)),
                                                     float(card.get('end_seconds',0.0)),fps)
                    after_pairs={tuple(sorted((str(x.get('event_a')),str(x.get('event_b')))))
                                 for x in after_rows}
                    if trigger_pair in after_pairs or len(after_pairs)>=len(before_pairs):
                        continue

                    ids=[str(e.get('event_id')) for e in members]
                    partition_ids=[e for e in members
                                   if e.get('render_mode') in {'CHILD_PARTITION','RESIDUAL_SUPPORT'}]
                    stats['handoffs_committed']+=1
                    stats['trimmed_source_group_count']+=1
                    if partition_ids:
                        stats['trimmed_partition_group_count']+=1
                    stats['motion_fallback_count']+=fallback_count
                    stats['incoming_delay_frames'].append(int(delay_frames))
                    stats['trimmed_event_ids'].extend(ids)
                    stats['repairs'].append({
                        'visual_card_id':cid,'scene_id':str(outgoing.get('scene_id')),
                        'handoff_seconds':round(handoff,6),
                        'incoming_scene_id':str(incoming_live.get('scene_id')),
                        'incoming_delay_frames':int(delay_frames),
                        'trigger_conflict':dict(row),'event_ids':ids,
                        'motion_fallback_count':fallback_count,
                        'authority':'FINAL_CROSS_SCENE_BOUNDED_HANDOFF_SEARCH',
                    })
                    committed=True
                    break

                if committed:
                    break
                _restore(members,outgoing_snap)
                _restore(incoming_members,incoming_snap)
                stats['handoffs_rejected']+=1
            if committed:
                break
        if not committed:
            break

    stats['trimmed_event_ids']=sorted(set(stats['trimmed_event_ids']))
    return stats


def _finalize_visual_lifetimes(events:list[dict], cards:dict, fps:float=30.0)->dict:
    """Commit physical carrier lifetimes from the final immutable motion state.

    Scheduling establishes provisional timing only. Downstream optimizers may
    legally retime entry/action/exit presets, so physical lifetime is committed
    once, after every timing-mutating pass. Certified partition members share
    one carrier envelope while retaining independent motion intervals.
    """
    card_by={str(c.get('card_id')):c for c in (cards.get('cards') or [])}
    active=[e for e in events if not e.get('suppressed_by_card_density')]
    stats={'event_count':len(active),'partition_group_count':0,'partition_member_count':0,
           'suppressed_partition_member_count':0,'recommitted_event_count':0}

    # A certified partition is source-survival atomic. Never allow density or
    # identity suppression to silently turn it into a partial reconstruction.
    partition_all={}
    for e in events:
        if e.get('render_mode') not in {'CHILD_PARTITION','RESIDUAL_SUPPORT'}:
            continue
        key=(str(e.get('visual_card_id')),str(e.get('scene_id')),str(e.get('partition_root_id')))
        partition_all.setdefault(key,[]).append(e)
    partial=[]
    for key,members in partition_all.items():
        suppressed=[e for e in members if e.get('suppressed_by_card_density')]
        live=[e for e in members if not e.get('suppressed_by_card_density')]
        if suppressed and live:
            stats['suppressed_partition_member_count']+=len(suppressed)
            partial.append((key,[str(e.get('event_id')) for e in suppressed]))
    if partial:
        detail=' | '.join(f"{k[0]}:{k[1]}:{k[2]} suppressed={ids}" for k,ids in partial[:8])
        raise ValueError('PARTIAL_CERTIFIED_PARTITION_SUPPRESSION: '+detail)

    for e in active:
        intervals,motion_start,motion_end=_compile_final_motion_intervals(e)
        prior_start=float(e.get('physical_start_seconds',motion_start))
        prior_end=float(e.get('physical_end_seconds',motion_end))
        e['motion_start_seconds']=round(motion_start,6)
        e['motion_end_seconds']=round(motion_end,6)
        e['motion_intervals']=intervals
        e['physical_start_seconds']=round(min(prior_start,motion_start),6)
        e['physical_end_seconds']=round(max(prior_end,motion_end),6)
        e['visibility_interval_seconds']=[e['physical_start_seconds'],e['physical_end_seconds']]
        e['final_lifetime_authority']='FINAL_COMMITTED_MOTION_AND_CARRIER_STATE'
        stats['recommitted_event_count']+=1

    groups={}
    for e in active:
        if e.get('render_mode') not in {'CHILD_PARTITION','RESIDUAL_SUPPORT'}:
            continue
        key=(str(e.get('visual_card_id')),str(e.get('scene_id')),str(e.get('partition_root_id')))
        groups.setdefault(key,[]).append(e)
    for key,members in groups.items():
        carrier_start=min(float(e['physical_start_seconds']) for e in members)
        carrier_end=max(float(e['physical_end_seconds']) for e in members)
        card=card_by.get(key[0])
        if card is not None:
            carrier_start=max(float(card.get('start_seconds',carrier_start)),carrier_start)
            carrier_end=min(float(card.get('end_seconds',carrier_end)),carrier_end)
        if carrier_end<=carrier_start+1e-6:
            raise ValueError(f"{key[0]}:{key[1]}:{key[2]} invalid Foundation partition carrier lifetime")
        for e in members:
            # Existence is group-owned; reveal/action timing remains actor-owned.
            # If this member's disappearance was scheduled before the group
            # carrier ends, move only that final exit to the carrier boundary.
            # Otherwise the renderer would correctly preserve physical lifetime
            # but visibly exit and then reappear as a held state.
            if e.get('render_mode')!='RESIDUAL_SUPPORT' and e.get('preset_exit'):
                exit_row=e['preset_exit']
                exit_start=float(exit_row.get('start_seconds',e.get('end_seconds',carrier_end)))
                exit_duration=max(0.0,float(exit_row.get('duration_seconds') or 0.0))
                exit_fraction=_motion_interval_effective_fraction('EXIT',str(exit_row.get('name') or ''))
                exit_effective_end=exit_start+exit_duration*exit_fraction
                if carrier_end>exit_effective_end+1e-6:
                    _retime_exit_to_effective_end(e,carrier_end,float(e.get('motion_start_seconds',carrier_start)))
                    e['end_seconds']=round(carrier_end,6)
                    intervals,motion_start,motion_end=_compile_final_motion_intervals(e)
                    e['motion_intervals']=intervals
                    e['motion_start_seconds']=round(motion_start,6)
                    e['motion_end_seconds']=round(motion_end,6)
                    e['partition_exit_retimed_to_carrier_end']=True
            e['partition_carrier_start_seconds']=round(carrier_start,6)
            e['partition_carrier_end_seconds']=round(carrier_end,6)
            e['physical_start_seconds']=round(carrier_start,6)
            e['physical_end_seconds']=round(carrier_end,6)
            e['visibility_interval_seconds']=[e['physical_start_seconds'],e['physical_end_seconds']]
            motion_escapes=(float(e.get('motion_start_seconds',carrier_start))<carrier_start-1e-6 or
                            float(e.get('motion_end_seconds',carrier_end))>carrier_end+1e-6)
            if motion_escapes and e.get('render_mode')!='RESIDUAL_SUPPORT':
                # Final semantic/card ownership is harder authority than an
                # optional animated path. Preserve the complete source member
                # and compile a bounded reveal/hold/exit instead of deleting it
                # or allowing motion to escape the carrier.
                ad=preset_duration('APPEAR_HIGH_SCALE');dd=preset_duration('DISAPPEAR_DOWN_SCALE')
                disappear_fraction=_motion_interval_effective_fraction('EXIT','DISAPPEAR_DOWN_SCALE')
                visible_dd=dd*disappear_fraction
                latest_entry=max(carrier_start,carrier_end-visible_dd-ad-0.10)
                old_entry=float((e.get('preset_entry') or {}).get('start_seconds',e.get('start_seconds',carrier_start)))
                st=max(carrier_start,min(old_entry,latest_entry))
                xs=max(st+ad+0.05,carrier_end-visible_dd)
                if xs+visible_dd>carrier_end+1e-6:
                    xs=max(st+ad,carrier_end-visible_dd)
                e['preset_entry']={'name':'APPEAR_HIGH_SCALE','start_seconds':round(st,6),'duration_seconds':ad,
                                   'authority':'FINAL_PARTITION_CARRIER_REVEAL_FALLBACK'}
                e['preset_actions']=[]
                e['preset_exit']={'name':'DISAPPEAR_DOWN_SCALE','start_seconds':round(xs,6),'duration_seconds':dd,
                                  'authority':'FINAL_PARTITION_CARRIER_REVEAL_FALLBACK'}
                e['start_seconds']=round(st,6);e['settle_seconds']=round(st+ad,6);e['end_seconds']=round(carrier_end,6)
                e['appearance_method']='SCALE_POP';e['disappearance_method']='PRESET_DISAPPEARANCE'
                e['position_animated']=False;e['entry_direction']=None
                e['foundation_motion_decision']='REVEAL_ONLY'
                e['final_partition_motion_fallback']='MOTION_ENVELOPE_OUTSIDE_CARRIER'
                intervals,motion_start,motion_end=_compile_final_motion_intervals(e)
                e['motion_intervals']=intervals;e['motion_start_seconds']=round(motion_start,6);e['motion_end_seconds']=round(motion_end,6)
                motion_escapes=False
            if motion_escapes and e.get('render_mode')!='RESIDUAL_SUPPORT':
                raise ValueError(f"{e.get('event_id')}: motion lifetime cannot fit certified partition carrier")
            if e.get('render_mode')=='RESIDUAL_SUPPORT':
                # Residual reconstruction is physical source preservation, not
                # an actor. The renderer keeps it static for the whole carrier,
                # so the final plan must not retain fake appearance/exit motion.
                e['preset_entry']=None;e['preset_exit']=None;e['preset_actions']=[]
                e['start_seconds']=round(carrier_start,6);e['settle_seconds']=round(carrier_start,6);e['end_seconds']=round(carrier_end,6)
                e['motion_start_seconds']=round(carrier_start,6);e['motion_end_seconds']=round(carrier_start,6);e['motion_intervals']=[]
                e['appearance_method']='STATIC_SUPPORT';e['disappearance_method']='STATIC_SUPPORT'
                e['independent_motion_allowed']=False
                e['position_animated']=False
                e['final_lifetime_authority']='FOUNDATION_STATIC_RESIDUAL_CARRIER'
        stats['partition_group_count']+=1
        stats['partition_member_count']+=len(members)
    handoff_stats=_reconcile_final_partition_handoffs(events,cards,fps)
    stats['partition_handoff_repair']=handoff_stats
    return stats


def _hierarchical_render_metadata(unit:dict)->dict:
    return {
        'render_mode':unit.get('render_mode','ROOT_ATOMIC'),
        'partition_root_id':unit.get('partition_root_id') or unit.get('root_id'),
        'partition_complete':bool(unit.get('partition_complete')),
        'independent_motion_allowed':bool(unit.get('independent_motion_allowed',True)),
        'source_layer_path':unit.get('layer_path') or unit.get('mask_path'),
        'foundation_residual_support':bool(unit.get('foundation_residual_support')),
        'animation_mode':unit.get('animation_mode'),
        'translation_safe_after_occlusion':bool(unit.get('translation_safe_after_occlusion',unit.get('animation_safe',True))),
    }

def _schedule_event(e:dict, phase_window:tuple[float,float], card:dict, index:int, total:int, *, force_static:bool=False, local_events:list[dict]|None=None, fps:float=30.0):
    """Schedule one already collision-solved object using only user preset families."""
    ps,pe=phase_window;card_end=float(card['end_seconds']);primary=str(e.get('attention_priority') or '').upper()=='PRIMARY'
    center=e.get('card_rest_position_norm') or [0.5,0.5];dur=max(0.05,pe-ps)
    # voice-aligned appearance start; preserve the phase grammar as the hard envelope
    hit=_clamp(float(e.get('perceptual_hit_seconds',ps+dur*.45)),ps+0.20,pe-0.20)
    appearance='APPEAR_HIGH_SCALE';ad=preset_duration(appearance);dd=preset_duration('DISAPPEAR_DOWN_SCALE')
    exact_middle=abs(float(center[0])-0.5)<0.025 and abs(float(center[1])-0.5)<0.035
    room_for_entry=dur>=preset_duration('ENTRY_LEFT_TO_MIDDLE')+0.72
    # Position-entry presets have a literal MIDDLE settled endpoint.  Snapping a
    # near-middle solved object to that endpoint is a geometry change, so it must
    # reuse the solver's 112% motion envelope before becoming committed state.
    middle_candidate=candidate_middle_envelope_geometry(e)
    foundation_approved=e.get('foundation_motion_decision')=='APPROVED_POSITION_ENTRY'
    use_position_entry=bool(not force_static and room_for_entry and middle_candidate.get('safe') and not e.get('composite_atomic') and (foundation_approved or (total>1 and primary and exact_middle and not e.get('relationship_source_requested'))))
    pn=pd=st=None
    if use_position_entry:
        pn=choose_entry_for_center(float(e.get('source_center_norm',[0.5,0.5])[0]));pd=preset_duration(pn);st=max(ps,min(hit-pd*.90,pe-pd-0.62));st=max(ps+0.02,st)
        if total==1:st=ps
        if local_events:
            snap=copy.deepcopy(e)
            e['card_rest_position_norm']=middle_candidate['center_norm']
            e['planned_rect_norm']=middle_candidate['rect_norm']
            e['collision_envelope_rect_norm']=list(middle_candidate['rect_norm'])
            e['layout_scale_multiplier']=middle_candidate['scale']
            e['preset_entry']={'name':pn,'start_seconds':round(st,6),'duration_seconds':pd,'authority':'USER_PRFPSET_ENTRY_EXIT__V31_SAFE_CENTER'}
            e['preset_actions']=[]
            e['start_seconds']=round(st,6)
            rows=card_motion_conflicts(local_events,float(card.get('start_seconds',ps)),float(card.get('end_seconds',card_end)),fps)
            e.clear();e.update(snap)
            if any(str(r.get('event_a'))==str(e.get('event_id')) or str(r.get('event_b'))==str(e.get('event_id')) for r in rows):
                use_position_entry=False
    if use_position_entry:
        e['card_rest_position_norm']=middle_candidate['center_norm']
        e['planned_rect_norm']=middle_candidate['rect_norm']
        e['collision_envelope_rect_norm']=list(middle_candidate['rect_norm'])
        e['layout_scale_multiplier']=middle_candidate['scale']
        e['preset_entry']={'name':pn,'start_seconds':round(st,6),'duration_seconds':pd,'authority':'USER_PRFPSET_ENTRY_EXIT__V31_SAFE_CENTER'}
        e['appearance_method']='POSITION_ENTRY';e['entry_direction']='LEFT' if 'LEFT' in pn else 'RIGHT';e['position_animated']=True;e['settle_seconds']=round(st+pd,6)
        # Position exits are used only when this is the sole independent object in the visual
        # sentence. With supports/other primaries, disappearance is safer: a fixed MIDDLE->OUT
        # path can sweep through another valid object even when both settled layouts are clean.
        if total==1 and not foundation_approved:
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
    # Physical existence is owned by the semantic phase. Motion presets are a
    # separate, bounded interval and may never retire the source composition.
    e['physical_start_seconds']=round(ps,6);e['physical_end_seconds']=round(pe,6)
    e['motion_start_seconds']=e.get('start_seconds');e['motion_end_seconds']=e.get('end_seconds')
    e['motion_intervals']=[dict(kind='ENTRY',**e['preset_entry'])] if e.get('preset_entry') else []
    e['motion_intervals'] += [dict(kind='ACTION',**a) for a in (e.get('preset_actions') or [])]
    if e.get('preset_exit'):e['motion_intervals'].append(dict(kind='EXIT',**e['preset_exit']))
    e['visual_carrier_id']=f"{e.get('visual_card_id')}::{e.get('scene_id')}::{e.get('partition_root_id') or e.get('event_id')}"
    e['visual_carrier_role']='FOUNDATION_STATIC_SUPPORT' if e.get('render_mode')=='RESIDUAL_SUPPORT' else ('FOUNDATION_PARTITION_MEMBER' if e.get('render_mode')=='CHILD_PARTITION' else 'SOURCE_VISUAL')
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
    # Never resolve geometry by shortening a source carrier. The static/reveal
    # recovery above is the final safe fallback; unresolved topology must fail.
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
        units,hierarchy_selection=_select_render_units(vr)
        camera_fit=compute_reference_camera_fit(float(vr.get('foreground_fraction') or 0.0),units,ref);camera_fit['camera_scale']=max(0.68,min(1.15,float(camera_fit.get('camera_scale') or 1.0)));camera_fit['expected_occupancy_percent']=float(camera_fit.get('source_occupancy_percent') or 0.0)*camera_fit['camera_scale']**2
        scene_events=[]
        for u in units:
            sem=sems.get(str(u.get('semantic_unit_id'))) or {};primary=bool(u.get('partition_primary_member')) if u.get('render_mode')=='CHILD_PARTITION' else is_primary_semantic(u);cx,cy=map(float,u.get('center_norm') or [0.5,0.5]);trig=sem.get('appear_trigger') or sem.get('focus_trigger');hit=_word_time(trig,alignment,st,False)
            hit_source='VOICE_TRIGGER'
            if hit is None:
                hit=(float(st['start'])+float(st['end']))/2.0;hit_source='SOURCE_INTERVAL_FALLBACK'
            e={
                'event_id':f'{sid}_{u["physical_id"]}','scene_id':sid,'visual_card_id':card['card_id'],'physical_id':u['physical_id'],'semantic_unit_id':u.get('semantic_unit_id'),'semantic_scope_id':f"{sid}::{u.get('semantic_unit_id')}" if u.get('semantic_unit_id') else f"{sid}::{u['physical_id']}",'semantic_type':u.get('semantic_type'),'semantic_role':u.get('semantic_role'),'kind':_kind(u),'identity_key':_identity(sem,u),
                'narrative_function':sem.get('narrative_function'),'semantic_intent':sem.get('semantic_intent'),'relationship':sem.get('relationship'),'visual_concept':sem.get('visual_concept'),'canonical_clause':(scene.get('script_span') or {}).get('text') or scene.get('narration') or '',
                'source_scene_start_seconds':float(st['start']),'source_scene_end_seconds':float(st['end']),'source_center_norm':[cx,cy],'source_bbox_norm':u.get('bbox_norm'),'source_grouped_detail_count':int(u.get('grouped_detail_count') or ((vr.get('grouped_detail_count') or (vr.get('artifacts') or {}).get('grouped_detail_count') or 0) if len(units)==1 else 0)),
                'start_seconds':float(st['start']),'perceptual_hit_seconds':round(hit,6),'perceptual_hit_source':hit_source,'settle_seconds':float(st['end']),'end_seconds':float(st['end']),'preset_entry':None,'preset_exit':None,'preset_actions':[],
                'appearance_method':None,'disappearance_method':None,'entry_direction':None,'position_animated':False,'position_min_frames':12,'position_interpolation':'USER_PRESET_CURVE','motion_profile':'USER_VISUAL_SAMPLE_AUTHORITY','motion_blur_enabled':False,'preset_coordinate_mode':'ABSOLUTE_OBJECT_CENTER',
                'start_x_norm':cx,'start_y_norm':cy,'end_x_norm':cx,'end_y_norm':cy,'exit_x_norm':cx,'exit_y_norm':cy,'focus_beats':[],'story_actions':[],'story_beats':[],'continuous_drift':False,'continuous_image_scale':False,
                'reference_camera_scale':float(camera_fit['camera_scale']),'layout_scale_multiplier':1.0,'hierarchy_level':int(u.get('hierarchy_level') or 0),'parent_semantic_unit_id':u.get('parent_semantic_unit_id'),'composition_slot_id':u.get('composition_slot_id') or u.get('semantic_unit_id') or u.get('physical_id'),'fifth_element_overlay':False,
                **_hierarchical_render_metadata(u),'reveal_safe':bool(u.get('reveal_safe',True)),'animation_safe':bool(u.get('animation_safe',True)),'matting':u.get('matting'),'semantic_mapping_confidence':float(u.get('semantic_mapping_confidence',0.0)),'cutout_policy':'TOP_LEVEL_SEMANTIC_GROUP_ONLY__PRESERVE_ATTACHED_DETAILS','relationship_motion_policy':'EXPLICIT_METADATA_ONLY__UNSAFE_TRAVEL_BECOMES_TEMPORAL_HANDOFF','attention_priority':'PRIMARY' if primary else 'SUPPORTING','motion_energy':'HIGH' if primary else 'MEDIUM','budget_cost':0.25 if primary else 0.12,
            }
            e['composite_atomic']=_event_is_atomic(e);events.append(e);scene_events.append(e)
        scenes_out.append({'scene_id':sid,'start_seconds':float(st['start']),'end_seconds':float(st['end']),'duration_seconds':float(st['end'])-float(st['start']),'duration_class':'CARD_MEMBER','vision_mode':vr.get('mode'),'choreography_profile':'V31_0_25_PREMIUM_MOTION_LANGUAGE','relation_to_previous':_relation(scene),'transition':{'mode':'OBJECT_PRESETS_ONLY__NO_FRAME_BLEND','duration_seconds':0.0,'white_reset':False,'relation':_relation(scene),'profile':'V31_0_25_PREMIUM_MOTION_LANGUAGE','energy_cost':0.0,'strong':False},'visual_card_id':card['card_id'],'reference_camera_fit':camera_fit,'event_ids':[e['event_id'] for e in scene_events],'internal_change_count':len(scene_events),'semantic_focus_count':0,'story_beat_count':0,'story_action_count':0,'physical_story_action_count':0,'max_story_gap_seconds':min(1.4,float(card['duration_seconds'])),'hierarchical_motion_unit_count':hierarchy_selection['hierarchical_motion_unit_count'],'hierarchy_render_selection':hierarchy_selection,'composition_slot_count':len(set(str(e.get('composition_slot_id')) for e in scene_events)),'short_beat':False,'motion_budget':{'budget_points':10.0,'duration_class':'CARD_MEMBER'},'estimated_motion_cost':sum(e['budget_cost'] for e in scene_events),'budget_utilization':0.0})

    # Semantic card repartition: preserve the locked legal 3–5 second card
    # intervals, but assign each required event to the interval containing its
    # voice anchor. A source scene may straddle an editorial boundary; its
    # physical state must follow the anchor rather than an obsolete scene map.
    ordered_cards=cards['cards']
    def _target_card_for_anchor(hit):
        target=next((c for c in ordered_cards if float(c['start_seconds'])-1e-6<=hit<float(c['end_seconds'])-1e-6),None)
        if target is None and ordered_cards:
            target=min(ordered_cards,key=lambda c:min(abs(hit-float(c['start_seconds'])),abs(hit-float(c['end_seconds']))))
        return target
    # Certified Foundation partitions are one source visual. Card ownership is
    # therefore group-owned even when individual children have staggered voice
    # anchors. Splitting children of one reconstruction across cards creates a
    # partial source state and invalid carrier lifetimes.
    partition_groups={}
    for e in events:
        if e.get('render_mode') in {'CHILD_PARTITION','RESIDUAL_SUPPORT'}:
            key=(str(e.get('scene_id')),str(e.get('partition_root_id')))
            partition_groups.setdefault(key,[]).append(e)
    assigned_partition_ids=set()
    for members in partition_groups.values():
        focus=next((e for e in members if str(e.get('attention_priority') or '').upper()=='PRIMARY'),None)
        if focus is None:
            focus=min(members,key=lambda e:(float(e.get('perceptual_hit_seconds',e.get('source_scene_start_seconds',0))),str(e.get('event_id'))))
        hit=float(focus.get('perceptual_hit_seconds',focus.get('source_scene_start_seconds',0)))
        target=_target_card_for_anchor(hit)
        if target:
            for e in members:
                assigned_partition_ids.add(str(e.get('event_id')))
                if e.get('visual_card_id')!=target['card_id']:
                    e['repartitioned_from_visual_card_id']=e.get('visual_card_id')
                    e['visual_card_id']=target['card_id']
                    e['card_repartition_strategy']='FOUNDATION_PARTITION_GROUP_ANCHOR'
                if e.get('scene_id') not in target.get('source_scene_ids',[]):
                    target.setdefault('source_scene_ids',[]).append(e.get('scene_id'))
    for e in events:
        if str(e.get('event_id')) in assigned_partition_ids:
            continue
        hit=float(e.get('perceptual_hit_seconds',e.get('source_scene_start_seconds',0)))
        target=_target_card_for_anchor(hit)
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
                    if e.get('render_mode') in {'CHILD_PARTITION','RESIDUAL_SUPPORT'}:
                        # Never solve density by deleting certified source pixels.
                        # Keep the full partition; the subsequent layout/static
                        # fallback must either fit it or fail safely.
                        e['partition_suppression_blocked']='CERTIFIED_SOURCE_SURVIVAL_ATOMICITY'
                        continue
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
        foundation_contract=_plan_foundation_partition_choreography(selected_events,phase_plan)
        for e in selected_events:
            window=_phase_for_event(phase_plan,e['event_id'])
            if window:_schedule_event(e,window,card,selected_events.index(e),len(selected_events),force_static=not bool(e.get('independent_motion_allowed',True)),local_events=selected_events,fps=fps)
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
                if window:_schedule_event(e,window,card,selected_events.index(e),len(selected_events),force_static=True,local_events=selected_events,fps=fps)
            card['semantic_phase_repartition']={'detected_conflicts':len(pre_conflicts),'resolved_by_internal_phase_split':len(pre_conflicts),'cards_split':0}
        relationship_resolutions=_safe_relationship_motion(card,selected_events,rels)
        relationship_resolutions=_recover_trajectory_conflicts(card,selected_events,phase_plan,relationship_resolutions,fps)
        for zi,e in enumerate(sorted(selected_events,key=lambda x:(0 if x.get('attention_priority')!='PRIMARY' else 1,1 if 'CHARACTER' in str(x.get('semantic_type') or '') else 0,str(x.get('event_id')))),2):
            e['z_order']=zi;e['visibility_interval_seconds']=[e.get('physical_start_seconds',e.get('start_seconds')),e.get('physical_end_seconds',e.get('end_seconds'))]
            e['collision_envelope_rect_norm']=e.get('planned_rect_norm')
        card['universal_scene_grammar']=grammar;card['story_phase_plan']=phase_plan;card['constraint_layout']=layout;card['relationship_resolutions']=relationship_resolutions;card['foundation_partition_motion_contract']=foundation_contract
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
    segment_stats=_solve_semantic_segments(events,cards,fps)
    readable_hold_stats=_commit_readable_state_holds(events,cards,fps)
    recomposition_stats=_recomposition_optimize(events,cards,fps)
    optical_scale_stats=_optical_scale_optimize(events,cards,fps)
    spatial_choreography_stats=_spatial_choreography_optimize(events,cards,fps)
    for e in events:
        e['visual_affordance']=classify_affordance(e);e['visual_affordance_operations']=list(legal_operations(e['visual_affordance']))
    semantic_visual_sentences=SemanticVisualSentenceCompiler().compile(events)
    beat_choreography=BeatChoreographyCompiler().compile(events,semantic_visual_sentences.get('sentences') or [])
    editorial_motion_grammar=EditorialMotionGrammarDirector().direct(events)
    pacing_diagnostics=PacingDirector().plan(events,alignment,fps)
    character_director=SemanticCharacterDirector().direct(events)
    # This must run after all entry/exit selection and after bounded editorial
    # constraints. The exact animated envelope is its authority.
    effect_variety_stats=_effect_variety_director(events,cards,fps)
    continuity_planning=VisualContinuityQA().repair_once(events,cards)
    # Final semantic timing ownership starts here.  Every pass above may alter
    # entry selection, lifecycle, geometry, or trajectories; none below may.
    cross_card_stats=_cross_card_handoff_optimize(events,cards,fps)
    atomic_stats=_atomic_handoff_optimize(events,cards,fps)
    final_secondary_geometry=_finalize_secondary_character_geometry(events)
    final_physical_certification=_final_physical_certification(events,cards,fps)
    final_lifetime_commit=_finalize_visual_lifetimes(events,cards,fps)
    from hexa_v31.composition_qa import composition_plan_qa
    final_composition_qa=composition_plan_qa({'events':events,'visual_cards':cards,'fps':fps})
    # This is intentionally retained as an authoritative final-plan record.
    # Pipeline hard QA consumes the same committed state after the audit; do
    # not replace that gate with a planner exception for unrelated fixtures.
    sync_qa=perceptual_sync_qa(events,fps)
    # Final continuity is an observer of the exact committed timeline.  It
    # runs after every optimizer and is deliberately read-only.
    visual_continuity_qa=VisualContinuityQA().assess({'events':events,'visual_cards':cards})
    hierarchical_count=sum(1 for e in events if int(e.get('hierarchy_level') or 0)>0 and not e.get('suppressed_by_card_density'))
    out={'schema':'HEXA_MOTION_PLAN_V31','version':'31.0.25','fps':fps,'project_id':plan.get('project_id'),'rules_authority':'USER_UPLOADED_RULES_PDF','reference_authority':ref.get('authority_id'),'preset_authority':'HEXA_USER_PRESET_AUTHORITY_V31','timing_method':alignment.get('method'),'scenes':scenes_out,'events':events,'visual_cards':cards,'atomic_handoff_optimizer':atomic_stats,'cross_card_handoff_optimizer':cross_card_stats,'motion_dna_version':'HEXA_MOTION_DNA_V31_0_25_PREMIUM_MOTION_LANGUAGE','continuity_summary':{'scene_count':len(scenes_out),'visual_card_count':len(cards['cards']),'transition_modes':['OBJECT_PRESETS_ONLY__NO_FRAME_BLEND'],'appearance_methods':sorted(set(e.get('appearance_method') for e in events if e.get('appearance_method'))),'strong_transition_count':0,'identity_persistence_count':sum(1 for e in events if len(e.get('persistent_source_scene_ids') or [])>1),'white_reset_scene_percent':0.0},'budget_summary':{'story_action_count':sum(len(e.get('preset_actions') or []) for e in events),'choreography_action_count':sum(2+len(e.get('preset_actions') or []) for e in events if not e.get('suppressed_by_card_density')),'story_sources':['UNIVERSAL_SCENE_GRAMMAR','EXPLICIT_SEMANTIC_RELATIONSHIPS','SPATIOTEMPORAL_FEASIBILITY_SOLVER','ATOMIC_HANDOFF_TIMING_OPTIMIZER','CROSS_CARD_HANDOFF_CONSTRAINT_SOLVER','READABLE_STATE_LIFECYCLE_COMPILER','DETERMINISTIC_EFFECT_VARIETY_DIRECTOR','TYPOGRAPHY_MOTION_UNITS'],'hierarchical_motion_unit_count':hierarchical_count,'inferred_causal_edge_count':0,'actionable_story_edge_count':sum(1 for c in cards['cards'] for r in c.get('relationship_resolutions') or [] if r.get('mode')=='WITHIN_FRAME_PRESET'),'layout_choreography_action_count':sum(len(e.get('preset_actions') or []) for e in events),'story_eligible_scene_count':sum(1 for c in cards['cards'] if (c.get('universal_scene_grammar') or {}).get('explicit_edges'))},'hard_invariants':{'latest_user_rules_hard_authority':True,'user_prfpset_hard_authority':True,'user_visual_samples_hard_authority':True,'legacy_motion_heuristics_disabled':True,'speculative_subobject_cutouts_forbidden':True,'spatial_role_guessing_forbidden':True,'explicit_relationship_evidence_required':True,'layout_choreography_must_not_claim_semantic_relationship':True,'high_confidence_physical_semantic_mapping_required_for_relationship_motion':True,'visual_card_duration_seconds':[3.0,5.0],'primary_elements_per_card':[1,2],'primary_rule_interpretation':'MAX_CONCURRENT_VISIBLE_PRIMARY','secondary_elements_per_card':[3,8],'secondary_detail_count_may_remain_grouped_to_preserve_cutout_integrity':True,'entry_exit_primary_only':True,'within_frame_any_element':True,'appearance_prefer_secondary':True,'disappearance_any_element':True,'full_frame_crossfade_forbidden':True,'white_wash_forbidden':True,'mask_wipe_reveal_forbidden':True,'arbitrary_drift_forbidden':True,'arbitrary_diagonal_travel_forbidden':True,'auto_relationship_arrow_forbidden':True,'allowed_preset_names':sorted((preset_authority().get('preset_motion') or {}).keys()),'position_interpolation':'USER_VISUAL_SAMPLE_CURVES','position_motion_profile':'USER_PRFPSET_ENDPOINTS_PLUS_PHYSICAL_SAMPLE_TIMING','card_layout_policy':'DENSITY_AWARE_PHASE_SOLVER__CERTIFIED_HIERARCHY_PARTITION','topic_specific_motion_hardcoding_forbidden':True,'universal_content_type_classifier':True,'joint_story_layout_motion_planning':True}}
    visual_instances,semantic_events=_compile_visual_instances(events,scenes_out)
    out['visual_instances']=visual_instances;out['semantic_events']=semantic_events
    out['foundation_partition_motion_contract']=_foundation_partition_motion_contract(events)
    out['semantic_segment_solver']=segment_stats
    out['readable_state_hold_optimizer']=readable_hold_stats
    out['premium_recomposition_optimizer']=recomposition_stats
    out['effect_variety_director']=effect_variety_stats
    out['editorial_motion_grammar_director']=editorial_motion_grammar
    out['semantic_visual_sentence_compiler']=semantic_visual_sentences
    out['visual_affordance_graph']={'version':'HEXA_VISUAL_AFFORDANCE_GRAPH_V1','classes':{k:sum(1 for e in events if e.get('visual_affordance')==k) for k in ('ROOT_ATOMIC','DETACHED_TRANSLATABLE','CONNECTED_REVEAL_ONLY','CONNECTED_LOCAL_EMPHASIS','ARTICULATED_SUBOBJECT','CONTEXT_RESIDUAL')},'consumed_by_planner':True}
    out['beat_choreography_compiler']=beat_choreography
    out['pacing_director']=pacing_diagnostics
    out['semantic_character_director']=character_director
    out['continuity_planning_repair']=continuity_planning
    out['visual_continuity_qa']=visual_continuity_qa
    out['perceptual_sync_qa']=sync_qa
    out['final_semantic_timing_composition_qa']=final_composition_qa
    out['final_secondary_character_geometry_event_ids']=final_secondary_geometry
    out['final_physical_certification']=final_physical_certification
    out['final_lifetime_commit']=final_lifetime_commit
    out['premium_optical_scale_optimizer']=optical_scale_stats
    out['premium_spatial_choreography_optimizer']=spatial_choreography_stats
    out['instance_metrics']={'visual_instances_total':len(visual_instances),'semantic_events_total':len(semantic_events),'persistent_instances_total':sum(1 for x in visual_instances if len((x.get('persistence_source_evidence') or {}).get('source_states') or [])>1),'duplicate_same_identity_overlap_count':0,'illegal_persistence_count':0,'logical_instance_reentry_without_source_reset':0,**lifetime_stats}
    if logger:logger.log('PASS','MOTION_PLAN_BUILT',event_count=len(events),scene_count=len(scenes_out),visual_cards=len(cards['cards']),fps=fps,motion_dna=out['motion_dna_version'],story_actions=out['budget_summary']['story_action_count'],choreography_actions=out['budget_summary']['choreography_action_count'],suppressed_events=sum(1 for e in events if e.get('suppressed_by_card_density')),subobject_cutouts=0)
    return out
