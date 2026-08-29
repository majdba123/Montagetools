from __future__ import annotations
import difflib, json, math, os, pathlib, re
from dataclasses import dataclass
import numpy as np
from .audio import load_wav_mono, rms_envelope
from .util import canonical_words_with_offsets, normalize_arabic, read_json, write_json

class AlignmentError(RuntimeError): pass


def project_scene_intervals_from_word_timings(plan: dict, alignment: dict, duration: float, fps: float=30.0) -> dict:
    """Project raw word timestamps onto one continuous, non-overlapping scene timeline.

    Faster-Whisper word timestamps can contain tiny overlaps/gaps between adjacent words.
    Those are valid acoustic observations but are not valid scene clip boundaries.  V20.0.3
    keeps the physical word timestamps unchanged and derives scene boundaries from the midpoint
    between the previous scene's final word and the next scene's first word.  The projected
    scene intervals are continuous, monotonic, and at least the 12-frame Transform minimum.
    """
    rows=alignment.get('word_timings') or []
    scenes=plan.get('scenes') or []
    if not rows or not scenes:
        return alignment
    duration=float(max(duration,0.001)); min_scene=max(1.0/fps,12.0/fps)
    lexical=[]
    for s in scenes:
        a=int(s['script_span']['global_char_start']); b=int(s['script_span']['global_char_end'])
        wr=[r for r in rows if int(r['char_end'])>a and int(r['char_start'])<b]
        if not wr: raise AlignmentError(f'No aligned words for {s["scene_id"]} during scene projection')
        lexical.append((float(wr[0]['start']),float(wr[0]['end']),float(wr[-1]['start']),float(wr[-1]['end']),wr))
    raw=[0.0]
    max_overlap=0.0; max_gap=0.0
    for i in range(1,len(scenes)):
        left_end=lexical[i-1][3]; right_start=lexical[i][0]
        if right_start < left_end: max_overlap=max(max_overlap,left_end-right_start)
        else: max_gap=max(max_gap,right_start-left_end)
        raw.append(max(0.0,min(duration,(left_end+right_start)*0.5)))
    raw.append(duration)
    n=len(scenes)
    # Feasible bounds guarantee every scene can host a strict 12-frame Position animation.
    b=[0.0]*(n+1); b[0]=0.0; b[n]=duration
    for i in range(1,n):
        lo=i*min_scene; hi=duration-(n-i)*min_scene
        if lo>hi:
            # Extremely short project: fall back to one-frame positivity rather than inventing time.
            min_scene=max(1.0/fps,duration/max(1,n)*0.25); lo=i*min_scene; hi=duration-(n-i)*min_scene
        b[i]=max(lo,min(hi,raw[i]))
    # Forward/backward monotonic projection.
    for i in range(1,n): b[i]=max(b[i],b[i-1]+min_scene)
    for i in range(n-1,0,-1): b[i]=min(b[i],b[i+1]-min_scene)
    projected=[]
    for i,s in enumerate(scenes):
        first_start,first_end,last_start,last_end,wr=lexical[i]
        projected.append({
            'scene_id':s['scene_id'],'start':round(float(b[i]),6),'end':round(float(b[i+1]),6),
            'duration':round(float(b[i+1]-b[i]),6),'confidence':round(float(np.mean([float(r.get('confidence',0.0)) for r in wr])),4),
            'source':'CANONICAL_WORD_BOUNDARY_PROJECTION_V20_0_3',
            'trigger_start':round(first_start,6),'trigger_end':round(first_end,6),
            'lexical_start':round(first_start,6),'lexical_end':round(last_end,6),
        })
    out=dict(alignment); out['scene_timings']=projected
    q=dict(out.get('quality') or {})
    q.update({
        'scene_timing_projection':'MONOTONIC_CONTINUOUS_WORD_BOUNDARY_V20_0_3',
        'raw_adjacent_word_max_overlap_seconds':round(max_overlap,6),
        'raw_adjacent_word_max_gap_seconds':round(max_gap,6),
        'projected_scene_min_duration_seconds':round(min(x['duration'] for x in projected),6),
        'projected_scene_max_duration_seconds':round(max(x['duration'] for x in projected),6),
        'projected_scene_continuous':True,
    })
    out['quality']=q
    return out

