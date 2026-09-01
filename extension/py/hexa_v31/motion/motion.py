from __future__ import annotations
import hashlib, pathlib
from typing import Any
from hexa_v31.util import read_json
from hexa_v31.motion_vocabulary import VOCABULARY, MOTION_DNA_ID, clamp_duration
from hexa_v31.story_graph import build_semantic_object_graph
from hexa_v31.story_state import build_story_state_machine
from hexa_v31.visual_sequence import build_visual_sequences
from hexa_v31.framing import compute_reference_camera_fit
from hexa_v31.motion_solver import schedule_around_hit

class MotionError(RuntimeError):
    pass


def _scene_timing_map(alignment: dict):
    return {str(x['scene_id']): x for x in (alignment.get('scene_timings') or [])}


def _unit_kind(u: dict):
    t = str(u.get('semantic_type') or '').upper()
    if t == 'MAIN_CHARACTER':
        return 'MAIN_NARRATOR'
    if t == 'SECONDARY_CHARACTER':
        return 'SECONDARY_CHARACTER'
    return 'VISUAL'


def _norm_relation(scene: dict) -> str:
    raw = str(scene.get('relation_to_previous') or '').strip().upper().replace(' ', '_').replace('-', '_')
    aliases = {
        '': 'UNSPECIFIED', 'START': 'START', 'CONTINUE': 'CONTINUE', 'CONTINUATION': 'CONTINUE', 'PERSIST': 'CONTINUE',
        'ADD': 'ADD', 'ADDITION': 'ADD', 'REVEAL': 'ADD', 'REPLACE': 'REPLACE', 'REFLOW': 'REFLOW',
        'COMPARE': 'COMPARE', 'COMPARISON': 'COMPARE', 'CAUSE_EFFECT': 'CAUSE_EFFECT', 'CAUSE/EFFECT': 'CAUSE_EFFECT',
        'RESOLVE': 'RESOLVE', 'RESOLUTION': 'RESOLVE', 'RESET': 'RESET', 'NEW': 'RESET', 'NEW_SCENE': 'RESET',
    }
    allowed = {'CONTINUE', 'ADD', 'REPLACE', 'REFLOW', 'COMPARE', 'CAUSE_EFFECT', 'RESOLVE', 'RESET', 'START'}
    return aliases.get(raw, raw if raw in allowed else 'UNSPECIFIED')


def _stable_choice(seed: str, items: list[str]) -> str:
    if not items:
        return ''
    h = int(hashlib.sha256(seed.encode('utf-8')).hexdigest()[:8], 16)
    return items[h % len(items)]


def _word_time(trigger: dict | None, alignment: dict, scene_timing: dict, prefer_end: bool = False) -> float | None:
    if not trigger:
        return None
    a = int(trigger.get('global_char_start', -1)); b = int(trigger.get('global_char_end', -1))
    if a < 0 or b < a:
        return None
    rows = alignment.get('word_timings') or []
    wr = [r for r in rows if int(r.get('char_end', -1)) > a and int(r.get('char_start', 10**9)) < b]
    if not wr:
        return None
    val = float(wr[-1].get('end', 0)) if prefer_end else float(wr[0].get('start', 0))
    return max(float(scene_timing['start']), min(float(scene_timing['end']), val))


def _char_fraction(trigger: dict | None, scene: dict) -> float | None:
    if not trigger:
        return None
    span = scene.get('script_span') or {}
    s = int(span.get('global_char_start', -1)); e = int(span.get('global_char_end', -1)); a = int(trigger.get('global_char_start', -1))
    if s < 0 or e <= s or a < s:
        return None
    return max(0.0, min(1.0, (a - s) / float(e - s)))


def _duration_class(duration: float) -> str:
    if duration < 0.75:
        return 'MICRO'
    if duration < 1.50:
        return 'SHORT'
    if duration < 3.00:
        return 'MEDIUM'
    if duration < 5.00:
        return 'LONG'
    return 'EXTENDED'


def _visual_progression_count(scene: dict) -> int:
    vp = scene.get('visual_progression') or []
    return len(vp) if isinstance(vp, list) else 0


def _scene_profile(scene: dict, vr: dict, duration: float) -> str:
    rel = _norm_relation(scene)
    units = scene.get('units') or []
    types = {str(u.get('type') or '').upper() for u in units}
    if duration < 0.95:
        return 'QUICK_CONTINUATION'
    if rel == 'COMPARE':
        return 'COMPARISON'
    if rel == 'CAUSE_EFFECT' or any(u.get('interaction_target') or u.get('relationship') for u in units):
        return 'CAUSE_FLOW'
    if rel == 'RESOLVE':
        return 'RESOLUTION'
    if types & {'UI', 'DEVICE', 'CARD'}:
        return 'INTERFACE_FOCUS'
    if types & {'PRICE', 'NUMBER', 'STATUS', 'LABEL'}:
        return 'DATA_EMPHASIS'
    if 'MAIN_CHARACTER' in types:
        return 'NARRATOR_EXPLAIN'
    if 'GROUP' in types or str(vr.get('mode')) == 'GROUPED_LAYERED':
        return 'SYSTEM_REVEAL'
    return 'OBJECT_STORY'


