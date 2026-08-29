from hexa_v31.design_director import compile_semantic_timeline

plan={'scenes':[{'scene_id':'S1','units':[{'unit_id':'U1','semantic_name':'source concept'}]}]}
event={'event_id':'E1','scene_id':'S1','semantic_unit_id':'U1','physical_id':'P1','semantic_role':'PRIMARY','semantic_mapping_confidence':.95,'visual_card_id':'C1','start_seconds':1.0,'end_seconds':3.0,'perceptual_hit_seconds':1.72,'preset_entry':{'name':'ENTRY_LEFT_TO_MIDDLE','start_seconds':1.0,'duration_seconds':1.0}}
motion={'events':[event],'visual_cards':{'cards':[{'card_id':'C1','start_seconds':0.0,'end_seconds':3.0}]},'visual_instances':[{'instance_id':'INSTANCE_P1','semantic_event_ids':['SEMANTIC_E1']}],'semantic_events':[{'event_id':'SEMANTIC_E1','anchor_id':'ANCHOR_E1','anchor_time':1.72,'target_instance_id':'INSTANCE_P1','semantic_role':'PRIMARY'}],'atomic_handoff_optimizer':{}}
report=compile_semantic_timeline(motion,plan,{'word_timings':[]},30.0)
assert report['events'][0]['satisfaction']=='OBJECT',report
assert report['events'][0]['participating_semantic_event_ids']==['SEMANTIC_E1'],report
assert report['events'][0]['anchor_id']=='ANCHOR_E1',report
print('V31_SEMANTIC_LEDGER_ACCOUNTING_PASS')
