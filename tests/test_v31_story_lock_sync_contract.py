from hexa_v31.design_director import _frac
from hexa_v31.preset_story_planner import _entry_fraction, perceptual_sync_qa

entry={'preset_entry':{'name':'ENTRY_LEFT_TO_MIDDLE','start_seconds':1.0,'duration_seconds':1.0},'perceptual_hit_seconds':1.9}
assert _frac(entry)==_entry_fraction(entry)==.90
assert perceptual_sync_qa([entry],30.0)['pass']
for anchor,flag in ((1.65,'VOICE_PRECEDES_VISUAL_RESULT'),(2.15,'VISUAL_PRECEDES_VOICE_RESULT')):
    row=dict(entry,perceptual_hit_seconds=anchor)
    qa=perceptual_sync_qa([row],30.0)
    assert not qa['pass'] and qa['events'][0]['flag']==flag,qa
print('V31_STORY_LOCK_SYNC_CONTRACT_PASS')
