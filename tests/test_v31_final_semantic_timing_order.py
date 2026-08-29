from hexa_v31.preset_story_planner import _entry_fraction, perceptual_sync_qa

event={'event_id':'E','perceptual_hit_seconds':2.0,'preset_entry':{'name':'ENTRY_LEFT_TO_MIDDLE','start_seconds':1.1,'duration_seconds':1.0}}
assert perceptual_sync_qa([event],30.0)['pass']
# A later entry rewrite is detected symmetrically rather than silently keeping
# an obsolete atomic proof alive.
event['preset_entry']['start_seconds']=.6
qa=perceptual_sync_qa([event],30.0)
assert not qa['pass'] and qa['events'][0]['flag']=='VISUAL_PRECEDES_VOICE_RESULT',qa
assert abs((event['preset_entry']['start_seconds']+_entry_fraction(event)-2.0)*30)>6
print('V31_FINAL_SEMANTIC_TIMING_ORDER_PASS')
