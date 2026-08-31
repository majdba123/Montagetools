from __future__ import annotations
import json, pathlib, statistics

ROOT=pathlib.Path(__file__).resolve().parent
RUN=pathlib.Path(r"C:\Users\INTEL CENTER\AppData\Local\HEXA\VideoBuilderV31\builds\f4bd7a84c350_6332a4da1726\runs\20260831-160354-35f309f6")
def load(p):
    with pathlib.Path(p).open(encoding="utf-8-sig") as f:return json.load(f)
cur=load(ROOT/'current_video_metrics.json');a=load(ROOT/'reference_a_metrics.json');b=load(ROOT/'reference_b_metrics.json')
motion=load(RUN/'HEXA_MOTION_PLAN_V31.json');ch=load(RUN/'HEXA_V31_PREMIUM_VISUAL_CHOREOGRAPHY_REPORT.json')
typo=load(RUN/'HEXA_V31_SELECTIVE_TYPOGRAPHY_PLAN.json');vision=load(RUN/'scene_vision_report_v31.json')
acting=load(RUN/'HEXA_V31_PHYSICAL_ACTING_VERIFICATION.json');perceptual=load(RUN/'HEXA_V31_PERCEPTUAL_STORY_QA.json')
events=[e for e in motion.get('events',[]) if not e.get('suppressed_by_card_density')]
entries=[e for e in events if e.get('preset_entry')]
spatial=[e for e in entries if e.get('position_animated')]
exits=[e for e in events if e.get('preset_exit')]
spatial_exits=[e for e in exits if str((e.get('preset_exit') or {}).get('name','')).startswith(('EXIT_','DISAPPEAR_LEFT','DISAPPEAR_RIGHT'))]
families=[str((e.get('preset_entry') or {}).get('name','NONE')) for e in entries]
streak=0;best=0;prev=None
for x in families:
    streak=streak+1 if x==prev else 1;best=max(best,streak);prev=x
