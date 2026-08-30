import copy

from hexa_v31.semantic_sentence import SemanticVisualSentenceCompiler
from hexa_v31.editorial_motion import EditorialMotionGrammarDirector
from hexa_v31.preset_story_planner import rank_legal_effects

def physical(action):
    return [
        {'event_id':'SUBJECT','scene_id':'S','visual_card_id':'C','attention_priority':'PRIMARY','semantic_intent':action,
         'semantic_role':'ACTOR','semantic_scope_id':'S::A','card_rest_position_norm':[.5,.5],'perceptual_hit_seconds':1.,
         'preset_entry':{'name':'APPEAR_HIGH_SCALE','duration_seconds':.55},'preset_actions':[]},
        {'event_id':'OBJECT','scene_id':'S','visual_card_id':'C','attention_priority':'SUPPORTING','semantic_role':'TARGET',
         'semantic_scope_id':'S::B','card_rest_position_norm':[.72,.5],'perceptual_hit_seconds':1.6,
         'preset_entry':{'name':'APPEAR_HIGH_SCALE','duration_seconds':.55},'preset_actions':[]},
    ]

compare=physical('COMPARE');reveal=physical('REVEAL')
ca=SemanticVisualSentenceCompiler().compile(compare);ra=SemanticVisualSentenceCompiler().compile(reveal)
EditorialMotionGrammarDirector().direct(compare);EditorialMotionGrammarDirector().direct(reveal)
assert ca['sentences'][0]['action']=='COMPARE' and ra['sentences'][0]['action']=='REVEAL'
assert ca['sentences'][0]['subject_event_id']=='SUBJECT' and ca['sentences'][0]['object_event_id']=='OBJECT'
assert compare[0]['editorial_motion_intent']=='COMPARE' and reveal[0]['editorial_motion_intent']=='REVEAL'
choices=('WITHIN_MIDDLE_TO_LEFT','WITHIN_MIDDLE_TO_RIGHT')
compare_order=rank_legal_effects(choices,[],compare[0],compare[1])
reveal_order=rank_legal_effects(choices,[],reveal[0],reveal[1])
assert compare_order!=reveal_order
assert set(compare_order)==set(reveal_order)==set(choices)
assert ca['unsupported_motion_invention_count']==0

static=physical('UNSUPPORTED_ACTION')
report=SemanticVisualSentenceCompiler().compile(static)
assert report['sentences'][0]['action']=='PRESENT'

print('V31_SEMANTIC_VISUAL_SENTENCE_COMPILER_PASS')
