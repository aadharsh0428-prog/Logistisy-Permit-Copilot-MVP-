from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import (
    Document, DocumentStatus, Permit, PermitSegment, PermitCondition,
    EscortRequirement, ChatMessage
)
from app.schemas import DocumentOut
from app.services.ocr_service import OCRService
from app.services.extraction_service import ExtractionService


router = APIRouter(prefix="/documents", tags=["documents"])


ocr_service = OCRService()
extraction_service = ExtractionService()


def _wipe_previous_extraction(document: Document, db: Session) -> None:
    """
    Dev-mode helper (FORCE_REPROCESS=true): deletes any prior Permit and its
    child rows (segments, escorts, conditions, chat_messages) tied to this
    document, so the same test file can be re-uploaded repeatedly during
    debugging without manual SQL cleanup. Deletion order respects FK
    constraints: chat_messages -> escorts -> segments -> conditions -> permit.
    """
    old_permit = db.query(Permit).filter(Permit.document_id == document.id).first()
    if not old_permit:
        return

    db.query(ChatMessage).filter(
        ChatMessage.permit_id == old_permit.id
    ).delete(synchronize_session=False)

    segment_ids = [s.id for s in old_permit.segments]
    if segment_ids:
        db.query(EscortRequirement).filter(
            EscortRequirement.segment_id.in_(segment_ids)
        ).delete(synchronize_session=False)

    db.query(PermitSegment).filter(
        PermitSegment.permit_id == old_permit.id
    ).delete(synchronize_session=False)

    db.query(PermitCondition).filter(
        PermitCondition.permit_id == old_permit.id
    ).delete(synchronize_session=False)

    db.delete(old_permit)
    db.commit()


@router.post("", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not ocr_service.is_supported_type(file.filename):
        raise HTTPException(400, "Unsupported file type. Upload a PDF or image.")

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(400, "Empty file uploaded.")

    checksum = ocr_service.checksum(file_bytes)

    existing = db.query(Document).filter(Document.checksum == checksum).first()

    if existing and not settings.force_reprocess:
        return existing

    if existing and settings.force_reprocess:
        _wipe_previous_extraction(existing, db)
        document = existing
        document.status = DocumentStatus.uploaded
        document.error_message = None
        db.commit()
        db.refresh(document)
    else:
        document = Document(
            filename=file.filename,
            checksum=checksum,
            file_url=f"local://{file.filename}",
            status=DocumentStatus.uploaded,
        )
        db.add(document)
        db.commit()
        db.refresh(document)

    try:
        # Llama 3.2 Vision (via Ollama) reads the image and extracts
        # structured data in a single call — no separate OCR pass needed.
        await extraction_service.process_document(document, file_bytes, db)
    except Exception as exc:
        document.status = DocumentStatus.failed
        document.error_message = str(exc)
        db.commit()

    db.refresh(document)
    return document


@router.get("/{document_id}/status", response_model=DocumentOut)
def get_status(document_id: str, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(404, "Document not found.")
    return document