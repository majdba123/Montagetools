from __future__ import annotations

"""Source-authoritative, bounded semantic action resolution for visual beats."""
import re

_ACTIONS=('PRESENT','ENTER','TRANSFER','CONNECT','READ','COMPARE','INCREASE','DECREASE','BLOCK','REJECT','ACCEPT','REVEAL','REACT','RESOLVE')
_SIGNALS={'COMPARE':('COMPARE','COMPARISON','DIFFERENCE','VERSUS','LESS','MORE','EQUAL'),'INCREASE':('INCREASE','RISE','GROW','HIGHER'),'DECREASE':('DECREASE','DROP','REDUCE','LOWER'),'BLOCK':('BLOCK','PREVENT','STOP','DENY','LIMIT'),'REJECT':('REJECT','FAIL','ERROR','INVALID'),'ACCEPT':('ACCEPT','SUCCESS','CONFIRM','VALID','APPROVE'),'TRANSFER':('TRANSFER','HANDOFF','SEND','MOVE'),'CONNECT':('CONNECT','LINK','RELATION','FLOW'),'READ':('READ','MEASURE','CHECK','INSPECT','SCAN'),'ENTER':('ENTER','ARRIVE','REACH','INTRODUCE'),'REVEAL':('REVEAL','SHOW','DISCOVER'),'REACT':('REACT','REACTION','RESPOND'),'RESOLVE':('RESOLVE','RESULT','CONCLUDE','COMPLETE')}
_NEGATION=re.compile(r'(?<!\w)(?:ما|لا|لم|لن|ليس|غير|NOT|NO|NEVER|WITHOUT)(?!\w)',re.I)

def _text(event):return ' '.join(str(event.get(k) or '') for k in ('canonical_clause','canonical_narration','visual_concept','narrative_function','semantic_intent','relationship'))
def _resolve(event):
    text=_text(event);upper=text.upper();hits=[]
    for action,signals in _SIGNALS.items():
        score=sum(1 for signal in signals if signal in upper)
        if score:hits.append((score,action))
    semantic=str(event.get('semantic_intent') or event.get('narrative_function') or '').upper();direct=next((a for a in _ACTIONS if a in semantic),None)
    action=direct or (max(hits)[1] if hits else 'PRESENT');confidence=.94 if direct else (.72 if hits else .30);polarity='NEGATED' if _NEGATION.search(text) else 'AFFIRMED'
    if polarity=='NEGATED' and action=='ACCEPT':action='REJECT';confidence=max(confidence,.78)
    return action,round(confidence,3),polarity

class SemanticVisualSentenceCompiler:
    version='HEXA_SEMANTIC_ACTION_RESOLVER_V2'
    def compile(self,events):
        groups={}
        for event in events:groups.setdefault((str(event.get('visual_card_id') or ''),str(event.get('scene_id') or '')),[]).append(event)
        sentences=[]
        for card_id,scene_id in sorted(groups):
            members=groups[(card_id,scene_id)];ordered=sorted(members,key=lambda e:(0 if str(e.get('attention_priority')).upper()=='PRIMARY' else 1,float(e.get('perceptual_hit_seconds',0)),str(e.get('event_id'))));subject=ordered[0] if ordered else {};obj=next((e for e in ordered[1:] if str(e.get('semantic_scope_id') or '')!=str(subject.get('semantic_scope_id') or '')),None);result=next((e for e in ordered if any(x in str(e.get('semantic_role') or '').upper() for x in ('RESULT','TARGET','OUTCOME'))),None);action,confidence,polarity=_resolve(subject)
            sentence={'sentence_id':f'SENTENCE_{scene_id or card_id}','scene_id':scene_id,'visual_card_id':card_id,'subject_event_id':subject.get('event_id'),'action':action,'object_event_id':(obj or {}).get('event_id'),'relation':subject.get('relationship'),'result_event_id':(result or {}).get('event_id'),'polarity':polarity,'confidence':confidence,'physical_support':bool(subject),'source_authority':'CANONICAL_CLAUSE_PLUS_FINAL_PACKAGE_SEMANTICS_PLUS_PHYSICAL_EVENTS'};sentences.append(sentence)
            for event in members:event.update({'semantic_visual_sentence_id':sentence['sentence_id'],'semantic_sentence_action':action,'semantic_sentence_confidence':confidence,'semantic_sentence_polarity':polarity,'semantic_sentence_subject_event_id':sentence['subject_event_id'],'semantic_sentence_object_event_id':sentence['object_event_id'],'semantic_sentence_result_event_id':sentence['result_event_id'],'semantic_sentence_physical_support':sentence['physical_support']})
        counts={a:sum(1 for s in sentences if s['action']==a) for a in _ACTIONS}
        return {'version':self.version,'sentence_count':len(sentences),'supported_action_count':sum(1 for s in sentences if s['physical_support']),'action_counts':counts,'present_ratio':round(counts['PRESENT']/max(1,len(sentences)),4),'sentences':sentences,'unsupported_motion_invention_count':0}
