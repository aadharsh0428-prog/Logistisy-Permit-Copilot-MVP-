from sqlalchemy.orm import Session

from app.models import (
    Document, Permit, PermitSegment, PermitCondition, EscortRequirement, DocumentStatus
)
from app.services.llm_client import LLMClient

llm_client = LLMClient()


class ExtractionService:
    async def process_document(self, document: Document, file_bytes: bytes, db: Session) -> Permit:
        document.status = DocumentStatus.processing
        db.commit()

        # Llama 3.2 Vision reads the image directly and returns structured JSON
        # in a single call — no separate OCR pass required.
        extracted = await llm_client.extract_from_image(file_bytes)

        permit = Permit(
            document_id=document.id,
            permit_number=extracted.get("permit_number"),
            authority=extracted.get("authority"),
            legal_basis=extracted.get("legal_basis"),
            issue_date=extracted.get("issue_date"),
            valid_until=extracted.get("valid_until"),
            status="pending_review",
            confidence=0.85,
        )
        db.add(permit)
        db.flush()

        for seg in extracted.get("segments", []):
            segment = PermitSegment(
                permit_id=permit.id,
                route_order=seg.get("route_order", 0),
                from_location=seg.get("from_location"),
                to_location=seg.get("to_location"),
                road_type=seg.get("road_type"),
                bundesland=seg.get("bundesland"),
            )
            db.add(segment)
            db.flush()

            for escort in seg.get("escorts", []):
                db.add(EscortRequirement(
                    segment_id=segment.id,
                    escort_type=escort.get("escort_type"),
                    mandatory=escort.get("mandatory", True),
                ))

        any_needs_review = False
        for cond in extracted.get("conditions", []):
            needs_review = cond.get("needs_review", False)
            any_needs_review = any_needs_review or needs_review
            db.add(PermitCondition(
                permit_id=permit.id,
                category=cond.get("category"),
                raw_text=cond.get("raw_text"),
                structured_value=cond.get("structured_value"),
                confidence=cond.get("confidence", 0.0),
                needs_review=needs_review,
            ))

        document.status = (
            DocumentStatus.needs_review if any_needs_review else DocumentStatus.extracted
        )
        db.commit()
        db.refresh(permit)
        return permit