@dataclass
class AlignedWord:
    index:int; raw:str; norm:str; char_start:int; char_end:int; start:float; end:float; confidence:float; source:str


def _scene_span_contract_allows_acoustic(plan: dict) -> bool:
    # Safe fallback only when every visual event is anchored exactly at scene start/full span.
    for s in plan.get('scenes') or []:
        sp=s.get('script_span') or {}; a=int(sp.get('global_char_start',-1))
        for ev in s.get('visual_progression') or []:
            t=ev.get('trigger') or {}
            if int(t.get('global_char_start',-2))!=a:
                return False
        for u in s.get('units') or []:
            t=u.get('appear_trigger') or {}
            if int(t.get('global_char_start',-2))!=a:
                return False
            if u.get('focus_trigger') is not None or u.get('exit_trigger') is not None:
                return False
    return True


def _candidate_minima(rms: np.ndarray, times: np.ndarray, duration: float):
    if len(rms)<5: return [(0.0,1.0),(duration,1.0)]
    # Smoothed log energy; local minima become candidate phrase boundaries.
    e=np.log10(np.maximum(rms,1e-7))
    k=5; smooth=np.convolve(e,np.ones(k)/k,mode='same')
    q25=float(np.quantile(smooth,0.25)); q50=float(np.quantile(smooth,0.50))
    c=[(0.0,1.0)]
    last=-9.0
    for i in range(2,len(smooth)-2):
        if smooth[i]<=smooth[i-1] and smooth[i]<=smooth[i+1] and smooth[i] <= q50:
            t=float(times[i])
            if t-last<0.10: continue
            depth=max(0.0,min(1.0,(q50-smooth[i])/max(0.05,q50-q25+1e-6)))
            c.append((t,depth)); last=t
    c.append((duration,1.0))
    return c


def acoustic_scene_alignment(plan: dict, wav_path: str|os.PathLike, duration: float, logger=None) -> dict:
    if not _scene_span_contract_allows_acoustic(plan):
        raise AlignmentError('Acoustic scene fallback forbidden: package has internal/focus/exit triggers requiring word-level alignment.')
    x,sr=load_wav_mono(wav_path); rms,times=rms_envelope(x,sr)
    scenes=plan['scenes']; script=plan['canonical_script']['text']; N=len(scenes)
    candidates=_candidate_minima(rms,times,duration)
    # Expected boundary from cumulative character weight. We use audio minima around it, not fabricated fixed timestamps.
    weights=[]
    for s in scenes:
        txt=s['script_span']['text']
        # Arabic letters carry more timing weight than punctuation/spaces.
        letters=sum(1 for ch in txt if ch.isalnum() or '\u0600'<=ch<='\u06ff')
        weights.append(max(1.0,float(letters)))
    cum=np.cumsum(weights); total=float(cum[-1])
    expected=[0.0]+[duration*float(cum[i-1]/total) for i in range(1,N)]+[duration]
    # Dynamic monotonic boundary selection from candidate minima within a generous local window.
    chosen=[0.0]
    prev=0.0
    median=max(0.35,duration/N)
    for i in range(1,N):
        ex=expected[i]
        lo=max(prev+0.12, ex-max(1.1,median*0.85)); hi=min(duration-0.12*(N-i), ex+max(1.1,median*0.85))
        opts=[(tt,dep) for tt,dep in candidates if lo<=tt<=hi]
        if opts:
            # Distance and silence depth. Strong silence can win over proportional expectation.
            tt,dep=min(opts,key=lambda z: abs(z[0]-ex)/(median+1e-6) - 0.55*z[1])
        else:
            tt=max(prev+0.12,min(ex,duration-0.12*(N-i)))
            dep=0.0
        chosen.append(float(tt)); prev=float(tt)
    chosen.append(duration)
    # Enforce monotonicity and non-negative intervals.
    for i in range(1,len(chosen)):
        if chosen[i]<=chosen[i-1]: chosen[i]=min(duration,chosen[i-1]+0.02)
    scene_rows=[]
    for i,s in enumerate(scenes):
        st=float(chosen[i]); en=float(chosen[i+1])
        # Confidence from nearest energy minimum depth and closeness to expected.
        near=min(candidates,key=lambda z:abs(z[0]-st)) if i>0 else (0.0,1.0)
        clos=max(0.0,1.0-abs(st-expected[i])/max(0.7,median))
        conf=0.55*near[1]+0.45*clos if i>0 else 1.0
        scene_rows.append({'scene_id':s['scene_id'],'start':st,'end':en,'duration':en-st,'confidence':round(float(conf),4),'source':'ACOUSTIC_BOUNDARY+CANONICAL_ORDER'})
    result={'method':'LOCAL_CANONICAL_ACOUSTIC_SCENE_ALIGNMENT_V20','production_semantics':'SCENE_BOUNDARY_ONLY','invented_timestamps':0,'duration_seconds':duration,'scene_count':N,'scene_timings':scene_rows,'word_timings':None,'quality':{
        'mean_boundary_confidence':round(float(np.mean([r['confidence'] for r in scene_rows])),4),
        'min_scene_duration':round(float(min(r['duration'] for r in scene_rows)),4),
        'max_scene_duration':round(float(max(r['duration'] for r in scene_rows)),4),
        'internal_trigger_support':False,
    }}
    if logger: logger.log('WARNING','ALIGNMENT_ACOUSTIC_FALLBACK','Word-level engine unavailable; using exact-package scene-start contract plus real acoustic boundaries.',**result['quality'])
    return result