def _scene_budget(scene: dict, vr: dict, duration: float) -> dict[str, Any]:
    cls = _duration_class(duration)
    base = {'MICRO': 0.70, 'SHORT': 1.05, 'MEDIUM': 1.65, 'LONG': 2.15, 'EXTENDED': 2.55}[cls]
    units = list(vr.get('units') or [])
    n = len(units)
    primary = sum(1 for u in units if str(u.get('semantic_role') or '').upper() == 'PRIMARY')
    progression = _visual_progression_count(scene)
    # Dense scenes need less simultaneous animation; explicit visual progression earns a little room.
    density_penalty = max(0.0, (n - 2) * 0.16)
    grouped_penalty = 0.18 if str(vr.get('mode') or '') == 'GROUPED_LAYERED' else 0.0
    progression_bonus = min(0.35, max(0, progression - 1) * 0.10)
    budget = max(0.55, base - density_penalty - grouped_penalty + progression_bonus)
    return {
        'duration_class': cls,
        'budget_points': round(budget, 3),
        'unit_count': n,
        'primary_count': primary,
        'visual_progression_count': progression,
        'vision_mode': vr.get('mode'),
    }


def _transition(scene: dict, scene_index: int, duration: float, profile: str, fps: float, recent_strong_at: float | None, scene_start: float) -> dict:
    rel = _norm_relation(scene)
    frame = 1.0 / max(1.0, fps)
    if scene_index == 0:
        return {'mode': 'OPEN_WHITE', 'duration_seconds': round(max(3 * frame, min(5 * frame, duration * 0.12)), 6), 'white_reset': True, 'relation': rel, 'profile': profile, 'energy_cost': 0.35, 'strong': False}
    if rel == 'RESET':
        # A semantic reset clears objects on the stable white stage; it never dissolves
        # the whole frame through white. This removes the ghost/white-wash signature.
        frames=6 if duration>=0.75 else 4
        return {'mode':'OBJECT_RESET_6F','duration_seconds':round(frames*frame,6),'white_reset':False,'relation':rel,'profile':profile,'energy_cost':0.26,'strong':True,'transition_frames':frames}

    # V31 treats a boundary as punctuation, not as a mandatory animation event.
    # Continuations/additions mostly carry or dissolve over only 2-3 frames.
    # V31 uses short-but-smooth opacity handoffs instead of two-frame screen shocks.
    # These are boundary fades, not Position animations, so the PDF's 12-frame Position rule
    # does not apply. The duration is long enough to suppress isolated one-frame spikes while
    # remaining visually subordinate to object choreography.
    if rel in {'CONTINUE', 'UNSPECIFIED'}:
        mode = 'CARRY_BLEND_4F'; frames = 4
    elif rel in {'ADD', 'RESOLVE'}:
        mode = 'SOFT_MATCH_6F'; frames = 6
    elif rel in {'REPLACE', 'REFLOW', 'COMPARE', 'CAUSE_EFFECT'}:
        mode = 'SOFT_MATCH_8F'; frames = 8
    else:
        mode = 'CARRY_BLEND_4F'; frames = 4
    if duration < 0.70: frames=min(frames,4)
    strong=False
    cost = {'CARRY_BLEND_4F':0.12,'SOFT_MATCH_6F':0.18,'SOFT_MATCH_8F':0.22}[mode]
    return {'mode': mode, 'duration_seconds': round(frames * frame, 6), 'white_reset': False, 'relation': rel, 'profile': profile, 'energy_cost': cost, 'strong': strong, 'transition_frames': frames}


def _identity_key(sem:dict,u:dict)->str:
    name=str((sem or {}).get('semantic_name') or '').strip().upper()
    typ=str(u.get('semantic_type') or (sem or {}).get('type') or '').strip().upper()
    if not name or name in {'OBJECT','ICON','ITEM','ELEMENT'}: return ''
    return typ+'::'+name

def _entry_for_unit(u:dict, scene_duration:float, scene_index:int, vision_mode:str, profile:str, explicit_trigger:bool, motion_role:str='CONTEXT', persistent:bool=False):
    kind=_unit_kind(u);cx,cy=u['center_norm'];_,_,w,h=u['bbox_norm']
    animation_mode=str(u.get('animation_mode') or ('TRANSLATE_SAFE' if u.get('translation_safe_after_occlusion',u.get('animation_safe',True)) else 'GROUP_ONLY')).upper()
    role=str(u.get('semantic_role') or '').upper();typ=str(u.get('semantic_type') or '').upper();area=max(0.0,float(w)*float(h));cls=_duration_class(scene_duration)
    if persistent:
        return 'CONTINUATION',None
    if kind=='MAIN_NARRATOR':
        if cls=='MICRO': return 'OPACITY_FADE_IN',None
        if cx<0.43:return 'POSITION_ENTRY','LEFT'
        if cx>0.57:return 'POSITION_ENTRY','RIGHT'
        return 'POSITION_ENTRY','BOTTOM'
    if kind=='SECONDARY_CHARACTER':
        if cls in {'MEDIUM','LONG','EXTENDED'} and explicit_trigger:
            return ('POSITION_ENTRY','LEFT' if cx<=0.5 else 'RIGHT')
        return 'OPACITY_FADE_IN',None
    if cls=='MICRO':
        return 'OPACITY_FADE_IN',None
    # Connected/reveal-only subobjects must never translate or scale away from their source seams.
    if animation_mode in {'REVEAL_ONLY','GROUP_ONLY'} and int(u.get('hierarchy_level') or 0)>0:
        return 'OPACITY_FADE_IN',None
    # Scale Pop is reserved for supporting elements exactly as required by the hard PDF.
    if role!='PRIMARY' and typ in {'STATUS','NUMBER','PRICE','LABEL','SYMBOL','ICON','ARROW','CAPTION'}:
        return 'SCALE_POP',None
    if role!='PRIMARY' and area<0.055 and explicit_trigger:
        return 'SCALE_POP',None
    # Reference choreography: safe semantic actors/targets/results should travel, not merely fade.
    # P1 reserved Position entry mostly for ACTOR, which produced excellent spacing but timid motion.
    # P2 expands directional travel only when the occlusion graph certifies translation safety and
    # there is enough time for the locked 12-frame Position contract.
    safe_translate=bool(u.get('translation_safe_after_occlusion',u.get('animation_safe',True)))
    role_motion=motion_role in {'ACTOR','TARGET','RESULT'}
    profile_motion=profile in {'CAUSE_FLOW','COMPARISON','INTERFACE_FOCUS','RESOLUTION'} and role=='PRIMARY'
    major_support=(role!='PRIMARY' and area>=0.070 and motion_role in {'TARGET','RESULT'})
    if explicit_trigger and cls in {'MEDIUM','LONG','EXTENDED'} and safe_translate and (role_motion or profile_motion or major_support):
        if cx<0.42:return 'POSITION_ENTRY','LEFT'
        if cx>0.58:return 'POSITION_ENTRY','RIGHT'
        # Centered semantic results/targets rise from below; narrator TOP remains forbidden.
        return 'POSITION_ENTRY','BOTTOM'
    return 'OPACITY_FADE_IN',None

