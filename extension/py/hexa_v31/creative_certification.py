from __future__ import annotations
import json, pathlib
import cv2
cv2.setNumThreads(1)
import numpy as np
from .util import write_json
from .visual_choreography import visual_choreography_qa


def _frame(cap,t):
    cap.set(cv2.CAP_PROP_POS_MSEC,max(0.0,float(t))*1000.0);ok,fr=cap.read();return fr if ok else None


def verify_typography_survival(video_path,text_plan):
    cap=cv2.VideoCapture(str(video_path));rows=[]
    if not cap.isOpened():return {'pass':False,'planned':len(text_plan.get('events') or []),'pixel_verified':0,'rows':[],'reason':'VIDEO_OPEN_FAILED'}
    fps=float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    for e in text_plan.get('events') or []:
        st=float(e.get('start_seconds',0));impact=float(e.get('impact_seconds',st));en=float(e.get('end_seconds',st));x=float(e.get('x_norm',0));y=float(e.get('y_norm',0));w=float(e.get('w_norm',0));h=float(e.get('h_norm',0))
        before=_frame(cap,max(0,st-2/fps));visible=_frame(cap,min(en-2/fps,max(st+4/fps,impact+2/fps)))
        ok=False;change=ink=0.0
        if before is not None and visible is not None and w>0 and h>0:
            ih,iw=visible.shape[:2];x0=max(0,int(x*iw));y0=max(0,int(y*ih));x1=min(iw,int((x+w)*iw));y1=min(ih,int((y+h)*ih))
            a=before[y0:y1,x0:x1];b=visible[y0:y1,x0:x1]
            if a.size and b.size:
                d=cv2.absdiff(cv2.cvtColor(a,cv2.COLOR_BGR2GRAY),cv2.cvtColor(b,cv2.COLOR_BGR2GRAY));change=float(np.mean(d>=8));ink=float(np.mean(np.min(b,axis=2)<210));ok=bool(change>=.010 and ink>=.006 and st<=impact<=en)
        rows.append({'text_id':e.get('text_id'),'visual_card_id':e.get('visual_card_id'),'start_seconds':st,'impact_seconds':impact,'end_seconds':en,'changed_pixel_ratio':round(change,6),'dark_ink_ratio':round(ink,6),'pass':ok})
    cap.release();planned=len(rows);verified=sum(1 for x in rows if x['pass']);ratio=verified/max(1,planned)
    return {'pass':bool(planned>0 and ratio>=.90),'planned':planned,'pixel_verified':verified,'verification_ratio':round(ratio,4),'rows':rows,'authority':'EXPECTED_TEXT_BBOX_PIXEL_SURVIVAL'}


def cutout_execution_qa(render_map):
    rows=[];seen=set()
    for e in render_map.get('events') or []:
        path=str(e.get('source_path') or '');key=(path,str(e.get('render_source_kind') or ''))
        if not path or key in seen:continue
        seen.add(key);kind=str(e.get('render_source_kind') or 'SAFE_FALLBACK');im=cv2.imread(path,cv2.IMREAD_UNCHANGED)
        alpha_ok=bool(im is not None and im.ndim==3 and im.shape[2]==4)
        transparent=0.0;tight=False;white_rectangle=False
        if alpha_ok:
            a=im[:,:,3];transparent=float(np.mean(a<8));yy,xx=np.where(a>8)
            if len(xx):
                bbox_area=(int(xx.max())-int(xx.min())+1)*(int(yy.max())-int(yy.min())+1);tight=bool(bbox_area/max(1,a.shape[0]*a.shape[1])<.92 and transparent>=.02)
                opaque=a>245;white_rectangle=bool(np.mean(np.all(im[:,:,:3]>248,axis=2)&opaque)>.08)
        expected=kind!='FULL_SCENE_BACKGROUND';ok=bool((not expected) or (alpha_ok and tight and not white_rectangle))
        rows.append({'event_id':e.get('event_id'),'render_source_kind':kind,'alpha_exists':alpha_ok,'transparent_fraction':round(transparent,6),'tight_bbox':tight,'opaque_white_rectangle':white_rectangle,'pass':ok})
    independent=[x for x in rows if x['render_source_kind']!='FULL_SCENE_BACKGROUND'];fallback=[x for x in rows if x['render_source_kind']=='FULL_SCENE_BACKGROUND']
    ratio=len(fallback)/max(1,len(rows));return {'pass':bool(rows and all(x['pass'] for x in rows) and ratio<=.35),'rows':rows,'independent_object_events':len(independent),'isolated_layer_events':sum(1 for x in rows if x['render_source_kind'] in ('ISOLATED_ALPHA_LAYER','CONNECTED_GROUP_LAYER','ATOMIC_LAYER')),'full_scene_fallback_events':len(fallback),'fallback_ratio':round(ratio,4)}


