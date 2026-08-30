from hexa_v31.editorial_motion import PacingDirector

def event(event_id,hit,intent='REVEAL'):
    return {'event_id':event_id,'perceptual_hit_seconds':hit,'start_seconds':hit-.1,'end_seconds':hit+1.,'semantic_intent':intent,'attention_priority':'PRIMARY','preset_entry':{'name':'APPEAR_HIGH_SCALE','duration_seconds':.5}}

director=PacingDirector()
words=[
    {'word':'fast','start':0.,'end':.12,'energy':.3},{'word':'dense','start':.13,'end':.25,'energy':.3},{'word':'clause,','start':.26,'end':.38,'energy':.3},
    {'word':'slow','start':1.0,'end':1.7,'energy':.3},{'word':'explanation.','start':1.9,'end':2.8,'energy':.3},
    {'word':'emphasis!','start':3.4,'end':3.9,'energy':.9},{'word':'handoff','start':5.0,'end':5.6,'energy':.3},
]
events=[event('FAST_A',.15),event('FAST_B',.30),event('SLOW_A',1.2),event('SLOW_B',2.2),event('EMPHASIS_A',3.6),event('EMPHASIS_B',3.75),event('SILENCE',4.5),event('RESOLVE',4.6,'RESOLVE')]
report=director.plan(events,{'word_timings':words})
phrases=report['phrases']
assert phrases[0]['motion_energy_class']=='FAST_DENSE' and phrases[0]['allowed_discretionary_actions']==0
assert phrases[1]['motion_energy_class']=='SLOW_EXPLANATORY' and phrases[1]['allowed_discretionary_actions']==2
assert phrases[2]['motion_energy_class']=='EMPHASIS' and phrases[2]['allowed_discretionary_actions']==1
assert not events[0]['pacing_discretionary_action_allowed'] and not events[1]['pacing_discretionary_action_allowed']
assert events[2]['pacing_discretionary_action_allowed'] and events[3]['pacing_discretionary_action_allowed']
assert sum(e['pacing_discretionary_action_allowed'] for e in events[4:6])==1
assert events[6]['pacing_mode']=='SILENCE_NO_AUTOMATIC_MOTION' and not events[6]['pacing_discretionary_action_allowed']
assert events[7]['pacing_mode']=='SEMANTIC_PAUSE_HANDOFF' and events[7]['pacing_discretionary_action_allowed']
assert director.plan([dict(e) for e in events],{'word_timings':words})['phrases']==phrases
print('V31_PHRASE_LOCAL_PACING_PASS')
