from typing import Optional, List, Any
from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: str
    filename: str
    status: str

    class Config:
        from_attributes = True


class EscortOut(BaseModel):
    escort_type: str
    mandatory: bool

    class Config:
        from_attributes = True


class SegmentOut(BaseModel):
    route_order: int
    from_location: Optional[str]
    to_location: Optional[str]
    road_type: Optional[str]
    bundesland: Optional[str]
    escorts: List[EscortOut] = []

    class Config:
        from_attributes = True


class ConditionOut(BaseModel):
    category: str
    raw_text: str
    structured_value: Optional[Any]
    confidence: float
    needs_review: bool

    class Config:
        from_attributes = True


class PermitOut(BaseModel):
    id: str
    permit_number: Optional[str]
    authority: Optional[str]
    legal_basis: Optional[Any]
    issue_date: Optional[str]
    valid_until: Optional[str]
    status: str
    confidence: float
    segments: List[SegmentOut] = []
    conditions: List[ConditionOut] = []

    class Config:
        from_attributes = True


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    answer: str
    citations: List[str] = []