def _outside(direction: str | None, x: float, y: float, w: float, h: float, pad: float = 0.08):
    if direction == 'LEFT': return (-w / 2 - pad, y)
    if direction == 'RIGHT': return (1 + w / 2 + pad, y)
    if direction == 'BOTTOM': return (x, 1 + h / 2 + pad)
    if direction == 'TOP': return (x, -h / 2 - pad)
    return x, y


def _scene_unit_map(scene: dict) -> dict[str, dict]:
    return {str(u.get('unit_id')): u for u in (scene.get('units') or []) if u.get('unit_id')}


def _event_cost(method: str, focus_beats: list[dict], story_actions: list[dict], drift: bool, role: str) -> float:
    base = {'CONTINUATION': 0.02, 'OPACITY_FADE_IN': 0.20, 'SCALE_POP': 0.30, 'POSITION_ENTRY': 0.48}.get(method, 0.18)
    base += 0.18 * len(focus_beats)
    # Story beats carry the narrative and therefore cost less than full-frame
    # transition energy. They are local object transformations, not decoration.
    base += sum(float(x.get('budget_cost',0.16)) for x in story_actions)
    if drift:
        base += 0.10
    if role != 'PRIMARY':
        base *= 0.84
    return round(base, 3)


def _clamp_delta(v: float, limit: float) -> float:
    return max(-limit,min(limit,float(v)))


def _beat_window(scene_start:float,scene_end:float,center:float,duration:float):
    half=max(0.12,duration*0.5);st=max(scene_start,center-half);en=min(scene_end,center+half)
    if en-st<0.20:
        st=max(scene_start,min(scene_end-0.20,center-0.10));en=min(scene_end,st+0.20)
    return st,en


def _progression_rows(scene:dict, unit_id:str)->list[dict]:
    out=[]
    for row in scene.get('visual_progression') or []:
        if not isinstance(row,dict):continue
        targets=[str(x) for x in (row.get('targets') or [])]
        if targets and str(unit_id) not in targets:continue
        out.append(row)
    return out


def _progression_time(row:dict,alignment:dict,st:dict,scene:dict)->float|None:
    tr=row.get('trigger') if isinstance(row,dict) else None
    t=_word_time(tr,alignment,st,False)
    if t is not None:return t
    f=_char_fraction(tr,scene)
    if f is None:return None
    return float(st['start'])+(float(st['end'])-float(st['start']))*(0.10+0.78*f)


def _progression_intent(row:dict)->str:
    if not isinstance(row,dict):return ''
    for k in ('motion_intent','intent','action','state','type','name'):
        v=row.get(k)
        if v:return str(v).upper().replace(' ','_').replace('-','_')
    return ''


def _action_window(scene_start: float, scene_end: float, start: float, duration: float) -> tuple[float,float]:
    st=max(scene_start,min(scene_end-0.16,float(start)))
    en=min(scene_end,max(st+0.16,st+float(duration)))
    return st,en


def _action(kind: str, st: float, en: float, *, source: str, budget_cost: float,
            dx: float = 0.0, dy: float = 0.0, scale_from: float = 1.0,
            scale_peak: float = 1.0, scale_end: float = 1.0, opacity_from: float = 1.0,
            opacity_peak: float = 1.0, opacity_end: float = 1.0, hold_after: bool = False,
            arc_norm: float = 0.0, target_semantic_unit_id: str | None = None,
            authority_priority: int = 20) -> dict:
    return {
        'kind': kind, 'start_seconds': round(st,6), 'end_seconds': round(en,6),
        'source': source, 'budget_cost': float(budget_cost), 'dx_norm': float(dx), 'dy_norm': float(dy),
        'scale_from': float(scale_from), 'scale_peak': float(scale_peak), 'scale_end': float(scale_end),
        'opacity_from': float(opacity_from), 'opacity_peak': float(opacity_peak), 'opacity_end': float(opacity_end),
        'hold_after': bool(hold_after), 'arc_norm': float(arc_norm),
        'target_semantic_unit_id': target_semantic_unit_id, 'authority_priority': int(authority_priority),
    }


