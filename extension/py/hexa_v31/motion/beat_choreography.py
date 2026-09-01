from __future__ import annotations
"""Bounded coordinated beat order; selection remains subject to physical QA."""
_BEATS={'READ':('ESTABLISH','FOCUS','OBJECT_EMPHASIS','RESULT_LOCK'),'BLOCK':('APPROACH','BARRIER','STOP_REJECT','RESOLVE'),'COMPARE':('A_ESTABLISH','B_ESTABLISH','BASELINE','DIFFERENCE_EMPHASIS'),'TRANSFER':('SOURCE','CONNECTION','DESTINATION','RESULT')}
class BeatChoreographyCompiler:
    version='HEXA_BEAT_CHOREOGRAPHY_COMPILER_V1'
    def compile(self,events,sentences):
        by={s['sentence_id']:s for s in sentences};out=[]
        for sid,sentence in sorted(by.items()):
            action=sentence['action'];sequence=_BEATS.get(action,('ESTABLISH',action,'READABLE_STATIC_STATE'));members=sorted((e for e in events if e.get('semantic_visual_sentence_id')==sid),key=lambda e:(float(e.get('perceptual_hit_seconds',0)),str(e.get('event_id'))));supported=[e for e in members if 'STATIC' in (e.get('visual_affordance_operations') or [])]
            fallback=not supported or action=='PRESENT';row={'sentence_id':sid,'action':action,'beat_sequence':list(sequence if not fallback else ('ESTABLISH','READABLE_STATIC_STATE')),'event_ids':[e.get('event_id') for e in supported],'fallback_static':fallback,'authority':'CERTIFIED_PHYSICAL_AFFORDANCES_ONLY'};out.append(row)
            for e in members:e['beat_choreography_id']=sid;e['beat_choreography_sequence']=row['beat_sequence'];e['beat_choreography_fallback_static']=fallback
        return {'version':self.version,'beat_count':len(out),'beats':out,'consumed_by_planner':True}
