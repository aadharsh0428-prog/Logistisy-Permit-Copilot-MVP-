from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Permit, PermitSegment
from app.schemas import PermitOut

router = APIRouter(prefix="/permits", tags=["permits"])


@router.get("", response_model=list[PermitOut])
def list_permits(db: Session = Depends(get_db)):
    permits = (
        db.query(Permit)
        .options(
            joinedload(Permit.segments).joinedload(PermitSegment.escorts),
            joinedload(Permit.conditions),
        )
        .order_by(Permit.created_at.desc())
        .all()
    )
    return permits


@router.get("/{permit_id}", response_model=PermitOut)
def get_permit(permit_id: str, db: Session = Depends(get_db)):
    permit = (
        db.query(Permit)
        .options(
            joinedload(Permit.segments).joinedload(PermitSegment.escorts),
            joinedload(Permit.conditions),
        )
        .filter(Permit.id == permit_id)
        .first()
    )
    if not permit:
        raise HTTPException(404, "Permit not found.")
    return permit