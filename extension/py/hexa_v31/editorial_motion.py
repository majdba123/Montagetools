from __future__ import annotations

"""Deterministic editorial interpretation of already-certified motion plans."""
import statistics

_INTENTS={'ESTABLISH','INTRODUCE','PRESENT','ENTER','READ','ACCEPT','REVEAL','EMPHASIZE','COMPARE','CONNECT','TRANSFER','BLOCK','REJECT','SUCCESS','FAILURE','COUNT','INCREASE','DECREASE','REACTION','REACT','FOCUS','RESOLVE'}
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
    sentence=str(event.get('semantic_sentence_action') or '').upper()
    if sentence in _INTENTS:return sentence
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
            # This is a bounded preference over installed within-frame presets,
            # consumed by the planner's legal-effect selector.  It is never a
            # request to manufacture a new effect or bypass geometry QA.
            side=float((event.get('card_rest_position_norm') or [.5,.5])[0])
            if intent=='COMPARE': event['editorial_within_frame_preference']='WITHIN_MIDDLE_TO_LEFT' if side>=.5 else 'WITHIN_MIDDLE_TO_RIGHT'
            elif intent in {'REVEAL','EMPHASIZE','SUCCESS','FAILURE'}: event['editorial_within_frame_preference']='WITHIN_MIDDLE_TO_RIGHT' if side>=.5 else 'WITHIN_MIDDLE_TO_LEFT'
            elif intent=='REACTION': event['editorial_within_frame_preference']='WITHIN_MIDDLE_TO_UP'
            else:event['editorial_within_frame_preference']=None
            event['editorial_motion_planning_authority']='CERTIFIED_PRESET_ALTERNATIVES_ONLY'
            history.append({'family':family,'primitive':primitive})
        return {'version':self.version,'event_count':len(history),'motion_family_streak_max':max_streak,'same_primitive_streak_max':max_primitive,'families':sorted(set(x['family'] for x in history))}

