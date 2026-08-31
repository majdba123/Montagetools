from __future__ import annotations

"""Read-only premium choreography diagnostics over one committed plan."""

from dataclasses import dataclass, asdict
import statistics
from .composition_qa import _state
from .preset_authority import preset as preset_def


@dataclass(frozen=True)
class MotionUnit:
    motion_unit_id: str
    source_event_id: str
    visual_instance_id: str
    semantic_role: str
    semantic_type: str
    start_seconds: float
    readable_start_seconds: float
    readable_end_seconds: float
    end_seconds: float
    placement: tuple[float, float]
    scale: float
    entry_preset: str | None
    exit_preset: str | None
    relationship_count: int
    source_backed: bool = True


@dataclass(frozen=True)
class TypographyUnit:
    typography_unit_id: str
    source_text_id: str
    source_unit_id: str | None
    semantic_source: str
    style: str
    hierarchy_level: str
    text: str
    start_seconds: float
    end_seconds: float
    placement_slot: str
    source_backed: bool = True


def _family(row):
    name=str((row or {}).get('name') or '')
    return str((preset_def(name) if name else {}).get('family') or '')


def build_motion_units(motion_plan:dict)->list[dict]:
    rows=[]
    for e in motion_plan.get('events') or []:
        if e.get('suppressed_by_card_density'):continue
        st=float(e.get('start_seconds',0));en=float(e.get('end_seconds',st));entry=e.get('preset_entry') or {};exit_=e.get('preset_exit') or {}
        hit=float(e.get('perceptual_hit_seconds',st+float(entry.get('duration_seconds') or 0)))
        readable_end=float(exit_.get('start_seconds',en)) if exit_ else en
        pos=e.get('card_rest_position_norm') or [0.5,0.5]
        rows.append(asdict(MotionUnit(
            motion_unit_id='MU_'+str(e.get('event_id')),source_event_id=str(e.get('event_id')),
            visual_instance_id=str(e.get('visual_instance_id') or e.get('physical_id') or e.get('event_id')),
            semantic_role=str(e.get('attention_priority') or e.get('semantic_role') or 'SUPPORTING'),semantic_type=str(e.get('semantic_type') or 'OBJECT'),
            start_seconds=round(st,6),readable_start_seconds=round(max(st,hit),6),readable_end_seconds=round(min(en,max(hit,readable_end)),6),end_seconds=round(en,6),
            placement=(round(float(pos[0]),6),round(float(pos[1]),6)),scale=round(float(e.get('layout_scale_multiplier') or 1.0),6),
            entry_preset=str(entry.get('name')) if entry.get('name') else None,exit_preset=str(exit_.get('name')) if exit_.get('name') else None,
            relationship_count=len(e.get('preset_actions') or []))))
    return rows


def build_typography_units(text_plan:dict)->list[dict]:
    levels={'NUMERIC_HERO':'A','STATUS_BADGE':'A','RESULT_FOCUS':'A','CONTRAST_LABEL':'B','KEY_TERM':'B','MICRO_LABEL':'C'}
    out=[]
    for e in text_plan.get('events') or []:
        style=str(e.get('style') or 'KEY_TERM')
        out.append(asdict(TypographyUnit(
            typography_unit_id='TU_'+str(e.get('text_id')),source_text_id=str(e.get('text_id')),source_unit_id=str(e.get('unit_id')) if e.get('unit_id') else None,
            semantic_source=str(e.get('semantic_source') or ''),style=style,hierarchy_level=levels.get(style,'B'),text=str(e.get('text') or ''),
            start_seconds=round(float(e.get('start_seconds',0)),6),end_seconds=round(float(e.get('end_seconds',0)),6),placement_slot=str(e.get('slot') or ''))))
    return out


def _event_transition(e):
    entry=e.get('preset_entry') or {};exit_=e.get('preset_exit') or {}
    if e.get('preset_actions'):return 'WITHIN_FRAME_MOVE'
    if e.get('focus_beats') and not entry:return 'BEAT_FOCUS_PERSISTENCE'
    if _family(entry)=='ENTRY_EXIT':return 'SPATIAL_ENTRY'
    if _family(entry)=='APPEARANCE':return 'SCALE_REVEAL' if 'SCALE' in str(entry.get('name') or '') else 'FADE_ONLY'
    if _family(exit_)=='ENTRY_EXIT':return 'SPATIAL_EXIT'
    if _family(exit_)=='DISAPPEARANCE' and any(abs(float(x))>.01 for x in (preset_def(str(exit_.get('name') or '')).get('position_delta_norm') or [])):return 'SPATIAL_EXIT'
    return 'FADE_ONLY'


