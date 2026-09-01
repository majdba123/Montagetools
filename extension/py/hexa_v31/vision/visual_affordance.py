from __future__ import annotations
"""Physical affordances constrain motion; they never manufacture subobjects."""
def classify(unit):
    mode=str(unit.get('render_mode') or 'ROOT_ATOMIC');translation=bool(unit.get('translation_safe_after_occlusion',unit.get('animation_safe',False)));reveal=bool(unit.get('reveal_safe',False));children=int(unit.get('hierarchy_level') or 0)>0
    if mode=='CHILD_PARTITION' and translation:return 'DETACHED_TRANSLATABLE'
    if children and reveal:return 'ARTICULATED_SUBOBJECT'
    if translation:return 'DETACHED_TRANSLATABLE'
    if reveal:return 'CONNECTED_REVEAL_ONLY'
    if mode in {'GROUPED_DETAIL','CONTEXT_RESIDUAL'}:return 'CONTEXT_RESIDUAL'
    return 'ROOT_ATOMIC'
def legal_operations(affordance):
    return {'ROOT_ATOMIC':('STATIC','SCALE'),'DETACHED_TRANSLATABLE':('STATIC','SCALE','TRANSLATE'),'CONNECTED_REVEAL_ONLY':('STATIC','SCALE','REVEAL'),'CONNECTED_LOCAL_EMPHASIS':('STATIC','SCALE','LOCAL_EMPHASIS'),'ARTICULATED_SUBOBJECT':('STATIC','SCALE','REVEAL','LOCAL_EMPHASIS'),'CONTEXT_RESIDUAL':('STATIC',)}.get(affordance,('STATIC',))