class PacingDirector:
    version='HEXA_PHRASE_LOCAL_PACING_DIRECTOR_V2'
    _PUNCTUATION=('.',',',';','!', '?','،','؛','؟',':')

    @staticmethod
    def _word_value(word):
        return str(word.get('word') or word.get('text') or word.get('token') or '')

    def _phrases(self,words,events):
        if not words:return []
        gaps=[max(0.,float(b.get('start',0))-float(a.get('end',0))) for a,b in zip(words,words[1:])]
        positive_energy=[float(w.get('rms',w.get('energy',0)) or 0) for w in words if float(w.get('rms',w.get('energy',0)) or 0)>0]
        median_energy=statistics.median(positive_energy) if positive_energy else 0.
        groups=[];current=[]
        for index,word in enumerate(words):
            current.append(word);text=self._word_value(word).rstrip()
            gap=gaps[index] if index<len(gaps) else 0.
            if index==len(words)-1 or gap>=.35 or text.endswith(self._PUNCTUATION):
                groups.append((current,gap));current=[]
        phrases=[]
        for index,(group,pause_after) in enumerate(groups):
            start=float(group[0].get('start',0));end=max(start+.001,float(group[-1].get('end',start)))
            pause_before=max(0.,start-float(groups[index-1][0][-1].get('end',start))) if index else max(0.,start)
            energy_rows=[float(w.get('rms',w.get('energy',0)) or 0) for w in group]
            energy=sum(energy_rows)/max(1,len(energy_rows));rate=len(group)/max(.001,end-start)
            local_events=[e for e in events if start-.001<=float(e.get('perceptual_hit_seconds',e.get('start_seconds',0)))<=end+.001]
            density=len(local_events)/max(.25,end-start)
            emphasized=bool(median_energy and energy>=median_energy*1.28) or any(self._word_value(w).rstrip().endswith(('!','؟','?')) for w in group)
            if emphasized:energy_class='EMPHASIS';budget=1;hold=.68
            elif rate>=3.2 or density>=2.4:energy_class='FAST_DENSE';budget=0;hold=.72
            elif rate<=1.8 and end-start>=.65:energy_class='SLOW_EXPLANATORY';budget=2;hold=1.0
            else:energy_class='BALANCED';budget=1;hold=.82
            phrases.append({'phrase_id':f'PHRASE_{index+1:03d}','phrase_start':round(start,6),'phrase_end':round(end,6),'speech_rate':round(rate,4),'pause_before':round(pause_before,4),'pause_after':round(pause_after,4),'energy':round(energy,6),'semantic_density':round(density,4),'allowed_discretionary_actions':budget,'minimum_readable_hold':hold,'motion_energy_class':energy_class,'emphasis':emphasized,'word_count':len(group)})
        return phrases

    def diagnose(self,events,alignment,fps=30.0):
        words=sorted(alignment.get('word_timings') or [],key=lambda w:float(w.get('start',0)))
        duration=max([float(e.get('end_seconds',0)) for e in events]+[float(w.get('end',0)) for w in words]+[0.001])
        pauses=[max(0.,float(b.get('start',0))-float(a.get('end',0))) for a,b in zip(words,words[1:])]
        actions=sorted(float(e.get('perceptual_hit_seconds',e.get('start_seconds',0))) for e in events)
        gaps=[max(0.,b-a) for a,b in zip(actions,actions[1:])];dead=max(gaps or [duration])
        bursts=[max(1,int(round(float((e.get('preset_entry') or {}).get('duration_seconds') or 0)*fps))) for e in events if e.get('preset_entry')]
        short=sum(1 for b in bursts if b<=3);high=sum(1 for e in events if str(e.get('motion_energy')).upper()=='HIGH')
        phrases=self._phrases(words,events);phrase_count=max(1,len(phrases));return {'version':self.version,'speech_words_per_second':round(len(words)/duration,4),'phrase_count':phrase_count,'phrases':phrases,'pause_count':len(pauses),'pause_motion_ratio':round(sum(1 for p in pauses if p>0.35)/max(1,len(pauses)),4),'per_phrase_visual_action_count':round(len(events)/phrase_count,4),'high_motion_single_frame_burst_ratio':round(sum(1 for b in bursts if b==1)/max(1,len(bursts)),4),'high_motion_short_burst_ratio':round(short/max(1,len(bursts)),4),'motion_burst_duration_p50':statistics.median(bursts) if bursts else 0,'motion_burst_duration_p90':sorted(bursts)[max(0,int(.9*len(bursts))-1)] if bursts else 0,'longest_planned_dead_hold':round(dead,4),'motion_energy_variance':round(high/max(1,len(events))*(1-high/max(1,len(events))),4)}

    def plan(self,events,alignment,fps=30.0):
        """Commit deterministic discretionary-action budgets before selection."""
        report=self.diagnose(events,alignment,fps);phrases=report['phrases']
        ordered=sorted(events,key=lambda e:(float(e.get('perceptual_hit_seconds',0)),str(e.get('event_id'))))
        used={p['phrase_id']:0 for p in phrases};last_strong=-999.;allowed=0
        for event in ordered:
            hit=float(event.get('perceptual_hit_seconds',event.get('start_seconds',0)))
            phrase=next((p for p in phrases if p['phrase_start']-.001<=hit<=p['phrase_end']+.001),None)
            eligible=not event.get('suppressed_by_card_density') and str(event.get('attention_priority') or '').upper()=='PRIMARY'
            if phrase is None:
                # A silence is not an animation cue. Only an already-authored
                # semantic resolve/handoff remains eligible in the gap.
                justified=_intent(event) in {'RESOLVE','TRANSFER','CONNECT'}
                permit=bool(eligible and justified)
                mode='SEMANTIC_PAUSE_HANDOFF' if permit else 'SILENCE_NO_AUTOMATIC_MOTION';spacing=.60;hold=.90
            else:
                budget=int(phrase['allowed_discretionary_actions']);spacing=.55 if phrase['motion_energy_class']=='FAST_DENSE' else .34
                strong=_intent(event) in {'EMPHASIZE','REVEAL','REJECT','ACCEPT','BLOCK','SUCCESS','FAILURE'}
                too_close=strong and hit-last_strong<spacing
                permit=bool(eligible and used[phrase['phrase_id']]<budget and not too_close)
                if permit:used[phrase['phrase_id']]+=1
                if permit and strong:last_strong=hit
                mode=phrase['motion_energy_class'];hold=float(phrase['minimum_readable_hold'])
                event['pacing_phrase_id']=phrase['phrase_id']
            event['pacing_discretionary_action_allowed']=permit
            event['pacing_action_spacing_seconds']=round(spacing,4);event['pacing_minimum_readable_hold']=round(hold,4);event['pacing_mode']=mode
            allowed+=int(permit)
        report.update({'planning_authority':'PHRASE_LOCAL_BOUNDED_DISCRETIONARY_ACTION_CONSTRAINTS','discretionary_action_budget':allowed,'competing_impact_suppression':any(p['motion_energy_class']=='FAST_DENSE' for p in phrases),'silence_is_not_motion_cue':True,'deterministic':True})
        return report
