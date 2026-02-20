"""JSON API endpoints for vMix and external consumers."""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import (
    HymnModel, ServicePlanHymnModel, ServiceProgramModel, VmixRow,
)
from services.program_service import serialize_program_items
from utils import get_slides_by_type

router = APIRouter()


@router.get("/api/vmix", response_model=List[VmixRow])
def get_vmix_feed(db: Session = Depends(get_db)):
    """Flatten scheduled hymns into the row format vMix expects."""
    service_items = (
        db.query(ServicePlanHymnModel)
        .order_by(ServicePlanHymnModel.sequence)
        .all()
    )

    vmix_output = []
    for item in service_items:
        hymn = item.hymn
        if not hymn:
            continue

        sorted_slides = get_slides_by_type(hymn, preferred_type="VMIX")
        for slide in sorted_slides:
            vmix_output.append(
                VmixRow(
                    HymnNumber=hymn.number,
                    Title=hymn.title,
                    Label=slide.label,
                    SlideText=slide.content,
                )
            )

        # Spacer after each hymn
        vmix_output.append(
            VmixRow(HymnNumber="", Title="", Label="", SlideText="")
        )

    return vmix_output


@router.get("/api/program/{id}/json")
def get_program_json(id: int, db: Session = Depends(get_db)):
    """Return JSON for a specific program."""
    prog = (
        db.query(ServiceProgramModel)
        .filter(ServiceProgramModel.id == id)
        .first()
    )
    return serialize_program_items(prog)


@router.get("/api/program/current")
def get_current_program_json(db: Session = Depends(get_db)):
    """Return JSON for the currently active program."""
    prog = (
        db.query(ServiceProgramModel)
        .filter(ServiceProgramModel.is_active == True)
        .first()
    )
    if not prog:
        return [{"title": "No Active Program", "subtitle": "Select one in Dashboard"}]
    return serialize_program_items(prog)
