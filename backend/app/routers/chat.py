from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Permit, PermitCondition, PermitSegment, ChatMessage
from app.schemas import ChatRequest, ChatResponse
from app.services.llm_client import LLMClient

router = APIRouter(prefix="/permits", tags=["chat"])
llm_client = LLMClient()


def build_context_spans(permit: Permit, conditions, segments) -> list[str]:
    """
    Assemble ALL groundable facts about a permit into labeled spans.
    Labeling each span with its category (not just raw text) helps a small
    local model tell condition text apart from metadata like legal basis,
    which is what caused the earlier "legal paragraphs" mislabeling bug.
    """
    spans = []

    if permit.permit_number:
        spans.append(f"[Permit number] {permit.permit_number}")
    if permit.authority:
        spans.append(f"[Issuing authority] {permit.authority}")
    if permit.legal_basis:
        spans.append(f"[Legal basis / legal paragraphs] {', '.join(permit.legal_basis)}")
    if permit.issue_date:
        spans.append(f"[Issue date] {permit.issue_date}")
    if permit.valid_until:
        spans.append(f"[Valid until / expiry date] {permit.valid_until}")

    for seg in segments:
        route = f"{seg.from_location or '?'} -> {seg.to_location or '?'}"
        spans.append(
            f"[Route segment {seg.route_order}] {route} "
            f"({seg.road_type or 'unknown road type'}, {seg.bundesland or 'unknown state'})"
        )
        for escort in getattr(seg, "escorts", []) or []:
            spans.append(
                f"[Escort requirement, segment {seg.route_order}] "
                f"{escort.escort_type} mandatory={escort.mandatory}"
            )

    for c in conditions:
        spans.append(f"[Condition: {c.category}] {c.raw_text}")

    return spans


@router.post("/{permit_id}/chat", response_model=ChatResponse)
async def chat_with_permit(
    permit_id: str, payload: ChatRequest, db: Session = Depends(get_db)
):
    permit = db.query(Permit).filter(Permit.id == permit_id).first()
    if not permit:
        raise HTTPException(404, "Permit not found.")

    conditions = db.query(PermitCondition).filter(PermitCondition.permit_id == permit_id).all()
    segments = db.query(PermitSegment).filter(PermitSegment.permit_id == permit_id).all()

    # Pass ALL facts directly to the LLM — a single permit has only ~10-20
    # short facts, well within any local model's context window. The prior
    # keyword-based retrieval step (select_relevant_spans) was causing real
    # failures: bracket characters in labels like "[Route segment 1]" never
    # got stripped correctly, so question words like "route" never matched
    # "[route" as a token, and German raw_text never matched English
    # questions on pure keyword overlap. Skipping retrieval entirely at
    # this scale is simpler and strictly more reliable.
    all_spans = build_context_spans(permit, conditions, segments)

    result = await llm_client.grounded_answer(payload.message, all_spans)

    db.add(ChatMessage(permit_id=permit_id, role="user", content=payload.message))
    db.add(ChatMessage(
        permit_id=permit_id, role="assistant", content=result["answer"],
        citations=result["citations"],
    ))
    db.commit()

    return ChatResponse(answer=result["answer"], citations=result["citations"])