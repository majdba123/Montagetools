from __future__ import annotations

"""Deterministic editorial interpretation of already-certified motion plans."""
import statistics

_INTENTS={'ESTABLISH','INTRODUCE','REVEAL','EMPHASIZE','COMPARE','CONNECT','TRANSFER','BLOCK','REJECT','SUCCESS','FAILURE','COUNT','INCREASE','DECREASE','REACTION','FOCUS','RESOLVE'}
_GRAMMAR={
    'COMPARE':('ESTABLISH','YIELD_SPACE','REVEAL','MIRRORED_SETTLE','RESOLVE'),
    'REVEAL':('ESTABLISH','REVEAL','EMPHASIZE','READABLE_HOLD'),
    'REACTION':('CAUSE','REACTION','FOCUS','RESOLVE'),
    'TRANSFER':('ESTABLISH','CONNECT','TRANSFER','RESOLVE'),
    'BLOCK':('ESTABLISH','BLOCK','FOCUS','RESOLVE'),
    'REJECT':('ESTABLISH','REJECT','FOCUS','RESOLVE'),
    'SUCCESS':('ESTABLISH','EMPHASIZE','RESOLVE'),
    'FAILURE':('ESTABLISH','EMPHASIZE','RESOLVE'),
}

def motion_family(name):
    n=str(name or '').upper()
    if not n:return 'STATIC'
    if 'EXIT' in n:return 'EXIT_FADE' if 'FADE' in n else 'EXIT_DIRECTIONAL'
    if 'ENTRY' in n or 'APPEAR' in n:return 'ENTRY_SCALE' if 'SCALE' in n or 'APPEAR' in n else 'ENTRY_DIRECTIONAL'
    if 'FADE' in n:return 'FADE'
    if any(x in n for x in ('TRANSFER','HANDOFF','CONNECT')):return 'RELATIONSHIP_TRANSFER'
    if any(x in n for x in ('REACT','POSE')):return 'REACTION'
    return 'WITHIN_FRAME_FOCUS'

def _intent(event):
    raw=' '.join(str(event.get(k) or '') for k in ('semantic_intent','narrative_function','relationship')).upper()
    return next((x for x in _INTENTS if x in raw),'INTRODUCE')

class EditorialMotionGrammarDirector:
    version='HEXA_EDITORIAL_MOTION_GRAMMAR_V1'
    def direct(self,events):
        history=[];streak=0;max_streak=0;primitive_streak=0;max_primitive=0
        for event in sorted(events,key=lambda e:(float(e.get('perceptual_hit_seconds',0)),str(e.get('event_id')))):
            intent=_intent(event);entry=(event.get('preset_entry') or {}).get('name');within=[a.get('name') for a in (event.get('preset_actions') or []) if a.get('name')]
            family=motion_family(within[0] if within else entry);primitive=str(within[0] if within else entry or 'STATIC')
            streak=streak+1 if history and history[-1]['family']==family else 1;primitive_streak=primitive_streak+1 if history and history[-1]['primitive']==primitive else 1
            max_streak=max(max_streak,streak);max_primitive=max(max_primitive,primitive_streak)
            event['editorial_motion_intent']=intent;event['editorial_motion_grammar']=list(_GRAMMAR.get(intent,('ESTABLISH',intent,'READABLE_HOLD')));event['motion_family']=family;event['motion_family_streak']=streak;event['motion_primitive_streak']=primitive_streak
            history.append({'family':family,'primitive':primitive})
        return {'version':self.version,'event_count':len(history),'motion_family_streak_max':max_streak,'same_primitive_streak_max':max_primitive,'families':sorted(set(x['family'] for x in history))}

class PacingDirector:
    version='HEXA_PACING_DIRECTOR_V1'
    def diagnose(self,events,alignment,fps=30.0):
        words=sorted(alignment.get('word_timings') or [],key=lambda w:float(w.get('start',0)))
        duration=max([float(e.get('end_seconds',0)) for e in events]+[float(w.get('end',0)) for w in words]+[0.001])
        pauses=[max(0.,float(b.get('start',0))-float(a.get('end',0))) for a,b in zip(words,words[1:])]
        actions=sorted(float(e.get('perceptual_hit_seconds',e.get('start_seconds',0))) for e in events)
        gaps=[max(0.,b-a) for a,b in zip(actions,actions[1:])];dead=max(gaps or [duration])
        bursts=[max(1,int(round(float((e.get('preset_entry') or {}).get('duration_seconds') or 0)*fps))) for e in events if e.get('preset_entry')]
        short=sum(1 for b in bursts if b<=3);high=sum(1 for e in events if str(e.get('motion_energy')).upper()=='HIGH')
        phrase_count=max(1,len(words));return {'version':self.version,'speech_words_per_second':round(len(words)/duration,4),'phrase_count':phrase_count,'pause_count':len(pauses),'pause_motion_ratio':round(sum(1 for p in pauses if p>0.35)/max(1,len(pauses)),4),'per_phrase_visual_action_count':round(len(events)/phrase_count,4),'high_motion_single_frame_burst_ratio':round(sum(1 for b in bursts if b==1)/max(1,len(bursts)),4),'high_motion_short_burst_ratio':round(short/max(1,len(bursts)),4),'motion_burst_duration_p50':statistics.median(bursts) if bursts else 0,'motion_burst_duration_p90':sorted(bursts)[max(0,int(.9*len(bursts))-1)] if bursts else 0,'longest_planned_dead_hold':round(dead,4),'motion_energy_variance':round(high/max(1,len(events))*(1-high/max(1,len(events))),4)}
