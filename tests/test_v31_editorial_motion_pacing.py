from hexa_v31.editorial_motion import EditorialMotionGrammarDirector,PacingDirector,motion_family

events=[{'event_id':'A','perceptual_hit_seconds':.5,'end_seconds':1.8,'semantic_intent':'COMPARE','motion_energy':'HIGH','preset_entry':{'name':'ENTRY_LEFT_TO_MIDDLE','duration_seconds':.4}}, {'event_id':'B','perceptual_hit_seconds':1.5,'end_seconds':3.0,'semantic_intent':'REACTION','motion_energy':'MEDIUM','preset_entry':{'name':'APPEAR_HIGH_SCALE','duration_seconds':.5}}]
alignment={'word_timings':[{'start':.0,'end':.2},{'start':.3,'end':.5},{'start':1.4,'end':1.6}]}
a=EditorialMotionGrammarDirector().direct(events);b=EditorialMotionGrammarDirector().direct(events)
assert a==b and events[0]['editorial_motion_grammar'][0]=='ESTABLISH'
p=PacingDirector().diagnose(events,alignment);assert p['speech_words_per_second']>0 and p['per_phrase_visual_action_count']>0
assert motion_family('ENTRY_LEFT_TO_MIDDLE')=='ENTRY_DIRECTIONAL' and motion_family('APPEAR_HIGH_SCALE')=='ENTRY_SCALE'
print('V31_EDITORIAL_MOTION_PACING_PASS')
