from types import SimpleNamespace
from hexa_v31.design_director import apply_audio_semantic_timing,build_title_plan,design_qa,finalize_anchor_coverage,stabilize_timeline_density

scene={'scene_id':'S1','script_span':{'text':'Secure payment confirmed'},'units':[{'unit_id':'HERO','type':'CONCEPT','role':'PRIMARY','semantic_name':'Secure payment','appear_trigger':{'phrase':'Secure payment','global_char_start':0,'global_char_end':14}}]}
plan={'project_id':'DIRECTOR','scenes':[scene],'canonical_script':{'text':'Secure payment confirmed'}}
alignment={'scene_timings':[{'scene_id':'S1','start':0.0,'end':4.0}],'word_timings':[{'text':'Secure','start':1.0,'end':1.3,'char_start':0,'char_end':6},{'text':'payment','start':1.31,'end':1.7,'char_start':7,'char_end':14}]}
event={'event_id':'S1_HERO','scene_id':'S1','visual_card_id':'C1','physical_id':'P1','semantic_unit_id':'HERO','semantic_scope_id':'S1::HERO','semantic_mapping_confidence':.99,'start_seconds':0.0,'end_seconds':4.0,'preset_entry':{'name':'APPEAR_HIGH_SCALE','duration_seconds':.8,'start_seconds':.44},'identity_key':'CONCEPT::SECURE_PAYMENT'}
motion={'events':[event],
        'visual_instances':[{'instance_id':'INSTANCE_S1_HERO','source_identity':'CONCEPT::SECURE_PAYMENT','source_asset_ref':'P1','physical_start_seconds':0.0,'physical_end_seconds':4.0,'readable_intervals':[{'start_seconds':0.0,'end_seconds':4.0}],'semantic_event_ids':['SEMANTIC_S1_HERO'],'state_ids':['S1'],'track':'VISUAL_INSTANCE'}],
        'semantic_events':[{'event_id':'SEMANTIC_S1_HERO','anchor_id':'ANCHOR_S1_HERO','anchor_time':1.0,'target_instance_id':'INSTANCE_S1_HERO','event_type':'ENTRY','semantic_role':'PRIMARY','source_authority':'SOURCE_SEMANTIC_CONTINUITY','preset':'APPEAR_HIGH_SCALE','motion_start':0.44,'perceptual_hit':1.0,'resulting_state':'S1','related_instance_ids':[]}],
        'scenes':[{'scene_id':'S1','visual_card_id':'C1'}],
        'visual_cards':{'cards':[{'card_id':'C1','start_seconds':0.0,'end_seconds':4.0,'source_scene_ids':['S1'],'story_phase_plan':{'phases':[{'phase_id':'P1'},{'phase_id':'P2'}]},'relationship_resolutions':[]}]}}
vision=[{'scene_id':'S1','units':[{'semantic_unit_id':'HERO','bbox_norm':[.10,.42,.36,.38]}]}]
report=stabilize_timeline_density(motion,apply_audio_semantic_timing(motion,plan,alignment))
assert report['pass'] and report['high_confidence_event_count']==1
assert abs(report['events'][0]['delta_frames'])<=3
titles=build_title_plan(SimpleNamespace(plan=plan),alignment,vision,motion)
assert titles['pass'] and titles['text_event_count']==1
t=titles['events'][0];assert .06<=t['x_norm']<=.94 and .06<=t['y_norm']<=.90 and t['text']=='Secure payment' and t['text_metrics']['fits'] and not t['generic_background_panel'],t
report=finalize_anchor_coverage(report,titles)
assert report['coverage_gates_pass'] and report['coverage']['physical_event_percent']>=60
qa=design_qa(motion,titles,report);assert qa['pass']
print('V31_0_9_SEMANTIC_PHASE_REPARTITION_COMPILER_PASS')
