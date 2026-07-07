"""
Pydantic validation layer for permit extraction output.

Why this exists: local vision models (Moondream, small quantized models)
occasionally return malformed JSON, wrong types, out-of-range confidence
scores, or invented enum values. Without validation, bad data flows
straight into Postgres and then into the chatbot's context, compounding
the hallucination risk. This module enforces a strict schema, coerces
recoverable issues, and DROPS (rather than crashes on, or blindly accepts)
entries that fail validation -- so a bad model response degrades
gracefully to "field not extracted" instead of corrupting the database
or being silently trusted downstream.

Works for ANY permit -- nothing here is specific to a single test document.
"""
import logging
from datetime import date
from typing import List, Optional, Literal

from pydantic import BaseModel, Field, field_validator, ValidationError

logger = logging.getLogger("extraction_schema")

EscortType = Literal["BF3", "BF4", "police", "none"]
ConditionCategory = Literal["time_window", "escort", "load", "weather", "other"]


class EscortExtraction(BaseModel):
    escort_type: EscortType = "none"
    mandatory: bool = False


class SegmentExtraction(BaseModel):
    route_order: int = Field(ge=1, default=1)
    from_location: Optional[str] = None
    to_location: Optional[str] = None
    road_type: Optional[str] = None
    bundesland: Optional[str] = None
    escorts: List[EscortExtraction] = Field(default_factory=list)


class ConditionExtraction(BaseModel):
    category: ConditionCategory = "other"
    raw_text: str
    structured_value: Optional[dict] = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    needs_review: bool = False

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))

    @field_validator("needs_review")
    @classmethod
    def enforce_review_flag(cls, v: bool, info) -> bool:
        confidence = info.data.get("confidence", 0.5)
        if confidence < 0.75:
            return True
        return v

    @field_validator("raw_text")
    @classmethod
    def raw_text_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("raw_text must not be empty")
        return v.strip()


class PermitExtraction(BaseModel):
    permit_number: Optional[str] = None
    authority: Optional[str] = None
    legal_basis: List[str] = Field(default_factory=list)
    issue_date: Optional[str] = None
    valid_until: Optional[str] = None
    segments: List[SegmentExtraction] = Field(default_factory=list)
    conditions: List[ConditionExtraction] = Field(default_factory=list)

    @field_validator("issue_date", "valid_until")
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        try:
            date.fromisoformat(v)
            return v
        except ValueError:
            logger.warning(f"Dropping malformed date value: {v!r}")
            return None

    @field_validator("legal_basis")
    @classmethod
    def dedupe_legal_basis(cls, v: List[str]) -> List[str]:
        seen = []
        for item in v:
            cleaned = item.strip()
            if cleaned and cleaned not in seen:
                seen.append(cleaned)
        return seen


def validate_extraction(raw: dict) -> dict:
    """
    Validate raw extraction JSON from the vision model. Returns a clean,
    schema-conformant dict. If the WHOLE payload fails validation, attempts
    a best-effort per-item salvage so one bad condition/segment doesn't
    discard an otherwise-good extraction. Never raises -- always returns
    something safe to persist, with issues logged for visibility.
    """
    try:
        validated = PermitExtraction(**raw)
        return validated.model_dump()
    except ValidationError as exc:
        logger.warning(f"Full extraction validation failed, attempting salvage: {exc}")
        return _salvage_extraction(raw)


def _salvage_extraction(raw: dict) -> dict:
    """
    Per-item best-effort validation. Drops individual malformed segments/
    conditions instead of discarding the entire extraction, so partial
    document quality doesn't zero out an otherwise usable result.
    """
    salvaged = {
        "permit_number": raw.get("permit_number") if isinstance(raw.get("permit_number"), str) else None,
        "authority": raw.get("authority") if isinstance(raw.get("authority"), str) else None,
        "legal_basis": [s for s in raw.get("legal_basis", []) if isinstance(s, str)],
        "issue_date": None,
        "valid_until": None,
        "segments": [],
        "conditions": [],
    }

    for date_field in ("issue_date", "valid_until"):
        val = raw.get(date_field)
        if isinstance(val, str):
            try:
                date.fromisoformat(val)
                salvaged[date_field] = val
            except ValueError:
                logger.warning(f"Salvage: dropping malformed {date_field}={val!r}")

    for seg in raw.get("segments", []):
        try:
            salvaged["segments"].append(SegmentExtraction(**seg).model_dump())
        except ValidationError as exc:
            logger.warning(f"Salvage: dropping malformed segment {seg!r}: {exc}")

    for cond in raw.get("conditions", []):
        try:
            salvaged["conditions"].append(ConditionExtraction(**cond).model_dump())
        except ValidationError as exc:
            logger.warning(f"Salvage: dropping malformed condition {cond!r}: {exc}")

    return salvaged