"""Bible verse set helpers shared by routes, PPT generation, and the feed."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from models import BibleEntryModel, BibleSetModel
from services.bible_service import DEFAULT_TRANSLATION_ID

DEFAULT_SET_NAME = "Bible Verses"


def touch_set(db: Session, set_id: int):
    """Mark a set as recently used (drives card ordering on the Bible page).

    Does not commit; callers commit as part of their own transaction.
    """
    db.query(BibleSetModel).filter(BibleSetModel.id == set_id).update(
        {BibleSetModel.last_used: datetime.now(timezone.utc)}
    )


def get_active_set(db: Session) -> BibleSetModel:
    """Return the active verse set, self-healing if none exists or is active."""
    active = (
        db.query(BibleSetModel).filter(BibleSetModel.is_active == True).first()
    )
    if active:
        return active
    first = db.query(BibleSetModel).order_by(BibleSetModel.id).first()
    if first:
        first.is_active = True
        db.commit()
        return first
    created = BibleSetModel(
        name=DEFAULT_SET_NAME,
        translation=DEFAULT_TRANSLATION_ID,
        is_active=True,
    )
    db.add(created)
    db.commit()
    db.refresh(created)
    return created


def get_set_or_active(db: Session, set_id: Optional[int]) -> BibleSetModel:
    """Return the requested set, falling back to the active one."""
    if set_id is not None:
        found = (
            db.query(BibleSetModel).filter(BibleSetModel.id == set_id).first()
        )
        if found:
            return found
    return get_active_set(db)


def set_entries_query(db: Session, set_id: int):
    """Entries of one set, in sequence order."""
    return (
        db.query(BibleEntryModel)
        .filter(BibleEntryModel.set_id == set_id)
        .order_by(BibleEntryModel.sequence)
    )
