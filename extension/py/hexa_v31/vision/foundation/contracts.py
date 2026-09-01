from __future__ import annotations
from dataclasses import dataclass,asdict,field

@dataclass(frozen=True)
class SemanticObjectCandidate:
    candidate_id:str
    semantic_label:str
    description:str
    confidence:float
    bbox:tuple[int,int,int,int]
    source:str
    semantic_role:str|None=None
    parent_id:str|None=None
    signals:tuple[str,...]=()

    def to_dict(self):return asdict(self)

@dataclass
class FoundationResult:
    status:str
    backend_used:str
    candidates:list[dict]=field(default_factory=list)
    masks:list[dict]=field(default_factory=list)
    diagnostics:dict=field(default_factory=dict)
    cache_state:dict=field(default_factory=dict)
    error:str|None=None

    def to_dict(self):return asdict(self)
