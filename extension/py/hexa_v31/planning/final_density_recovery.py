from __future__ import annotations

from hexa_v31.visual_density import build_visual_density_report


def recover_final_density(plan: dict, fps: float = 30.0) -> dict:
    """Repair only final measured readability troughs using existing source actors."""
    events=[e for e in plan.get('events') or [] if not e.get('suppressed_by_card_density')]
    cards=(plan.get('visual_cards') or {}).get('cards') or []
    before=build_visual_density_report(plan);rows={str(r.get('card_id')):r for r in before.get('cards') or []}
    repaired=[]
    for card in cards:
        cid=str(card.get('card_id'));metric=rows.get(cid) or {}
        local=sorted([e for e in events if str(e.get('visual_card_id'))==cid],key=lambda e:(float(e.get('start_seconds',0)),str(e.get('event_id'))))
        if not local:continue
        if float(metric.get('near_blank_duration_seconds') or 0)>.35:
            card_start=float(card.get('start_seconds',0));first_start=min(float(e.get('physical_start_seconds',e.get('start_seconds',0))) for e in local)
            cohort=[e for e in local if float(e.get('physical_start_seconds',e.get('start_seconds',0)))<=first_start+1e-5]
            candidate=next((e for e in cohort if e.get('preset_entry')),cohort[0])
            entry=candidate.get('preset_entry')
            if entry and float(entry.get('start_seconds',card_start))>card_start+1e-5:
                duration=float(entry.get('duration_seconds') or .8);entry['start_seconds']=round(card_start,6);entry['authority']='FINAL_DENSITY_CARD_LEADING_SOURCE_REVEAL';candidate['start_seconds']=round(card_start,6);candidate['settle_seconds']=round(card_start+duration,6)
            else:
                predecessors=[e for e in events if str(e.get('visual_card_id'))!=cid and float(e.get('physical_end_seconds',e.get('end_seconds',0)))<=card_start+.11]
                if predecessors:
                    outgoing=max(predecessors,key=lambda e:float(e.get('physical_end_seconds',e.get('end_seconds',0))))
                    target=min(float(card.get('end_seconds',candidate.get('settle_seconds',card_start))),float(candidate.get('settle_seconds',card_start)))
                    outgoing['end_seconds']=round(target,6);outgoing['physical_end_seconds']=round(target,6);outgoing['visibility_interval_seconds']=[float(outgoing.get('physical_start_seconds',outgoing.get('start_seconds',0))),round(target,6)]
                    exit_row=outgoing.get('preset_exit')
                    if exit_row:
                        dd=float(exit_row.get('duration_seconds') or .6);exit_row['start_seconds']=round(max(float(outgoing.get('start_seconds',0)),target-dd*.6),6);exit_row['authority']='FINAL_DENSITY_CARD_LEADING_SOURCE_HOLD'
                    outgoing['final_density_recovery']='CARD_LEADING_READABLE_SOURCE_HOLD';repaired.append(str(outgoing.get('event_id')))
                    continue
            repaired.append(str(candidate.get('event_id')))
        if metric.get('hard_under_density'):
            for outgoing,incoming in zip(local,local[1:]):
                if str(outgoing.get('scene_id'))==str(incoming.get('scene_id')):continue
                entry=incoming.get('preset_entry');exit_row=outgoing.get('preset_exit')
                if not entry or not exit_row:continue
                duration=float(entry.get('duration_seconds') or .8)
                target=max(float(incoming.get('physical_start_seconds',incoming.get('start_seconds',0))),float(exit_row.get('start_seconds',0))-.25)
                if target>=float(entry.get('start_seconds',target))-1e-5:continue
                entry['start_seconds']=round(target,6);entry['authority']='FINAL_DENSITY_READABLE_SOURCE_OVERLAP';incoming['start_seconds']=round(min(float(incoming.get('start_seconds',target)),target),6);incoming['settle_seconds']=round(target+duration,6);incoming['final_density_recovery']='BOUNDED_SOURCE_OVERLAP'
                incoming['final_density_overlap_required']=True
                repaired.append(str(incoming.get('event_id')));break
    return {'authority':'FINAL_MEASURED_SOURCE_DENSITY_RECOVERY','repaired_event_ids':sorted(set(repaired)),'before_hard_under_density_cards':before.get('hard_under_density_cards') or [],'before_near_blank_duration_seconds':before.get('near_blank_duration_seconds')}