def build_visual_choreography_report(motion_plan:dict,text_plan:dict,sample_step:float=.10)->dict:
    motion_units=build_motion_units(motion_plan);typography_units=build_typography_units(text_plan)
    events=[e for e in motion_plan.get('events') or [] if not e.get('suppressed_by_card_density')];cards=list((motion_plan.get('visual_cards') or {}).get('cards') or [])
    classes={};progressive=handoffs=recompositions=full_resets=static_risk=low_impact=0;optical=[];primary_scales=[];archetypes=[];card_rows=[]
    for e in events:
        k=_event_transition(e);classes[k]=classes.get(k,0)+1
        recompositions+=int(bool(e.get('preset_actions') or e.get('focus_beats')))
        if str(e.get('attention_priority') or '').upper()=='PRIMARY':primary_scales.append(float(e.get('layout_scale_multiplier') or 1.0))
    for idx,c in enumerate(cards):
        cs=float(c.get('start_seconds',0));ce=float(c.get('end_seconds',cs));evs=[e for e in events if float(e.get('start_seconds',0))<ce and float(e.get('end_seconds',0))>cs]
        arch=str((c.get('universal_scene_grammar') or {}).get('archetype') or 'UNKNOWN');variant=str(c.get('composition_history_variant') or 'CANONICAL');signature=arch+':'+variant;archetypes.append(signature)
        hits=sorted({round(float(e.get('perceptual_hit_seconds',e.get('start_seconds',0))),3) for e in evs});progressive_here=max(0,len(hits)-1);progressive+=progressive_here
        entries=[float(e.get('start_seconds',0)) for e in evs];risk=bool(len(entries)>=2 and max(entries)-min(entries)<=.18 and not any(e.get('preset_actions') for e in evs) and len(hits)<=1);static_risk+=int(risk)
        impacts=[];t=cs
        while t<ce-1e-9:
            mass=dominant=0.0
            for e in evs:
                s=_state(e,t)
                if not s or s[2]<=.08:continue
                r=s[3];fill=float((e.get('matting') or {}).get('opaque_foreground_fraction') or .62);value=max(.0,float(r[2])*float(r[3])*max(.12,min(1.,fill))*float(s[2]));mass+=value
                if str(e.get('attention_priority') or '').upper()=='PRIMARY':dominant=max(dominant,value)
            score=min(1.,mass/.22)*.55+min(1.,dominant/.105)*.45;impacts.append(score);optical.append(score);t+=sample_step
        med=statistics.median(impacts) if impacts else 0.0;weak=med<.36;low_impact+=int(weak)
        card_rows.append({'card_id':c.get('card_id'),'archetype':arch,'composition_variant':variant,'composition_signature':signature,'motion_unit_count':len(evs),'independent_perceptual_beats':len(hits),'progressive_reveal_count':progressive_here,'static_poster_risk':risk,'median_optical_impact':round(med,6),'low_optical_impact':weak})
        if idx:
            before=[e for e in events if float(e.get('start_seconds',0))<cs and float(e.get('end_seconds',0))>=cs-.04];after=[e for e in events if float(e.get('start_seconds',0))<=cs+.04 and float(e.get('end_seconds',0))>cs]
            ids=lambda rows:{str(e.get('visual_instance_id') or e.get('physical_id') or e.get('event_id')) for e in rows}
            if ids(before)&ids(after):handoffs+=1
            elif not before or not after:full_resets+=1
    repeats=sum(1 for i in range(2,len(archetypes)) if archetypes[i]==archetypes[i-1]==archetypes[i-2]);opportunities=int(text_plan.get('opportunity_count') or len(typography_units));used=len(typography_units)
    action_families={};effect_sequence=[]
    for e in events:
        entry=e.get('preset_entry') or {};exit_=e.get('preset_exit') or {}
        if entry.get('name'):action_families[_event_transition(e)]=action_families.get(_event_transition(e),0)+1;effect_sequence.append((float(entry.get('start_seconds',e.get('start_seconds',0))),str(entry.get('name'))))
        for a in e.get('preset_actions') or []:
            n=str(a.get('name') or ''); action_families['WITHIN_FRAME_MOVE']=action_families.get('WITHIN_FRAME_MOVE',0)+1;effect_sequence.append((float(a.get('start_seconds',0)),n))
        for fb in e.get('focus_beats') or []:action_families['BEAT_FOCUS_EMPHASIS']=action_families.get('BEAT_FOCUS_EMPHASIS',0)+1;effect_sequence.append((float(fb.get('start_seconds',0)),'BEAT_FOCUS_EMPHASIS'))
        if exit_.get('name'):action_families['SPATIAL_EXIT' if _family(exit_)=='ENTRY_EXIT' else 'DISAPPEARANCE']=action_families.get('SPATIAL_EXIT' if _family(exit_)=='ENTRY_EXIT' else 'DISAPPEARANCE',0)+1;effect_sequence.append((float(exit_.get('start_seconds',e.get('end_seconds',0))),str(exit_.get('name'))))
    return {'schema':'HEXA_V31_PREMIUM_VISUAL_CHOREOGRAPHY_REPORT','version':'31.0.25','policy':'READ_ONLY__COMMITTED_PLAN__NO_SEMANTIC_CREDIT','independent_motion_unit_count':len(motion_units),'motion_units':motion_units,
        'typography_unit_count':used,'typography_units':typography_units,'available_viewer_text_opportunities':opportunities,'used_viewer_text_opportunities':used,'text_utilization_ratio':round(used/max(1,opportunities),6),
        'transition_classification_counts':classes,'fade_only_transition_count':classes.get('FADE_ONLY',0),'full_state_reset_count':full_resets,'progressive_reveal_count':progressive,'handoff_count':handoffs,
        'within_frame_recomposition_count':recompositions,'static_poster_risk_count':static_risk,'low_optical_impact_count':low_impact,'median_optical_impact':round(statistics.median(optical) if optical else 0.0,6),
        'average_primary_optical_scale':round(statistics.mean(primary_scales) if primary_scales else 0.0,6),'median_primary_optical_scale':round(statistics.median(primary_scales) if primary_scales else 0.0,6),
        'composition_archetypes_used':sorted(set(archetypes)),'composition_archetype_diversity':len(set(archetypes)),'three_card_archetype_repeat_count':repeats,'cards':card_rows,
        'effect_family_diversity':len(action_families),'within_frame_effect_families':action_families,'effect_sequence':[name for _,name in sorted(effect_sequence)],
        'hard_invariants':{'passive_semantic_credit':0,'semantic_timing_mutated':False,'geometry_mutated':False}}