def certify_creative_release(video_path,motion,text_plan,render_map,choreography_report,pixel_metrics,preview_score,perceptual,physical_acting,reference_score,profile_path,out_json):
    profile=json.loads(pathlib.Path(profile_path).read_text(encoding='utf-8'));chqa=visual_choreography_qa(choreography_report,pixel_metrics,profile);typo=verify_typography_survival(video_path,text_plan);cutout=cutout_execution_qa(render_map)
    cards=list((motion.get('visual_cards') or {}).get('cards') or []);events=[e for e in motion.get('events') or [] if not e.get('suppressed_by_card_density')];meaningful=[]
    for c in cards:
        cid=str(c.get('card_id'));local=[e for e in events if str(e.get('visual_card_id'))==cid];meaningful.append(bool(any(not e.get('lifecycle_state_only') for e in local) or any(e.get('focus_beats') for e in local) or any(str(t.get('visual_card_id'))==cid for t in text_plan.get('events') or [])))
    meaningful_ratio=sum(meaningful)/max(1,len(meaningful));persistence_ratio=1.0-meaningful_ratio
    physical=motion.get('final_physical_certification') or {};repairs=physical.get('repairs') or [];planned=sum(1 for e in events for _ in ((e.get('preset_actions') or [])+(e.get('focus_beats') or [])))
    removed=sum(1 for r in repairs if r.get('type')=='REMOVE_OPTIONAL_CHOREOGRAPHY');surviving=max(0,planned-removed)
    typography_plan_ok=bool(text_plan.get('pass') and int(text_plan.get('text_event_count') or 0)>0 and int(text_plan.get('used_support_opportunity_count') or 0)>=max(1,int(.35*max(1,int(text_plan.get('opportunity_count') or 0)))))
    gates={
      'REFERENCE_FIDELITY_EXIT':bool(preview_score.get('pass') and reference_score.get('pass_8_plus')),
      'PIXEL_MOTION_SURVIVAL_EXIT':bool(physical_acting.get('pass')),
      'CHOREOGRAPHY_QA_EXIT':bool(chqa.get('pass')),
      'STATIC_POSTER_QA_EXIT':bool(float(pixel_metrics.get('p90_static_hold_seconds',999))<=1.35 and float(pixel_metrics.get('max_static_hold_seconds',999))<=2.5),
      'TYPOGRAPHY_PLAN_EXIT':typography_plan_ok,
      'TYPOGRAPHY_RENDER_SURVIVAL_EXIT':bool(typo.get('pass')),
      'CUTOUT_EXECUTION_EXIT':bool(cutout.get('pass')),
      'BEAT_SYNC_EXIT':bool((motion.get('perceptual_sync_qa') or {}).get('pass')),
      'POST_PHYSICAL_CREATIVE_SURVIVAL_EXIT':bool(physical.get('pass') and planned>0 and surviving/max(1,planned)>=.80),
      'V1_1_INTERVAL_UTILIZATION_EXIT':bool(meaningful_ratio>=.70 and persistence_ratio<=.30),
      'COMPOSITION_VARIETY_EXIT':bool(int(choreography_report.get('composition_archetype_diversity',0))>=3 and int(choreography_report.get('three_card_archetype_repeat_count',99))<=2),
    }
    result={'schema':'HEXA_V31_CREATIVE_RELEASE_CERTIFICATION','version':'1.0','status':'PASS' if all(gates.values()) else 'FAIL','pass':all(gates.values()),'gates':{k:{'pass':v,'exit':0 if v else 1} for k,v in gates.items()},'visual_choreography_qa':chqa,'typography_render_survival':typo,'cutout_execution_qa':cutout,'interval_utilization':{'meaningful_interval_change_ratio':round(meaningful_ratio,4),'persistence_only_ratio':round(persistence_ratio,4)},'post_physical_survival':{'planned_action_count':planned,'optional_actions_removed':removed,'surviving_action_count':surviving}}
    write_json(out_json,result);return result
