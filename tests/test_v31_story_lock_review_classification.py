from hexa_v31.pipeline import semantic_story_lock_status

review=semantic_story_lock_status({'coverage_gates_pass':False,'hard_failures':[]})
assert review['semantic_story_lock_review_required'] and not review['semantic_story_lock_hard_failure']
hard=semantic_story_lock_status({'coverage_gates_pass':False,'hard_failures':[{'delta_frames':7}]})
assert hard['semantic_story_lock_hard_failure'] and not hard['semantic_story_lock_review_required']
assert semantic_story_lock_status({'coverage_gates_pass':True,'hard_failures':[]})['semantic_story_lock_pass']
print('V31_STORY_LOCK_REVIEW_CLASSIFICATION_PASS')
