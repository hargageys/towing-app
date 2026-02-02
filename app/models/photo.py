# =========================
# FILE: app/models/photo.py
# =========================
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Float
from sqlalchemy.sql import func

from app.core.db import Base


class TowJobPhoto(Base):
    __tablename__ = "tow_job_photos"

    id = Column(String, primary_key=True)  # uuid
    tow_job_id = Column(String, ForeignKey("tow_jobs.id"), index=True, nullable=False)
    uploaded_by_user_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)

    photo_type = Column(String, nullable=False)     # BEFORE, AFTER, PLATE_CLOSEUP, OTHER
    file_path = Column(String, nullable=False)      # local path for now
    content_type = Column(String, nullable=False)   # image/jpeg, etc
    size_bytes = Column(Integer, nullable=False)

    # NEW: per-photo geo + capture time (authoritative from device/app)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)
    accuracy_m = Column(Float, nullable=True)
    captured_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# from sqlalchemy import Column, String, DateTime, ForeignKey, Integer
# from sqlalchemy.sql import func

# from app.core.db import Base


# class TowJobPhoto(Base):
#     __tablename__ = "tow_job_photos"

#     id = Column(String, primary_key=True)  # uuid
#     tow_job_id = Column(String, ForeignKey("tow_jobs.id"), index=True, nullable=False)
#     uploaded_by_user_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)

#     photo_type = Column(String, nullable=False)   # BEFORE, AFTER, PLATE_CLOSEUP, OTHER
#     file_path = Column(String, nullable=False)    # local path for now
#     content_type = Column(String, nullable=False) # image/jpeg, etc
#     size_bytes = Column(Integer, nullable=False)

#     created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


