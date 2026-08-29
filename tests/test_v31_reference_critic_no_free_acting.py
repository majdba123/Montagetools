from hexa_v31.reference_critic import score_reference_10
profile={'quality_floor':{'motion_mean':{'target_min':.02,'target_max':.025},'nonwhite_occupancy_median_percent':{'target_min':20,'target_max':29},'low_motion_percent':{'target_max':48},'static_run_p90_seconds':{'target_max':1.35},'static_run_max_seconds':{'target_max':2.5},'motion_p95':{'target_min':.075,'target_max':.12},'severe_isolated_motion_spikes_per_minute':{'target_max':3}}}
metrics={'motion_activity':.022,'low_motion_percent':40,'p90_static_hold_seconds':1.0,'max_static_hold_seconds':2.0,'median_nonwhite_occupancy_percent':25,'motion_p95':.09,'severe_isolated_motion_spikes_per_minute':2,'localized_motion_ratio':.7,'full_frame_motion_ratio':.05,'meaningful_change_gap_p90_seconds':1.0,'white_wash_event_count':0,'duration_seconds':60}
r0=score_reference_10(metrics,profile,physical_acting={'planned_physical_actions':0,'verified_ratio':1.0})
assert 'physical_acting_survival' not in r0['components'],r0
r1=score_reference_10(metrics,profile,physical_acting={'planned_physical_actions':2,'verified_ratio':.5})
assert r1['components']['physical_acting_survival']==5.0,r1
assert r1['version']=='1.2-V31'
print('V31_REFERENCE_CRITIC_NO_FREE_ACTING_PASS')
