import uuid
import enum
from datetime import datetime

from sqlalchemy import (
    Column, String, DateTime, ForeignKey, Text, Float, Boolean, Enum, Integer
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class DocumentStatus(str, enum.Enum):
    uploaded = "uploaded"
    processing = "processing"
    extracted = "extracted"
    needs_review = "needs_review"
    failed = "failed"


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    tenant_id = Column(String, nullable=False, default="demo-tenant")
    filename = Column(String, nullable=False)
    checksum = Column(String, nullable=False, index=True)
    file_url = Column(String, nullable=False)
    status = Column(Enum(DocumentStatus), default=DocumentStatus.uploaded)
    raw_text = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    permit = relationship("Permit", back_populates="document", uselist=False)


class Permit(Base):
    __tablename__ = "permits"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    document_id = Column(UUID(as_uuid=False), ForeignKey("documents.id"), nullable=False)
    permit_number = Column(String, nullable=True)
    authority = Column(String, nullable=True)
    legal_basis = Column(JSONB, nullable=True)
    issue_date = Column(String, nullable=True)
    valid_until = Column(String, nullable=True)
    status = Column(String, default="pending_review")
    confidence = Column(Float, default=0.0)
    supersedes_permit_id = Column(UUID(as_uuid=False), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    document = relationship("Document", back_populates="permit")
    segments = relationship("PermitSegment", back_populates="permit", cascade="all, delete-orphan")
    conditions = relationship("PermitCondition", back_populates="permit", cascade="all, delete-orphan")


class PermitSegment(Base):
    __tablename__ = "permit_segments"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    permit_id = Column(UUID(as_uuid=False), ForeignKey("permits.id"), nullable=False)
    route_order = Column(Integer, default=0)
    from_location = Column(String, nullable=True)
    to_location = Column(String, nullable=True)
    road_type = Column(String, nullable=True)
    bundesland = Column(String, nullable=True)

    permit = relationship("Permit", back_populates="segments")
    escorts = relationship("EscortRequirement", back_populates="segment", cascade="all, delete-orphan")


class PermitCondition(Base):
    __tablename__ = "permit_conditions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    permit_id = Column(UUID(as_uuid=False), ForeignKey("permits.id"), nullable=False)
    category = Column(String, nullable=False)
    raw_text = Column(Text, nullable=False)
    structured_value = Column(JSONB, nullable=True)
    confidence = Column(Float, default=0.0)
    needs_review = Column(Boolean, default=False)

    permit = relationship("Permit", back_populates="conditions")


class EscortRequirement(Base):
    __tablename__ = "escort_requirements"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    segment_id = Column(UUID(as_uuid=False), ForeignKey("permit_segments.id"), nullable=False)
    escort_type = Column(String, nullable=False)
    mandatory = Column(Boolean, default=True)

    segment = relationship("PermitSegment", back_populates="escorts")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    permit_id = Column(UUID(as_uuid=False), ForeignKey("permits.id"), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    citations = Column(JSONB, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReviewEvent(Base):
    __tablename__ = "review_events"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    permit_id = Column(UUID(as_uuid=False), ForeignKey("permits.id"), nullable=False)
    field = Column(String, nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    reviewer = Column(String, default="demo-user")
    created_at = Column(DateTime, default=datetime.utcnow)
