from hexa_v31.preset_authority import authority
A=authority();pm=A['preset_motion']
# The user's within-frame examples are the physical output authority. Execution endpoints
# must remain visibly inside frame; raw PRFPSET clip-space values are kept only for audit.
for n in ['WITHIN_LEFT_TO_MIDDLE','WITHIN_RIGHT_TO_MIDDLE','WITHIN_MIDDLE_TO_RIGHT','WITHIN_MIDDLE_TO_LEFT','WITHIN_MIDDLE_TO_UP','WITHIN_MIDDLE_TO_DOWN']:
    d=pm[n];a=d['start_norm'];b=d['end_norm']
    assert .10<=a[0]<=.90 and .18<=a[1]<=.82,(n,a)
    assert .10<=b[0]<=.90 and .18<=b[1]<=.82,(n,b)
    assert d.get('raw_prfpset_start_norm') is not None and d.get('raw_prfpset_end_norm') is not None,n
    assert d.get('endpoint_execution_mode')=='VISUAL_SAMPLE_CALIBRATED_WITH_PRFPSET_CURVE',n
# The disappearance visual sample is scale/opacity behavior, not a full-screen position throw.
d=pm['DISAPPEAR_DOWN_SCALE'];assert d['position_delta_norm']==[0.0,0.0],d
assert d.get('raw_prfpset_position_delta_norm') is not None
print('V31_VISUAL_SAMPLE_CALIBRATION_PASS')
