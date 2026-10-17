"""Typed blackboard messages shared by trusted orchestration and persistence."""
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,model_validator
from contracts import Claim,FinalAnswer


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)


class Part(Strict):
    id:str=Field(pattern=r'^[a-z][a-z0-9_]{0,63}$')
    question:str=Field(min_length=1,max_length=5000)
    depends_on:list[str]=Field(default_factory=list,max_length=4)


class Plan(Strict):
    subtasks:list[Part]=Field(min_length=1,max_length=5)

    @model_validator(mode='after')
    def dag(self):
        ids=[p.id for p in self.subtasks]
        if len(set(ids))!=len(ids):raise ValueError('Duplicate subtask ID')
        done=set()
        for p in self.subtasks:
            if len(set(p.depends_on))!=len(p.depends_on) or not set(p.depends_on)<=set(ids) or p.id in p.depends_on:
                raise ValueError('Invalid dependency')
        while len(done)<len(ids):
            ready={p.id for p in self.subtasks if p.id not in done and set(p.depends_on)<=done}
            if not ready:raise ValueError('Dependency cycle')
            done|=ready
        return self


class Decision(Strict):
    claim_index:int=Field(ge=0)
    approved:bool
    reason:str=Field(min_length=1,max_length=3000)


class Review(Strict):
    decisions:list[Decision]=Field(max_length=50)


class Subtask(Strict):
    question:str
    depends_on:list[str]
    status:Literal['pending','running','completed','failed','unverified']='pending'
    attempt:int=Field(default=0,ge=0,le=1)
    claims:list[Claim]=Field(default_factory=list,max_length=50)
    review:list[Decision]=Field(default_factory=list,max_length=50)
    error:str|None=None


class Board(Strict):
    plan:Plan
    subtasks:dict[str,Subtask]
    report:FinalAnswer|None=None