def _story_actions_from_machine(machine:dict, node_id:str, *, settle:float, scene_end:float, fps:float)->list[dict]:
    out=[];min_dur=12.0/max(1.0,fps)
    for a in (machine.get('actions') or []):
        if str(a.get('node_id'))!=str(node_id):continue
        kind=str(a.get('kind') or '')
        if kind=='INTRODUCE':
            st=float(a.get('start_seconds',settle));en=max(st+min_dur,float(a.get('end_seconds',st+min_dur)));en=min(float(scene_end)-0.02,en)
            if en-st<min_dur-1e-6:continue
            out.append({'kind':'INTRODUCE','render_mode':'APPEARANCE_AUTHORITY','start_seconds':round(st,6),'end_seconds':round(en,6),'source':str(a.get('authority') or 'SEMANTIC_ACTING_SCHEDULE'),'budget_cost':0.05,'dx_norm':0.0,'dy_norm':0.0,'scale_from':1.0,'scale_peak':1.0,'scale_end':1.0,'opacity_from':1.0,'opacity_peak':1.0,'opacity_end':1.0,'hold_after':True,'target_semantic_unit_id':None,'authority_priority':int(a.get('priority',70)),'motion_role':a.get('motion_role'),'semantic_purpose':a.get('semantic_purpose'),'confidence':float(a.get('confidence',0.0))})
            continue
        if kind!='POSITION_TRANSFER' or str(a.get('render_mode') or 'MOTION')!='MOTION':continue
        st=max(float(a.get('start_seconds',0)),float(settle)+0.04);en=max(st+min_dur,float(a.get('end_seconds',st)));en=min(float(scene_end)-0.03,en)
        if en-st<min_dur-1e-6:continue
        out.append({'kind':'POSITION_TRANSFER','render_mode':'MOTION','start_seconds':round(st,6),'end_seconds':round(en,6),'source':str(a.get('authority') or 'VISUAL_STORY_STATE_MACHINE'),'budget_cost':0.24,'dx_norm':float(a.get('dx_norm',0.0)),'dy_norm':float(a.get('dy_norm',0.0)),'scale_from':1.0,'scale_peak':1.0,'scale_end':1.0,'opacity_from':1.0,'opacity_peak':1.0,'opacity_end':1.0,'hold_after':True,'arc_norm':0.0,'target_semantic_unit_id':a.get('target_node_id'),'authority_priority':int(a.get('priority',70)),'interpolation':'BEZIER_EASE_IN_OUT','minimum_frames':12,'motion_role':a.get('motion_role'),'semantic_purpose':a.get('semantic_purpose'),'confidence':float(a.get('confidence',0.0))})
    return out[:4]