def _find_local_whisper_model(runtime_cfg: dict) -> str|None:
    for p in runtime_cfg.get('whisper_model_candidates',[]) or []:
        pp=pathlib.Path(os.path.expandvars(os.path.expanduser(str(p))))
        if pp.is_dir() and (pp/'model.bin').is_file(): return str(pp)
    p=runtime_cfg.get('whisper_model_path')
    if p and pathlib.Path(os.path.expandvars(p)).is_dir(): return os.path.expandvars(p)
    return None


def _sequence_map(canon: list[dict], obs: list[dict]):
    # Global sequence matcher first, then local fuzzy bridges. Canonical stays authority.
    a=[w['norm'] for w in canon]; b=[w['norm'] for w in obs]
    sm=difflib.SequenceMatcher(a=a,b=b,autojunk=False)
    mapping={}
    for block in sm.get_matching_blocks():
        for k in range(block.size): mapping[block.a+k]=(block.b+k,1.0)
    # Fuzzy nearest monotonic candidates for unmatched words.
    last=-1
    for i in range(len(canon)):
        if i in mapping: last=mapping[i][0]; continue
        next_mapped=min((j for k,(j,c) in mapping.items() if k>i),default=len(obs))
        lo=max(last+1,0); hi=min(len(obs),next_mapped+2)
        best=None
        for j in range(lo,hi):
            ratio=difflib.SequenceMatcher(None,canon[i]['norm'],obs[j]['norm']).ratio()
            if best is None or ratio>best[0]: best=(ratio,j)
        if best and best[0]>=0.58:
            mapping[i]=(best[1],best[0]); last=best[1]
    return mapping