units=[u for s in vision.get('scenes',[]) for u in s.get('units',[])]
hints=[r for s in vision.get('scenes',[]) for r in (((s.get('artifacts') or {}).get('hint_guided_extraction') or {}).get('regions') or [])]
alpha=sum(1 for u in units if u.get('matting') and u.get('layer_path'))
tight=sum(1 for u in units if (u.get('bbox_norm') or [0,0,1,1])[2]*(u.get('bbox_norm') or [0,0,1,1])[3] < .72)
full=sum(1 for u in units if (u.get('bbox_norm') or [0,0,1,1])[2]*(u.get('bbox_norm') or [0,0,1,1])[3] >= .72)
cards=(motion.get('visual_cards') or {}).get('cards') or []
dur=max(.001,float(cur['duration_seconds']));planned=len(typo.get('events') or [])
report={
 'schema':'HEXA_V31_CREATIVE_DIFFERENTIAL_REPORT','version':'1.0','evidence_authority':'PHYSICAL_MP4_PIXELS_PLUS_CORRELATED_COMMITTED_PLAN',
 'current_output':{'path':cur['video'],'metrics':cur,'creative_gate':'FAIL','reference_proxy_score_percent':10.0},
 'references':{'reference_a':a,'reference_b':b,'last_hexa_baseline':{'status':'NOT_FOUND_IN_SEARCHED_DOCUMENTS_OR_DESKTOP'}},
 'motion_differential':{k:{'current':cur[k],'reference_a':a[k],'reference_b':b[k]} for k in ('motion_activity','low_motion_percent','p90_static_hold_seconds','max_static_hold_seconds','motion_p95','meaningful_change_gap_p90_seconds','meaningful_change_gap_max_seconds','localized_motion_ratio','full_frame_motion_ratio')},
 'choreography':{'planned_progressive_reveals':ch.get('progressive_reveal_count',0),'progressive_reveals_per_minute_claimed':round(60*ch.get('progressive_reveal_count',0)/dur,3),'within_frame_recompositions_per_minute':round(60*ch.get('within_frame_recomposition_count',0)/dur,3),'object_handoffs':ch.get('handoff_count',0),'full_visual_resets':ch.get('full_state_reset_count',0),'fade_only_transition_ratio':round(ch.get('fade_only_transition_count',0)/max(1,len(entries)+len(exits)),4),'spatial_entry_ratio':round(len(spatial)/max(1,len(entries)),4),'spatial_exit_ratio':round(len(spatial_exits)/max(1,len(exits)),4),'effect_family_diversity':ch.get('effect_family_diversity',0),'consecutive_identical_preset_streak':best,'static_poster_risk_cards_plan_claim':ch.get('static_poster_risk_count',0),'low_optical_impact_cards':ch.get('low_optical_impact_count',0),'pixel_active_frame_ratio':round(cur['active_frame_count']/cur['frame_count'],4),'plan_pixel_contradiction':True},
 'typography':{'available_semantic_text_opportunities':typo.get('opportunity_count',0),'planned_events':planned,'events_per_visual_card':round(planned/max(1,len(cards)),4),'readable_text_seconds_per_minute_planned':round(60*sum(max(0,float(x.get('readable_end_seconds',x.get('end_seconds',0)))-float(x.get('readable_start_seconds',x.get('start_seconds',0)))) for x in typo.get('events',[]))/dur,3),'cards_with_meaningful_text':len({str(x.get('visual_card_id')) for x in typo.get('events',[])}),'title_count':typo.get('title_fallback_event_count',0),'support_count':typo.get('support_typography_event_count',0),'invalid_timing_events':[x.get('text_id') for x in typo.get('events',[]) if float(x.get('impact_seconds',0))<float(x.get('start_seconds',0))],'pixel_verified':'REQUIRES_NEW_HARD_RENDER_SURVIVAL_GATE'},
 'cutout_object_isolation':{'physical_units':len(units),'alpha_backed_units':alpha,'alpha_backed_ratio':round(alpha/max(1,len(units)),4),'tight_bbox_units':tight,'tight_bbox_ratio':round(tight/max(1,len(units)),4),'full_scene_extent_units':full,'full_scene_extent_ratio':round(full/max(1,len(units)),4),'hinted_objects':len(hints),'movable_hint_fallbacks':sum(1 for h in hints if h.get('policy')=='MOVABLE' and str(h.get('validation_result','')).startswith('FALLBACK'))},
 'sync':{'planned_event_count':len(events),'physical_acting_planned_actions':acting.get('planned_physical_actions'),'physical_acting_verified_actions':acting.get('verified_physical_actions'),'physical_acting_pass':acting.get('pass'),'vacuous_pass':bool(acting.get('pass') and not acting.get('planned_physical_actions')),'pixel_meaningful_change_gap_p90_seconds':cur['meaningful_change_gap_p90_seconds'],'perceptual_pass':perceptual.get('pass')},
 'composition':{'median_occupancy_percent':cur['median_nonwhite_occupancy_percent'],'underfilled_percent':cur['underfilled_frame_percent_lt15pct'],'card_count':len(cards),'composition_archetype_diversity':ch.get('composition_archetype_diversity'),'three_card_archetype_repeat_count':ch.get('three_card_archetype_repeat_count'),'within_frame_recomposition_count':ch.get('within_frame_recomposition_count')},
 'v1_1_utilization':{'source_scenes':len(motion.get('scenes') or []),'interval_child_cards':len(cards),'cards_with_independent_beats':sum(1 for x in ch.get('cards',[]) if x.get('independent_perceptual_beats',0)>1),'cards_preserving_static_full_composition':sum(1 for x in ch.get('cards',[]) if x.get('motion_unit_count',0)<=1 or x.get('low_optical_impact')),'meaningful_change_gap_max_seconds':cur['meaningful_change_gap_max_seconds']},
 'dominant_root_causes':[
  'COMMITTED_PLAN_ACTIONS_DO_NOT_SURVIVE_TO_PIXELS: 30 claimed progressive reveals coexist with zero within-frame recompositions, zero effect-family diversity, and only 16.64 percent active frames.',
  'FULL_COMPOSITION_FALLBACK_DOMINATES: hint-guided MOVABLE extraction frequently falls back, leaving large full-scene alpha groups that behave as poster plates.',
  'BOUNDARY CHOREOGRAPHY IS PALE FADE/RESET-LIKE: nine detected white-wash troughs and 10.89 isolated spikes/minute replace controlled handoffs.',
  'TYPOGRAPHY IS UNDERUTILIZED AND TIMING-INCOHERENT: four planned events for 28 cards, including a title whose impact precedes its start.',
  'FALSE-GREEN QA: physical acting passes vacuously with zero planned and zero verified physical actions; plan-level static-poster count is zero despite pixel static p90 of 5.27 seconds.',
  'INTERVAL SEGMENTATION CHANGES CARD IDS MORE OFTEN THAN PIXELS: meaningful-change p90 is 3.5 seconds and max gap is 8.6 seconds.'
 ],
 'creative_acceptance':'FAIL'
}
(ROOT/'HEXA_V31_CREATIVE_DIFFERENTIAL_REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'report':str(ROOT/'HEXA_V31_CREATIVE_DIFFERENTIAL_REPORT.json'),'dominant_root_causes':report['dominant_root_causes']},indent=2))
