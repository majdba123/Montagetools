from __future__ import annotations

"""Post-plan continuity and character-purpose QA; never fabricates assets."""
from .visual_density import build_visual_density_report

_PURPOSES=('PRESENT','POINT','COMPARE','WARN','THINK','REACT','CONFIRM','HANDOFF','RESOLVE')

def _purpose(event):
    raw=' '.join(str(event.get(k) or '') for k in ('semantic_intent','narrative_function','relationship')).upper()
    for key,purpose in (('COMPARE','COMPARE'),('WARN','WARN'),('FAIL','WARN'),('REJECT','WARN'),('REACT','REACT'),('THINK','THINK'),('CONFIRM','CONFIRM'),('SUCCESS','CONFIRM'),('TRANSFER','HANDOFF'),('HANDOFF','HANDOFF'),('RESOLVE','RESOLVE'),('POINT','POINT')):
        if key in raw:return purpose
    return 'PRESENT'

class VisualContinuityQA:
    version='HEXA_VISUAL_CONTINUITY_QA_V1'
    def assess(self,motion_plan):
        density=build_visual_density_report(motion_plan)
        cards=density.get('cards') or []
        troughs=[r for r in cards if float(r.get('near_blank_duration_seconds') or 0)>0 and not bool(r.get('intentional_blank'))]
        return {'version':self.version,'projected_visible_ink_authority':density.get('visible_ink_authority'),'whitewash_ghost_trough_count':len(troughs),'longest_continuity_trough_seconds':round(max([float(r.get('near_blank_duration_seconds') or 0) for r in troughs] or [0.0]),4),'handoff_readability_pass':not troughs,'normal_handoff_minimum_visible_ink_enforced':True,'cards':troughs}

    def repair_once(self,events,cards):
        """One deterministic source-lifetime repair before final certification."""
        repaired=[]
        for card in cards.get('cards') or []:
            cid=str(card.get('card_id'));members=sorted([e for e in events if str(e.get('visual_card_id'))==cid and not e.get('suppressed_by_card_density')],key=lambda e:(float(e.get('start_seconds',0)),str(e.get('event_id'))))
            for outgoing,incoming in zip(members,members[1:]):
                gap=float(incoming.get('start_seconds',0))-float(outgoing.get('end_seconds',0))
                if gap<=.01:continue
                # Extend an existing source-backed readable state only through
                # the gap. Entry anchors and preset families remain untouched.
                outgoing['end_seconds']=round(float(incoming['start_seconds']),6)
                outgoing['physical_end_seconds']=outgoing['end_seconds']
                outgoing['continuity_repair']='SOURCE_BACKED_READABLE_HANDOFF_EXTENSION'
                repaired.append(str(outgoing.get('event_id')));break
        return {'version':self.version,'repair_passes':1,'repaired_event_ids':repaired,'source_backed_only':True,'post_repair_assessment_required':True}

class SemanticCharacterDirector:
    version='HEXA_SEMANTIC_CHARACTER_DIRECTOR_V1'
    def direct(self,events):
        assigned=[];by_card={}
        for e in events:by_card.setdefault(str(e.get('visual_card_id') or ''),[]).append(e)
        for card_events in by_card.values():
            primaries=[e for e in card_events if str(e.get('attention_priority') or '').upper()=='PRIMARY' and 'CHARACTER' not in str(e.get('semantic_type') or '').upper()]
            for e in card_events:
                if 'CHARACTER' not in str(e.get('semantic_type') or '').upper():continue
                purpose=_purpose(e);e['character_editorial_purpose']=purpose;e['character_inserted_by_director']=False
                pos=(e.get('card_rest_position_norm') or [0.5,0.5])[0]
                opposite=all(abs(float((p.get('card_rest_position_norm') or [0.5,0.5])[0])-.5)<.03 or (float((p.get('card_rest_position_norm') or [0.5,0.5])[0])-.5)*(float(pos)-.5)<0 for p in primaries)
                e['character_opposite_half_composition']=opposite;e['character_identity_continuity_required']=purpose in {'PRESENT','COMPARE','HANDOFF','RESOLVE'}
                if purpose in {'POINT','COMPARE','HANDOFF'}:
                    e['character_within_frame_preference']='WITHIN_MIDDLE_TO_RIGHT' if float(pos)<.5 else 'WITHIN_MIDDLE_TO_LEFT'
                elif purpose=='REACT':
                    e['character_within_frame_preference']='WITHIN_MIDDLE_TO_UP';e['character_reaction_after_cause_required']=True
                else:e['character_within_frame_preference']=None
                e['character_choreography_authority']='EXISTING_SOURCE_BACKED_ASSET__CERTIFIED_PRESETS_ONLY'
                assigned.append(e)
        return {'version':self.version,'character_event_count':len(assigned),'purpose_counts':{p:sum(1 for e in assigned if e.get('character_editorial_purpose')==p) for p in _PURPOSES},'synthetic_character_insertions':0,'identity_continuity_required_count':sum(1 for e in assigned if e.get('character_identity_continuity_required'))}
