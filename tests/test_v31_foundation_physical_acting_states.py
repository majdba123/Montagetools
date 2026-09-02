from __future__ import annotations
import pathlib,tempfile
import cv2
import numpy as np
from hexa_v31.physical_acting_verify import verify_physical_acting
from hexa_v31.preset_story_planner import _foundation_partition_motion_contract

with tempfile.TemporaryDirectory() as raw:
    video=str(pathlib.Path(raw)/'blank.mp4');writer=cv2.VideoWriter(video,cv2.VideoWriter_fourcc(*'mp4v'),30,(160,90))
    for _ in range(30):writer.write(np.full((90,160,3),255,np.uint8))
    writer.release()
    eligible={'event_id':'E','physical_id':'P','render_mode':'CHILD_PARTITION','translation_safe_after_occlusion':True,'independent_motion_allowed':True,'position_animated':False,'preset_actions':[]}
    base={'motion_dna_version':'HEXA_MOTION_DNA_V31_0_26_FOUNDATION_PARTITION_CHOREOGRAPHY','events':[eligible],'budget_summary':{}}
    case_a=verify_physical_acting(video,base);assert case_a['status']=='FAIL' and case_a['pass'] is False,case_a
    case_b=verify_physical_acting(video,{**base,'events':[]});assert case_b['status']=='NOT_APPLICABLE' and case_b['pass'] is True,case_b
    removed={**eligible,'foundation_motion_decision':'APPROVED_POSITION_ENTRY','position_animated':False,'preset_entry':{'name':'APPEAR_HIGH_SCALE'}}
    post_collision=_foundation_partition_motion_contract([removed]);assert post_collision['eligible_foundation_actor_count']==1 and post_collision['independently_animated_actor_count']==0 and post_collision['distinct_motion_signature_count']==0,post_collision
print('V31_FOUNDATION_PHYSICAL_ACTING_STATES_PASS')
