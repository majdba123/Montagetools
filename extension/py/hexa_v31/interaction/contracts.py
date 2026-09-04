from __future__ import annotations
from dataclasses import dataclass, asdict

INTERACTION_ENGINE_VERSION='HEXA_INTERACTION_ENGINE_V3_3_CAUSAL_PREROLL_ATOMIC_ADOPTION'
PHYSICAL_CAUSAL_ACTIONS=frozenset({'TRANSFER','CONNECT','BLOCK','REJECT','ACCEPT','REACT','COMPARE'})
FOCUS_ACTIONS=frozenset({'READ','REVEAL','INCREASE','DECREASE','RESOLVE'})
RELATIONSHIP_VISUAL_TYPES=frozenset({'ARROW','CONNECTOR','RELATIONSHIP','FLOW_ARROW'})
MIN_SEMANTIC_CONFIDENCE=.72
MIN_MAPPING_CONFIDENCE=.85
MIN_PAIR_CONFIDENCE=.80
MIN_ACTIONABLE_EMBODIMENT_RATIO=.30

@dataclass(frozen=True)
class InteractionIntent:
    interaction_id:str
    sentence_id:str
    scene_id:str
    visual_card_id:str
    semantic_action:str
    subject_event_id:str
    object_event_id:str|None
    result_event_id:str|None
    semantic_hit_seconds:float
    confidence:float
    evidence:str
    pair_authority:str
    pair_confidence:float
    physical_pair_allowed:bool
    actionable:bool
    non_actionable_reason:str|None
    requires_reaction:bool

    def to_dict(self)->dict:
        return asdict(self)

def canonical_action(value:str|None)->str:
    action=str(value or 'PRESENT').strip().upper()
    aliases={'REACTION':'REACT','HANDOFF':'TRANSFER','SEND':'TRANSFER','LINK':'CONNECT',
             'FAIL':'REJECT','SUCCESS':'ACCEPT','SHOW':'REVEAL','COMPARISON':'COMPARE'}
    return aliases.get(action,action)
