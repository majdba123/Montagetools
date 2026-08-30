from __future__ import annotations

"""Compile source semantics into generic visual sentences before motion choice."""

_ACTIONS=('PRESENT','ENTER','TRANSFER','CONNECT','READ','COMPARE','INCREASE','DECREASE','BLOCK','REJECT','ACCEPT','REVEAL','REACT','RESOLVE')
_ALIASES=(
    (('COMPARE','VERSUS','CONTRAST'),'COMPARE'),(('INCREASE','GROW','RISE','ADD'),'INCREASE'),
    (('DECREASE','REDUCE','DROP','REMOVE'),'DECREASE'),(('BLOCK','PREVENT','STOP','DENY'),'BLOCK'),
    (('REJECT','FAIL','ERROR','INVALID'),'REJECT'),(('ACCEPT','SUCCESS','CONFIRM','VALID'),'ACCEPT'),
    (('TRANSFER','HANDOFF','MOVE','SEND'),'TRANSFER'),(('CONNECT','LINK','RELATE'),'CONNECT'),
    (('READ','MEASURE','CHECK','INSPECT'),'READ'),(('ENTER','ARRIVE','REACH','INTRODUCE'),'ENTER'),
    (('REVEAL','SHOW','DISCOVER'),'REVEAL'),(('REACT','REACTION','RESPOND'),'REACT'),
    (('RESOLVE','RESULT','CONCLUDE','COMPLETE'),'RESOLVE'),
)

def _action(event):
    raw=' '.join(str(event.get(k) or '') for k in ('semantic_intent','narrative_function','relationship')).upper()
    for keys,action in _ALIASES:
        if any(key in raw for key in keys):return action
    return 'PRESENT'

class SemanticVisualSentenceCompiler:
    version='HEXA_SEMANTIC_VISUAL_SENTENCE_COMPILER_V1'
    def compile(self,events):
        groups={}
        for event in events:
            groups.setdefault((str(event.get('visual_card_id') or ''),str(event.get('scene_id') or '')),[]).append(event)
        sentences=[]
        for (card_id,scene_id),members in sorted(groups.items()):
            ordered=sorted(members,key=lambda e:(0 if str(e.get('attention_priority')).upper()=='PRIMARY' else 1,float(e.get('perceptual_hit_seconds',0)),str(e.get('event_id'))))
            subject=ordered[0] if ordered else None
            obj=next((e for e in ordered[1:] if str(e.get('semantic_scope_id') or '')!=str((subject or {}).get('semantic_scope_id') or '')),None)
            result=next((e for e in ordered if any(x in str(e.get('semantic_role') or '').upper() for x in ('RESULT','TARGET','OUTCOME'))),None)
            action=_action(subject or {})
            sentence={'sentence_id':f'SENTENCE_{scene_id or card_id}','scene_id':scene_id,'visual_card_id':card_id,
                      'subject_event_id':(subject or {}).get('event_id'),'action':action,'object_event_id':(obj or {}).get('event_id'),
                      'relation':(subject or {}).get('relationship'),'result_event_id':(result or {}).get('event_id'),
                      'physical_support':bool(subject),'source_authority':'FINAL_PACKAGE_SEMANTICS_PLUS_PHYSICAL_EVENTS'}
            sentences.append(sentence)
            for event in members:
                event['semantic_visual_sentence_id']=sentence['sentence_id'];event['semantic_sentence_action']=action
                event['semantic_sentence_subject_event_id']=sentence['subject_event_id'];event['semantic_sentence_object_event_id']=sentence['object_event_id']
                event['semantic_sentence_result_event_id']=sentence['result_event_id'];event['semantic_sentence_physical_support']=sentence['physical_support']
        return {'version':self.version,'sentence_count':len(sentences),'supported_action_count':sum(1 for s in sentences if s['physical_support']),
                'action_counts':{a:sum(1 for s in sentences if s['action']==a) for a in _ACTIONS},'sentences':sentences,'unsupported_motion_invention_count':0}