def visual_choreography_qa(report:dict,pixel_metrics:dict,profile:dict)->dict:
    """Hard creative gate calibrated from the two locked physical references."""
    cards=list(report.get('cards') or []);duration=max(.001,float(pixel_metrics.get('duration_seconds',0)));transition_total=sum(int(v) for v in (report.get('transition_classification_counts') or {}).values())
    limits=profile.get('creative_quality_floor') or {}
    values={
        'static_poster_risk_ratio':float(report.get('static_poster_risk_count',0))/max(1,len(cards)),
        'low_optical_impact_ratio':float(report.get('low_optical_impact_count',0))/max(1,len(cards)),
        'fade_only_transition_ratio':float(report.get('fade_only_transition_count',0))/max(1,transition_total),
        'progressive_reveal_rate_per_minute':60.0*float(report.get('progressive_reveal_count',0))/duration,
        'meaningful_change_gap_p90_seconds':float(pixel_metrics.get('meaningful_change_gap_p90_seconds',999)),
        'effect_family_diversity':int(report.get('effect_family_diversity',0)),
        'within_frame_recomposition_rate_per_minute':60.0*float(report.get('within_frame_recomposition_count',0))/duration,
        'pixel_low_motion_percent':float(pixel_metrics.get('low_motion_percent',100)),
    }
    streak=0;run=0;last=None
    for name in report.get('effect_sequence') or []:
        name=str(name)
        run=run+1 if name==last else 1;last=name;streak=max(streak,run)
    values['consecutive_identical_preset_streak']=streak
    gates={}
    for name,value in values.items():
        rule=limits.get(name) or {}
        ok=(value>=float(rule.get('min',value)) and value<=float(rule.get('max',value)))
        gates[name]={'pass':bool(ok),'actual':round(value,6),'reference_calibrated_limit':rule}
    return {'schema':'HEXA_V31_VISUAL_CHOREOGRAPHY_QA','version':'1.0','pass':all(g['pass'] for g in gates.values()),'gates':gates,'reference_authority':profile.get('reference_authority')}
