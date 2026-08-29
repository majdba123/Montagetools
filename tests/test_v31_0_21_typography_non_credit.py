from hexa_v31.typography import merge_support_typography

title={'pass':True,'title_qa':{'title_hard_failure_count':0},'events':[{'text_id':'TITLE_001','scene_id':'S1','text':'نتيجة','start_seconds':1,'end_seconds':2}]}
support={'opportunity_count':3,'events':[{'text_id':'TEXT_001','scene_id':'S1','text':'نتيجة','start_seconds':1.2,'end_seconds':2.1},{'text_id':'TEXT_002','scene_id':'S2','text':'قيمة واضحة','start_seconds':2.2,'end_seconds':3.4}]}
r=merge_support_typography(title,support)
assert r['title_fallback_event_count']==1,r
assert r['support_typography_event_count']==1,r
assert r['text_event_count']==2,r
assert next(x for x in r['events'] if x['text_event_kind']=='TYPOGRAPHY_SUPPORT')['semantic_credit']=='NONE',r
assert r['hard_rules']['title_only_coverage_computed_before_merge'] is True,r
print('V31_0_21_TYPOGRAPHY_NON_CREDIT_PASS')
