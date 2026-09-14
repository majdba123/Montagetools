from hexa_v31.interaction.swept_geometry import swept_path_report
moving={'event_id':'MOVING','planned_rect_norm':[.432,.433,.11,.12],'physical_start_seconds':0.,'physical_end_seconds':4.}
blocker={'event_id':'BLOCKER','planned_rect_norm':[.24,.433,.15,.12],'physical_start_seconds':0.,'physical_end_seconds':4.}
clear={'event_id':'CLEAR','planned_rect_norm':[.80,.75,.10,.10],'physical_start_seconds':0.,'physical_end_seconds':4.}
bad=swept_path_report(moving,'WITHIN_MIDDLE_TO_LEFT',1.,1.9,[moving,blocker]);assert not bad['pass'] and bad['reason']=='INTERACTION_PATH_COLLISION' and bad['conflicts'],bad
good=swept_path_report(moving,'WITHIN_MIDDLE_TO_LEFT',1.,1.9,[moving,clear]);assert good['pass'],good
print('V31_PROBLEM2_SWEPT_GEOMETRY_PASS')