def build_motion_plan(plan: dict, alignment: dict, vision_results: list[dict], rules_path: str | pathlib.Path, reference_path: str | pathlib.Path, fps: float = 30.0, logger=None, calibration: dict | None = None):
    rules=read_json(rules_path);ref=read_json(reference_path);tm=_scene_timing_map(alignment);vis={str(v['scene_id']):v for v in vision_results}
    visual_sequence_plan=build_visual_sequences(plan,alignment,vision_results,fps=fps);visual_sequence_map={str(r.get('scene_id')):r for r in (visual_sequence_plan.get('scenes') or [])}
    outside_pad=max(0.02,min(0.12,float((calibration or {}).get('outside_pad',0.08))))
    events=[];scenes_out=[];recent_strong_at=None;scene_list=plan.get('scenes') or [];prev_identity_keys=set()
    for scene_index,scene in enumerate(scene_list):
        sid=str(scene['scene_id']);st=tm[sid];vr=vis[sid];scene_start=float(st['start']);scene_end=float(st['end']);dur=max(1.0/fps,scene_end-scene_start)
        profile=_scene_profile(scene,vr,dur);budget=_scene_budget(scene,vr,dur);cls=budget['duration_class'];vseq=visual_sequence_map.get(sid,{})
        camera_fit=compute_reference_camera_fit(float(vr.get('foreground_fraction') or 0.0),list(vr.get('units') or []),ref)
        trans=_transition(scene,scene_index,dur,profile,fps,recent_strong_at,scene_start)
        if scene_index>0:
            strategy=str(vseq.get('boundary_strategy') or 'OBJECT_MATCH_BLEND')
            if strategy=='SEQUENCE_OBJECT_CARRY':
                frames=6 if dur>=0.70 else 4;trans={'mode':'SEQUENCE_OBJECT_CARRY','duration_seconds':round(frames/fps,6),'white_reset':False,'relation':trans.get('relation'),'profile':profile,'energy_cost':0.13,'strong':False,'transition_frames':frames}
            elif strategy=='OBJECT_MATCH_BLEND':
                frames=8 if dur>=0.80 else 6;trans={'mode':'OBJECT_MATCH_BLEND','duration_seconds':round(frames/fps,6),'white_reset':False,'relation':trans.get('relation'),'profile':profile,'energy_cost':0.18,'strong':False,'transition_frames':frames}
        if trans.get('strong'):recent_strong_at=scene_start
        unit_meta=_scene_unit_map(scene);units=list(vr.get('units') or [])
        units.sort(key=lambda u:(0 if str(u.get('semantic_role')).upper()=='PRIMARY' else 1,0 if _unit_kind(u)=='VISUAL' else 1,str(u.get('physical_id'))))
        trigger_times={}
        for suid,sem0 in unit_meta.items():
            trigger_times[suid]={'appear':_word_time(sem0.get('appear_trigger') or sem0.get('focus_trigger'),alignment,st,False),'focus':_word_time(sem0.get('focus_trigger'),alignment,st,False)}
        semantic_graph=build_semantic_object_graph(scene,units,trigger_times,scene_duration_seconds=dur)
        story_machine=build_story_state_machine(scene,semantic_graph,scene_start=scene_start,scene_end=scene_end,fps=fps)
        graph_nodes={str(n.get('node_id')):n for n in (semantic_graph.get('nodes') or [])}
        current_identity_keys=set()
        for u in units:
            sem=unit_meta.get(str(u.get('semantic_unit_id'))) or {};key=_identity_key(sem,u)
            if key and int(u.get('hierarchy_level') or 0)==0:current_identity_keys.add(key)
        relation=_norm_relation(scene);scene_events=[];previous_hit=None
        for idx,u in enumerate(units):
            sem=unit_meta.get(str(u.get('semantic_unit_id'))) or {};node=graph_nodes.get(str(u.get('physical_id'))) or {};motion_role=str(node.get('motion_role') or 'CONTEXT')
            appear_trigger=sem.get('appear_trigger') or sem.get('focus_trigger');focus_trigger=sem.get('focus_trigger');exit_trigger=sem.get('exit_trigger')
            exact_hit=_word_time(appear_trigger,alignment,st,False);frac=_char_fraction(appear_trigger,scene)
            staged_hit=(story_machine.get('reveal_schedule') or {}).get(str(u.get('physical_id')))
            if staged_hit is not None:
                hit=float(staged_hit)
            elif exact_hit is not None:hit=exact_hit
            elif frac is not None:hit=scene_start+dur*(0.06+0.78*frac)
            else:
                n=max(1,len(units));base=0.05 if idx==0 else min(0.74,0.14+idx*(0.58/max(1,n-1)));hit=scene_start+dur*base
            hit=max(scene_start,min(scene_end-1.0/fps,hit))
            incoming_hold=float(vseq.get('incoming_carry_hold_seconds') or 0.0)
            if idx==0 and incoming_hold>0:
                hit=max(hit,min(scene_end-1.0/fps,scene_start+incoming_hold))
            # Spike suppression: simultaneous entrances are deliberately sequenced.
            if previous_hit is not None and dur>=0.80 and hit-previous_hit<0.18:
                hit=min(scene_end-1.0/fps,previous_hit+min(0.30,max(0.18,dur*0.075)))
            previous_hit=hit
            identity=_identity_key(sem,u);persistent=bool(identity and identity in prev_identity_keys and relation in {'CONTINUE','ADD','REFLOW'} and int(u.get('hierarchy_level') or 0)==0)
            method,direction=_entry_for_unit(u,dur,scene_index,str(vr.get('mode') or 'CLEAN_LAYERED'),profile,bool(appear_trigger),motion_role,persistent)
            if method=='POSITION_ENTRY':entry_dur=clamp_duration('POSITION_ENTRY',dur*0.26,fps)
            elif method=='SCALE_POP':entry_dur=clamp_duration('SCALE_POP',dur*0.19,fps)
            elif method=='OPACITY_FADE_IN':entry_dur=clamp_duration('OPACITY_FADE_IN',dur*0.15,fps)
            else:entry_dur=0.0
            if method=='CONTINUATION':start=scene_start;settle=scene_start;perceptual_hit=scene_start
            else:
                # V31.0.25: the voice owns the semantic impact. Start the approved
                # preset early enough that travel is effectively complete at the word.
                hit_fraction=0.90 if method=='POSITION_ENTRY' else (0.86 if method=='SCALE_POP' else 0.82)
                start,perceptual_hit,settle=schedule_around_hit(hit,entry_dur,scene_start,scene_end,fps,hit_fraction) if entry_dur>0 else (hit,hit,hit)
            endx,endy=map(float,u.get('center_norm') or [0.5,0.5]);_,_,bw,bh=map(float,u.get('bbox_norm') or [0,0,0.2,0.2]);sx,sy=_outside(direction,endx,endy,bw,bh,outside_pad)
            if method in {'CONTINUATION','OPACITY_FADE_IN','SCALE_POP'}:sx,sy=endx,endy
            is_fifth_overlay=bool(u.get('fifth_element_overlay'))
            story_actions=[] if is_fifth_overlay else _story_actions_from_machine(story_machine,str(u.get('physical_id')),settle=settle,scene_end=scene_end,fps=fps)
            explicit_exit=_word_time(exit_trigger,alignment,st,True);is_last=scene_index==len(scene_list)-1;disappearance='HOLD_TO_BOUNDARY';exit_start=scene_end;exit_end=scene_end;exit_x=endx;exit_y=endy;exit_interp=None
            should_clear=is_last or (explicit_exit is not None and explicit_exit<scene_end-0.05)
            if should_clear and cls!='MICRO':
                wanted_end=min(scene_end,explicit_exit if explicit_exit is not None else scene_end)
                if _unit_kind(u)=='MAIN_NARRATOR' and dur>=1.10:
                    exit_dur=clamp_duration('POSITION_ENTRY',dur*0.16,fps);exit_start=max(settle,wanted_end-exit_dur);exit_end=wanted_end;disappearance='POSITION_EXIT';exit_interp='BEZIER_EASE_IN_OUT'
                    outdir=direction if direction in {'LEFT','RIGHT','BOTTOM'} else ('LEFT' if endx<0.5 else 'RIGHT');exit_x,exit_y=_outside(outdir,endx,endy,bw,bh,outside_pad)
                else:
                    exit_dur=clamp_duration('OPACITY_FADE_OUT',dur*0.10,fps);exit_start=max(settle,wanted_end-exit_dur);exit_end=wanted_end;disappearance='OPACITY_FADE_OUT'
            physical_story_actions=[a for a in story_actions if str(a.get('render_mode') or 'MOTION')=='MOTION']
            # Continuous 110->100 motion is applied later at composition-slot scope so every
            # sub-layer of one semantic object remains registered while the object breathes.
            continuous_scale=False
            semantic_type=str(u.get('semantic_type') or '').upper();semantic_role=str(u.get('semantic_role') or '').upper()
            if physical_story_actions:motion_energy='HIGH'
            elif story_actions:motion_energy='MEDIUM'
            elif method=='POSITION_ENTRY' or continuous_scale:motion_energy='MEDIUM'
            else:motion_energy='LOW'
            cost=_event_cost(method,[],story_actions,False,semantic_role)+(0.13 if continuous_scale else 0.0)
            ev={
                'event_id':f'{sid}_{u["physical_id"]}','scene_id':sid,'physical_id':u['physical_id'],'semantic_unit_id':u.get('semantic_unit_id'),'semantic_type':u.get('semantic_type'),'semantic_role':u.get('semantic_role'),'kind':_unit_kind(u),
                'start_seconds':round(start,6),'perceptual_hit_seconds':round(perceptual_hit,6),'settle_seconds':round(settle,6),'end_seconds':round(scene_end,6),
                'appearance_method':method,'entry_direction':direction,'start_x_norm':round(sx,6),'start_y_norm':round(sy,6),'end_x_norm':round(endx,6),'end_y_norm':round(endy,6),
                'position_animated':method=='POSITION_ENTRY','position_min_frames':12,'position_interpolation':'BEZIER_EASE_IN_OUT','motion_profile':'JERK_LIMITED_S_CURVE_7','motion_blur_enabled':(method=='POSITION_ENTRY' or bool(physical_story_actions)),'motion_engine':'HEXA_V31_PROFESSIONAL_SEMANTIC_MOTION_ARCHITECTURE',
                'scale_pop':[100,110,100] if method=='SCALE_POP' else None,'scale_pop_from':1.0,'scale_pop_peak':1.10 if method=='SCALE_POP' else 1.0,
                'opacity_concealment_enter':[100,0] if method in {'SCALE_POP','OPACITY_FADE_IN'} else [0,0],
                'disappearance_method':disappearance,'exit_start_seconds':round(exit_start,6),'exit_end_seconds':round(exit_end,6),'exit_x_norm':round(exit_x,6),'exit_y_norm':round(exit_y,6),'exit_position_interpolation':exit_interp,
                'focus_beats':[],'story_actions':story_actions,'story_beats':[],'continuous_drift':False,'drift_dx_norm':0.0,'drift_dy_norm':0.0,'drift_scale_from':1.0,'drift_scale_to':1.0,
                'continuous_image_scale':continuous_scale,'continuous_scale_from':1.10 if continuous_scale else 1.0,'continuous_scale_to':1.0,'continuous_scale_min_seconds':3.0,
                'bbox_norm':u.get('bbox_norm'),'resting_composition_authority':'SOURCE_SCENE_IMAGE','reference_outside_pad':outside_pad,
                'semantic_trigger_bound':bool(appear_trigger),'focus_trigger_bound':bool(focus_trigger),'explicit_exit_bound':bool(exit_trigger),'transition_relation':trans['relation'],'choreography_profile':profile,
                'motion_energy':motion_energy,'attention_priority':'PRIMARY' if semantic_role=='PRIMARY' else 'SUPPORTING','budget_cost':round(cost,3),'semantic_intent':str(sem.get('semantic_intent') or '').upper(),'narrative_function':sem.get('narrative_function'),
                'motion_role':motion_role,'hierarchy_level':int(u.get('hierarchy_level') or 0),'parent_semantic_unit_id':u.get('parent_semantic_unit_id'),'composition_slot_id':u.get('composition_slot_id') or u.get('semantic_unit_id') or u.get('physical_id'),'subobject_role':u.get('subobject_role'),'hierarchy_confidence':float(u.get('hierarchy_confidence') or 0.0),'animation_safe':bool(u.get('animation_safe',True)),'translation_safe_after_occlusion':bool(u.get('translation_safe_after_occlusion',u.get('animation_safe',True))),'occlusion_reveal_risk':float(u.get('occlusion_reveal_risk',0.0)),'reveal_safe':bool(u.get('reveal_safe',True)),'animation_mode':str(u.get('animation_mode') or ('TRANSLATE_SAFE' if u.get('translation_safe_after_occlusion',u.get('animation_safe',True)) else 'GROUP_ONLY')),'occlusion_class':str(u.get('occlusion_class') or ''),'matting':u.get('matting') or {},'identity_persistence':persistent,'reference_camera_scale':float(camera_fit.get('camera_scale',1.0)),
                'fifth_element_overlay':is_fifth_overlay,'overlay_black_opacity_percent':42 if is_fifth_overlay else None,'overlay_blur_percent':16 if is_fifth_overlay else None,'overlay_base_four_must_persist':True if is_fifth_overlay else None,
            }
            scene_events.append(ev)
        if not scene_events and vr.get('mode')=='FLAT_SCENE':
            fade=clamp_duration('OPACITY_FADE_IN',dur*0.12,fps);scene_events=[{
                'event_id':f'{sid}_FLAT','scene_id':sid,'physical_id':'FULL_SCENE','semantic_unit_id':None,'semantic_type':'FULL_SCENE','semantic_role':'PRIMARY','kind':'FLAT_SCENE',
                'start_seconds':round(scene_start,6),'perceptual_hit_seconds':round(scene_start,6),'settle_seconds':round(min(scene_end,scene_start+fade),6),'end_seconds':round(scene_end,6),
                'appearance_method':'OPACITY_FADE_IN','entry_direction':None,'start_x_norm':0.5,'start_y_norm':0.5,'end_x_norm':0.5,'end_y_norm':0.5,'position_animated':False,
                'disappearance_method':'OPACITY_FADE_OUT' if scene_index==len(scene_list)-1 else 'HOLD_TO_BOUNDARY','exit_start_seconds':round(max(scene_start,scene_end-clamp_duration('OPACITY_FADE_OUT',dur*0.10,fps)),6) if scene_index==len(scene_list)-1 else round(scene_end,6),'exit_end_seconds':round(scene_end,6),'exit_x_norm':0.5,'exit_y_norm':0.5,
                'focus_beats':[],'story_actions':[],'story_beats':[],'continuous_drift':False,'continuous_image_scale':dur>=3.0,'continuous_scale_from':1.10 if dur>=3.0 else 1.0,'continuous_scale_to':1.0,'continuous_scale_min_seconds':3.0,
                'resting_composition_authority':'SOURCE_SCENE_IMAGE','reference_outside_pad':outside_pad,'semantic_trigger_bound':False,'focus_trigger_bound':False,'explicit_exit_bound':False,'transition_relation':trans['relation'],'choreography_profile':profile,'motion_energy':'MEDIUM' if dur>=3.0 else 'LOW','attention_priority':'PRIMARY','budget_cost':0.18,
            }]
        # V31 continuous visual timeline: long shots use one synchronized scene-camera
        # 110->100 move across every full-canvas layer. Because all semantic layers share
        # one source canvas, this preserves registration even when a child is revealed late.
        # It is the PDF continuous-image rule applied to the complete scene, not a random pulse.
        if dur>=3.0 and scene_events:
            for e in scene_events:
                e['continuous_image_scale']=True
                e['continuous_scale_from']=1.10
                e['continuous_scale_to']=1.0
                e['continuous_scale_min_seconds']=3.0
                e['continuous_scale_group_id']='SCENE_CAMERA::'+sid
                e['continuous_scale_scene_start_seconds']=scene_start
                e['continuous_scale_scene_end_seconds']=scene_end
                e['budget_cost']=round(float(e.get('budget_cost',0.0))+0.025/max(1,len(scene_events)),3)
                if e.get('motion_energy')=='LOW':e['motion_energy']='MEDIUM'

        estimated_cost=float(trans.get('energy_cost',0.0))+sum(float(e.get('budget_cost',0.0)) for e in scene_events);events.extend(scene_events)
        change_times=[scene_start,scene_end]
        for e in scene_events:
            change_times.extend([float(e.get('start_seconds',scene_start)),float(e.get('settle_seconds',scene_start))])
            for a in e.get('story_actions') or []:change_times.extend([float(a.get('start_seconds',scene_start)),float(a.get('end_seconds',scene_start))])
        change_times=sorted(set(max(scene_start,min(scene_end,x)) for x in change_times));max_story_gap=max([b-a for a,b in zip(change_times,change_times[1:])] or [dur])
        if any(bool(e.get('continuous_image_scale')) for e in scene_events):max_story_gap=min(max_story_gap,1.20)
        scenes_out.append({
            'scene_id':sid,'start_seconds':scene_start,'end_seconds':scene_end,'duration_seconds':dur,'duration_class':cls,'vision_mode':vr.get('mode'),'choreography_profile':profile,'relation_to_previous':trans['relation'],'transition':trans,'visual_sequence':vseq,'reference_camera_fit':camera_fit,
            'visual_progression_count':_visual_progression_count(scene),'event_ids':[e['event_id'] for e in scene_events],'internal_change_count':sum(1+len(e.get('story_actions') or []) for e in scene_events),'semantic_focus_count':0,
            'story_beat_count':sum(len(e.get('story_actions') or []) for e in scene_events),'story_action_count':sum(len(e.get('story_actions') or []) for e in scene_events),'physical_story_action_count':sum(1 for e in scene_events for a in (e.get('story_actions') or []) if str(a.get('render_mode') or 'MOTION')=='MOTION'),'max_story_gap_seconds':round(max_story_gap,3),'semantic_object_graph':semantic_graph,'story_state_machine':story_machine,
            'hierarchical_motion_unit_count':sum(1 for e in scene_events if int(e.get('hierarchy_level') or 0)>0),'composition_slot_count':len(set(str(e.get('composition_slot_id') or e.get('semantic_unit_id') or e.get('physical_id')) for e in scene_events)),'fifth_element_overlay_event_id':next((e.get('event_id') for e in scene_events if e.get('fifth_element_overlay')),None),'short_beat':cls in {'MICRO','SHORT'},'motion_budget':budget,'estimated_motion_cost':round(estimated_cost,3),'budget_utilization':round(estimated_cost/max(0.01,float(budget['budget_points'])),3),
        })
        prev_identity_keys=current_identity_keys
    opening_white_count=1 if scenes_out and (scenes_out[0].get('transition') or {}).get('white_reset') else 0;reset_count=sum(1 for i,s in enumerate(scenes_out) if i>0 and (s.get('transition') or {}).get('white_reset'));transition_boundary_count=max(1,len(scenes_out)-1)
    out={
        'schema':'HEXA_MOTION_PLAN_V31','version':'8.1-P2','fps':fps,'project_id':plan.get('project_id'),'rules_authority':rules.get('authority_id'),'reference_authority':ref.get('authority_id'),'timing_method':alignment.get('method'),
        'scenes':scenes_out,'events':events,'visual_sequence_plan':visual_sequence_plan,'motion_dna_version':'HEXA_MOTION_DNA_V31_P2_REFERENCE_CHOREOGRAPHY__'+MOTION_DNA_ID,'calibration':{'outside_pad':outside_pad,'metric_autotuning':False},
        'continuity_summary':{'scene_count':len(scenes_out),'opening_white_count':opening_white_count,'white_reset_scene_count':reset_count,'white_reset_scene_percent':round(100.0*reset_count/transition_boundary_count,2),'transition_modes':sorted(set((s.get('transition') or {}).get('mode') for s in scenes_out)),'choreography_profiles':sorted(set(s.get('choreography_profile') for s in scenes_out)),'appearance_methods':sorted(set(e.get('appearance_method') for e in events)),'strong_transition_count':sum(1 for s in scenes_out if (s.get('transition') or {}).get('strong')),'identity_persistence_count':sum(1 for e in events if e.get('identity_persistence'))},
        'budget_summary':{'scene_budget_system':'DURATION_DENSITY_PROGRESSION_AWARE','max_scene_budget_utilization_pre_orchestration':round(max([s.get('budget_utilization',0.0) for s in scenes_out] or [0.0]),3),'untriggered_focus_beats':0,'story_beat_count':sum(len(e.get('story_actions') or []) for e in events),'story_action_count':sum(len(e.get('story_actions') or []) for e in events),'story_sources':sorted(set(b.get('source') for e in events for b in (e.get('story_actions') or []))),'stateful_story_action_count':sum(1 for e in events for b in (e.get('story_actions') or []) if b.get('hold_after')),'semantic_object_graph_scene_count':sum(1 for s in scenes_out if (s.get('semantic_object_graph') or {}).get('nodes')),'hierarchical_motion_unit_count':sum(1 for e in events if int(e.get('hierarchy_level') or 0)>0),'inferred_causal_edge_count':sum(int((s.get('semantic_object_graph') or {}).get('inferred_causal_edge_count',0)) for s in scenes_out),'actionable_story_edge_count':sum(int((s.get('semantic_object_graph') or {}).get('actionable_edge_count',0)) for s in scenes_out),'story_eligible_scene_count':sum(1 for s in scenes_out if (s.get('semantic_object_graph') or {}).get('story_eligible'))},
        'hard_invariants':{
            'editing_rules_authority':'HEXA_EDITING_ENGINE_RULES_V20_PDF_HARD_CONSTRAINTS','reference_preset_role':'MOTION_FEEL_REFERENCE_ONLY','hard_rules_override_preset_on_conflict':True,
            'animated_position_execution':'PRE_RENDERED_EQUIVALENT_TRANSFORM','premiere_still_keyframes_required':False,'premiere_keyframes_required':False,'premiere_transform_effect_dependency':False,'basic_motion_position_forbidden':True,
            'position_minimum_frames':12,'position_interpolation':'BEZIER_EASE_IN_OUT','position_motion_profile':'JERK_LIMITED_S_CURVE_7','main_narrator_top_entry_exit_forbidden':True,'scale_exit_forbidden':True,'supporting_scale_pop':[100,110,100],'continuous_image_scale':[110,100],'continuous_image_scale_min_seconds':3.0,
            'full_scene_relative_composition_preserved':True,'mandatory_white_reset_between_scenes':False,'cross_scene_bridge_required':True,'visual_sequence_director_required':True,'micro_scene_linger_required':True,'composition_slots_independent_from_physical_layers':True,'semantic_trigger_choreography_required':True,'hierarchical_object_decomposition_required':True,'semantic_object_graph_required':True,'visual_story_state_machine_required':True,'stateful_object_lifecycle_required':True,'single_story_truth_required':True,'vacuous_story_pass_forbidden':True,'occlusion_safe_animation_required':True,'edge_aware_alpha_matting_required':True,'uniform_reference_camera_fit_required':True,'voice_hit_pre_roll_required':True,'jerk_limited_motion_required':True,
            'topic_specific_motion_hardcoding_forbidden':True,'auto_relationship_arrow_forbidden':True,'fifth_element_overlay':{'black_opacity_percent_range':[40,45],'default_black_opacity_percent':42,'blur_percent':16,'base_four_must_persist':True},'full_frame_transition_max_frames_normal':8,'max_normal_white_reset_scene_percent':18.0,'severe_motion_spikes_target_per_minute_max':3.0,
            'allowed_appearance':['POSITION_ENTRY','SCALE_POP','OPACITY_FADE_IN','CONTINUATION'],'allowed_disappearance':['POSITION_EXIT','OPACITY_FADE_OUT','HOLD_TO_BOUNDARY']
        }
    }
    if logger:logger.log('PASS','MOTION_PLAN_BUILT',event_count=len(events),scene_count=len(scenes_out),fps=fps,motion_dna=out['motion_dna_version'],white_reset_percent=out['continuity_summary']['white_reset_scene_percent'],hierarchical_units=out['budget_summary']['hierarchical_motion_unit_count'],inferred_causal_edges=out['budget_summary']['inferred_causal_edge_count'],actionable_story_edges=out['budget_summary'].get('actionable_story_edge_count'),story_eligible_scenes=out['budget_summary'].get('story_eligible_scene_count'),story_actions=out['budget_summary'].get('story_action_count'))
    return out

# ---------------------------------------------------------------------------
# V31.0.1 USER PRESET AUTHORITY
# Latest explicit user motion/output rules supersede the legacy V20/V31-P2
# heuristic director.  Keep the older implementation above only for forensic
# compatibility; production imports resolve to this final definition.
# ---------------------------------------------------------------------------
from hexa_v31.preset_story_planner import build_preset_story_motion_plan as _build_preset_story_motion_plan

def build_motion_plan(plan: dict, alignment: dict, vision_results: list[dict], rules_path: str | pathlib.Path, reference_path: str | pathlib.Path, fps: float = 30.0, logger=None, calibration: dict | None = None):
    return _build_preset_story_motion_plan(
        plan, alignment, vision_results, rules_path, reference_path,
        fps=fps, logger=logger, calibration=calibration,
    )
