from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func

from app.core.db import Base


class TowJobEvent(Base):
    __tablename__ = "tow_job_events"

    id = Column(String, primary_key=True)  # uuid
    tow_job_id = Column(String, ForeignKey("tow_jobs.id"), index=True, nullable=False)
    actor_user_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)

    event_type = Column(String, nullable=False)  # CREATED, ASSIGNED, STATUS_CHANGED, PHOTO_UPLOADED
    message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
