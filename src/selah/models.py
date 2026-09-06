from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey,
    UniqueConstraint,
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


class HymnSetModel(Base):
    __tablename__ = "hymn_sets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    is_active = Column(Boolean, default=False)
    last_used = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    items = relationship(
        "ServicePlanHymnModel",
        back_populates="set",
        cascade="all, delete-orphan",
    )


class ServicePlanHymnModel(Base):
    __tablename__ = "service_plan"
    __table_args__ = (UniqueConstraint("set_id", "sequence"),)

    id = Column(Integer, primary_key=True, index=True)
    set_id = Column(Integer, ForeignKey("hymn_sets.id"))
    sequence = Column(Integer)
    hymn_id = Column(Integer, ForeignKey("hymns.id"))

    hymn = relationship("HymnModel", back_populates="service_plans")
    set = relationship("HymnSetModel", back_populates="items")


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


class DataTableModel(Base):
    __tablename__ = "data_tables"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    slug = Column(String, unique=True, index=True)
    columns_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    rows = relationship(
        "DataTableRowModel",
        back_populates="table",
        cascade="all, delete-orphan",
    )
    pattern = relationship(
        "DataTablePatternModel",
        back_populates="table",
        uselist=False,
        cascade="all, delete-orphan",
    )


class DataTableRowModel(Base):
    __tablename__ = "data_table_rows"

    id = Column(Integer, primary_key=True, index=True)
    table_id = Column(Integer, ForeignKey("data_tables.id"))
    sequence = Column(Integer)
    data_json = Column(Text, default="{}")

    table = relationship("DataTableModel", back_populates="rows")


class DataTablePatternModel(Base):
    __tablename__ = "data_table_patterns"

    id = Column(Integer, primary_key=True, index=True)
    table_id = Column(Integer, ForeignKey("data_tables.id"), unique=True)
    pattern_name = Column(String)
    column_name = Column(String)
    is_enabled = Column(Boolean, default=False)

    table = relationship("DataTableModel", back_populates="pattern")


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
