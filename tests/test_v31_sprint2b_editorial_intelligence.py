import tempfile,wave,os
import numpy as np
from hexa_v31.semantic_sentence import SemanticVisualSentenceCompiler
from hexa_v31.typography import ArabicPhraseCompletenessAnalyzer,_strip_weak_prefix
from hexa_v31.audio_prosody import AudioProsodyAnalyzer
from hexa_v31.editorial_motion import PacingDirector
from hexa_v31.visual_affordance import classify,legal_operations
from hexa_v31.beat_choreography import BeatChoreographyCompiler
from hexa_v31.composition_qa import viewport_clipping_qa

def event(i,intent,clause=''):
 return {'event_id':i,'scene_id':i,'visual_card_id':i,'attention_priority':'PRIMARY','semantic_intent':intent,'canonical_clause':clause,'semantic_scope_id':i,'perceptual_hit_seconds':.5,'start_seconds':0.,'end_seconds':1.,'card_rest_position_norm':[.5,.5],'source_bbox_norm':[.3,.3,.2,.2],'layout_scale_multiplier':1.,'preset_entry':{'name':'APPEAR_HIGH_SCALE','start_seconds':0.,'duration_seconds':.5},'preset_actions':[]}
rows=[event('READ','READ','افحص القيمة'),event('BLOCK','ACCEPT','لا يسمح بتمريرها'),event('COMPARE','COMPARE','قارن القيمة')];report=SemanticVisualSentenceCompiler().compile(rows)
assert {x['scene_id']:x['action'] for x in report['sentences']}=={'READ':'READ','BLOCK':'REJECT','COMPARE':'COMPARE'} and report['present_ratio']==0
a=ArabicPhraseCompletenessAnalyzer();phrase='ما يسمح بتمريرها';assert a.assess(phrase,phrase)['pass'] and _strip_weak_prefix(phrase)==phrase and not a.assess('يسمح بتمريرها',phrase)['pass']
f=tempfile.NamedTemporaryFile(suffix='.wav',delete=False);f.close()
with wave.open(f.name,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes((np.sin(np.linspace(0,1000,32000))*12000).astype('<i2').tobytes())
try:
 alignment={'word_timings':[{'start':0.,'end':.2,'word':'fast'},{'start':.21,'end':.4,'word':'words,'},{'start':.9,'end':1.,'word':'slow'},{'start':1.5,'end':1.9,'word':'clause.'}]};prosody=AudioProsodyAnalyzer().analyze(f.name,alignment);assert prosody['nonzero_energy_count']==4
 for w,p in zip(alignment['word_timings'],prosody['word_features']):w.update(p)
 pace=PacingDirector().plan([event('P', 'READ')],alignment);assert any(p['energy']>0 for p in pace['phrases'])
finally:os.unlink(f.name)
u={'render_mode':'ROOT_ATOMIC','animation_safe':False,'reveal_safe':True};assert classify(u)=='CONNECTED_REVEAL_ONLY' and 'TRANSLATE' not in legal_operations(classify(u))
beats=BeatChoreographyCompiler().compile(rows,report['sentences']);assert beats['consumed_by_planner'] and beats['beats'][0]['beat_sequence'][0]=='ESTABLISH'
assert viewport_clipping_qa([event('V','READ')])['pass']
print('V31_SPRINT2B_EDITORIAL_INTELLIGENCE_PASS')
