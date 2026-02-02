import enum
from sqlalchemy import Column, String, DateTime, Enum, Float, Text, ForeignKey
from sqlalchemy.sql import func

from app.core.db import Base


class TowStatus(str, enum.Enum):
    NEW = "NEW"
    ASSIGNED = "ASSIGNED"
    EN_ROUTE = "EN_ROUTE"
    ARRIVED = "ARRIVED"
    TOWED = "TOWED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class TowJob(Base):
    __tablename__ = "tow_jobs"

    id = Column(String, primary_key=True)  # uuid string

    plate_number = Column(String, index=True, nullable=False)
    officer_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)

    status = Column(Enum(TowStatus), default=TowStatus.NEW, nullable=False)

    assigned_driver_id = Column(String, ForeignKey("users.id"), index=True, nullable=True)

    violation_type = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

    location_lat = Column(Float, nullable=False)
    location_lng = Column(Float, nullable=False)
    location_accuracy_m = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
