from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey,
)
from sqlalchemy.orm import relationship

from database import Base


# ---------------------------------------------------------------------------
# SQLAlchemy ORM models
# ---------------------------------------------------------------------------

class HymnModel(Base):
    __tablename__ = "hymns"

    id = Column(Integer, primary_key=True, index=True)
    number = Column(String, index=True)
    title = Column(String)

    slides = relationship(
        "SlideModel", back_populates="hymn", cascade="all, delete-orphan"
    )
    service_plans = relationship("ServicePlanHymnModel", back_populates="hymn")


class SlideModel(Base):
    __tablename__ = "slides"

    id = Column(Integer, primary_key=True, index=True)
    hymn_id = Column(Integer, ForeignKey("hymns.id"))
    label = Column(String)
    content = Column(Text)
    order = Column(Integer)
    type = Column(String, default="VMIX")  # 'VMIX' or 'PPT'

    hymn = relationship("HymnModel", back_populates="slides")


class ServicePlanHymnModel(Base):
    __tablename__ = "service_plan"

    id = Column(Integer, primary_key=True, index=True)
    sequence = Column(Integer, unique=True)
    hymn_id = Column(Integer, ForeignKey("hymns.id"))

    hymn = relationship("HymnModel", back_populates="service_plans")


class ServiceProgramModel(Base):
    __tablename__ = "programs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    is_active = Column(Boolean, default=False)
    template_id = Column(
        Integer, ForeignKey("presentation_templates.id"), nullable=True
    )
    last_used = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    template = relationship("PresentationTemplateModel")
    items = relationship(
        "ServiceProgramItemModel",
        back_populates="program",
        cascade="all, delete-orphan",
    )


class ServiceProgramItemModel(Base):
    __tablename__ = "program_items"

    id = Column(Integer, primary_key=True, index=True)
    program_id = Column(Integer, ForeignKey("programs.id"))
    sequence = Column(Integer)
    title = Column(String)
    subtitle = Column(String)
    tag = Column(String)
    is_muted = Column(Boolean, default=False)

    program = relationship("ServiceProgramModel", back_populates="items")


class PresentationTemplateModel(Base):
    __tablename__ = "presentation_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    filename = Column(String)


class AppSettingModel(Base):
    __tablename__ = "app_settings"

    key = Column(String, primary_key=True)
    value = Column(String)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class VmixRow(BaseModel):
    HymnNumber: str
    Title: str
    Label: str
    SlideText: str

    model_config = ConfigDict(from_attributes=True)
