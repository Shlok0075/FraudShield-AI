from pydantic import BaseModel, Field
class CaseCreate(BaseModel):
    alert_id:int=Field(gt=0)
    assigned_to:int|None=None
    priority:str=Field(default='medium',pattern='^(low|medium|high|critical)$')
    summary:str|None=None
class CaseUpdate(BaseModel):
    assigned_to:int|None=None
    status:str|None=Field(default=None,pattern='^(open|investigating|pending|closed)$')
    priority:str|None=Field(default=None,pattern='^(low|medium|high|critical)$')
    decision:str|None=Field(default=None,pattern='^(confirmed_fraud|false_positive|unresolved)$')
    summary:str|None=None
class NoteCreate(BaseModel):
    note:str=Field(min_length=1,max_length=5000)