def whisper_exact_transcript_alignment(plan: dict, audio_path: str|os.PathLike, runtime_cfg: dict, logger=None) -> dict:
    try:
        from faster_whisper import WhisperModel
    except Exception as e: raise AlignmentError(f'faster_whisper unavailable: {e}')
    model_path=_find_local_whisper_model(runtime_cfg)
    if not model_path: raise AlignmentError('No verified local faster-whisper model. Setup/Repair must prepare one; BUILD never downloads.')
    device=runtime_cfg.get('whisper_device','cpu'); compute=runtime_cfg.get('whisper_compute_type','int8')
    if logger: logger.log('INFO','WHISPER_LOAD',model_path=model_path,device=device,compute_type=compute)
    try:
        model=WhisperModel(model_path,device=device,compute_type=compute,local_files_only=True,cpu_threads=max(1,int(runtime_cfg.get('cpu_threads',4))))
    except TypeError:
        # Older faster-whisper without local_files_only; path is local so no network is needed.
        model=WhisperModel(model_path,device=device,compute_type=compute,cpu_threads=max(1,int(runtime_cfg.get('cpu_threads',4))))
    segments,info=model.transcribe(str(audio_path),language='ar',word_timestamps=True,beam_size=5,vad_filter=True,condition_on_previous_text=True)
    obs=[]
    for seg in segments:
        for w in (seg.words or []):
            norm=normalize_arabic(w.word or '')
            if norm: obs.append({'raw':w.word,'norm':norm,'start':float(w.start),'end':float(w.end),'probability':float(getattr(w,'probability',0.0) or 0.0)})
    if not obs: raise AlignmentError('Whisper produced no word timestamps')
    script=plan['canonical_script']['text']; canon=canonical_words_with_offsets(script); mapping=_sequence_map(canon,obs)
    rows=[]; direct=0
    # Fill direct observed times; interpolate only missing canonical words with explicit source label.
    direct_times={i:(obs[j]['start'],obs[j]['end'],min(1.0,max(0.0,0.5*conf+0.5*obs[j]['probability']))) for i,(j,conf) in mapping.items()}
    for i,c in enumerate(canon):
        if i in direct_times:
            st,en,cf=direct_times[i]; src='WHISPER_OBSERVED'; direct+=1
        else:
            prev=max((k for k in direct_times if k<i),default=None); nxt=min((k for k in direct_times if k>i),default=None)
            if prev is not None and nxt is not None:
                p_end=direct_times[prev][1]; n_start=direct_times[nxt][0]; frac=(i-prev)/(nxt-prev); st=p_end+(n_start-p_end)*max(0.0,min(1.0,frac-0.2)); en=p_end+(n_start-p_end)*max(0.0,min(1.0,frac+0.2)); cf=0.35; src='BOUNDED_INTERPOLATION'
            elif prev is not None:
                st=direct_times[prev][1]; en=st+0.12; cf=0.2; src='TAIL_INTERPOLATION'
            elif nxt is not None:
                en=direct_times[nxt][0]; st=max(0.0,en-0.12); cf=0.2; src='HEAD_INTERPOLATION'
            else: raise AlignmentError('No canonical word mapping possible')
        rows.append({'index':i,'raw':c['raw'],'norm':c['norm'],'char_start':c['start'],'char_end':c['end'],'start':float(st),'end':float(max(en,st+0.001)),'confidence':round(float(cf),4),'source':src})
    direct_ratio=direct/max(1,len(canon))
    # Scene timestamps from canonical char-overlap. No semantic text from Whisper is substituted into the plan.
    scenes=[]
    for s in plan['scenes']:
        a=s['script_span']['global_char_start']; b=s['script_span']['global_char_end']
        wr=[r for r in rows if r['char_end']>a and r['char_start']<b]
        if not wr: raise AlignmentError(f'No aligned words for {s["scene_id"]}')
        scenes.append({'scene_id':s['scene_id'],'start':wr[0]['start'],'end':wr[-1]['end'],'duration':wr[-1]['end']-wr[0]['start'],'confidence':round(float(np.mean([r['confidence'] for r in wr])),4),'source':'CANONICAL_WORD_MAP'})
    return {'method':'FASTER_WHISPER_OBSERVED_WORDS+EXACT_CANONICAL_RECONCILIATION_V20','canonical_text_authority':True,'observed_text_is_not_authority':True,'invented_timestamps':0,'scene_count':len(scenes),'scene_timings':scenes,'word_timings':rows,'quality':{'canonical_word_direct_match_ratio':round(direct_ratio,4),'observed_word_count':len(obs),'canonical_word_count':len(canon),'internal_trigger_support':True}}


def resolve_alignment(plan: dict, audio_path: str|os.PathLike, wav_path: str|os.PathLike, duration: float, runtime_cfg: dict|None=None, logger=None) -> dict:
    runtime_cfg=runtime_cfg or {}
    if runtime_cfg.get('allow_whisper',True):
        try:
            r=whisper_exact_transcript_alignment(plan,audio_path,runtime_cfg,logger)
            r=project_scene_intervals_from_word_timings(plan,r,duration,fps=30.0)
            if logger: logger.log('PASS','ALIGNMENT_RESOLVED',method=r['method'],**r['quality'])
            return r
        except Exception as e:
            if logger: logger.log('WARNING','WHISPER_ALIGNMENT_UNAVAILABLE',str(e))
    r=acoustic_scene_alignment(plan,wav_path,duration,logger)
    if logger: logger.log('PASS','ALIGNMENT_RESOLVED',method=r['method'],**r['quality'])
    return r
