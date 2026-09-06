"""Hymn set helpers shared by routes, PPT generation, and the vMix feed."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from models import HymnSetModel, ServicePlanHymnModel

DEFAULT_SET_NAME = "Service Hymns"


def touch_set(db: Session, set_id: int):
    """Mark a set as recently used (drives card ordering on the Hymns page).

    Does not commit; callers commit as part of their own transaction.
    """
    db.query(HymnSetModel).filter(HymnSetModel.id == set_id).update(
        {HymnSetModel.last_used: datetime.now(timezone.utc)}
    )


def get_active_set(db: Session) -> HymnSetModel:
    """Return the active hymn set, self-healing if none exists or is active."""
    active = (
        db.query(HymnSetModel).filter(HymnSetModel.is_active == True).first()
    )
    if active:
        return active
    first = db.query(HymnSetModel).order_by(HymnSetModel.id).first()
    if first:
        first.is_active = True
        db.commit()
        return first
    created = HymnSetModel(name=DEFAULT_SET_NAME, is_active=True)
    db.add(created)
    db.commit()
    db.refresh(created)
    return created


def get_set_or_active(db: Session, set_id: Optional[int]) -> HymnSetModel:
    """Return the requested set, falling back to the active one."""
    if set_id is not None:
        found = (
            db.query(HymnSetModel).filter(HymnSetModel.id == set_id).first()
        )
        if found:
            return found
    return get_active_set(db)


def set_plan_query(db: Session, set_id: int):
    """Plan rows of one set, in sequence order."""
    return (
        db.query(ServicePlanHymnModel)
        .filter(ServicePlanHymnModel.set_id == set_id)
        .order_by(ServicePlanHymnModel.sequence)
    )
